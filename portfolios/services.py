"""Todas las escrituras bloquean el portafolio y comparten su versión."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError

from countries.models import Pais
from audit.services import registrar_actividad

from .models import Portafolio, Posicion
from .permissions import exigir_edicion, exigir_escritura


class ConflictoVersion(APIException):
    status_code = 409
    default_code = "version_desactualizada"

    def __init__(self, actual):
        super().__init__({"detail": "El portafolio fue modificado por otro usuario. Recargue los datos antes de guardar.",
                          "codigo": self.default_code, "version_actual": actual})
        self.detail["version_actual"] = actual


def _usuario_actual(usuario):
    try:
        return get_user_model().objects.get(pk=usuario.pk)
    except get_user_model().DoesNotExist:
        raise NotFound("Usuario no encontrado.")


def _bloquear(usuario, portfolio_id, version, solo_propietario=False):
    try:
        portfolio = Portafolio.objects.select_for_update().get(pk=portfolio_id, activo=True)
    except Portafolio.DoesNotExist:
        raise NotFound("Portafolio no encontrado.")
    # Se evalúan permisos sobre el estado obtenido después de adquirir el bloqueo.
    actor = _usuario_actual(usuario)
    exigir_edicion(actor, portfolio, solo_propietario=solo_propietario)
    if type(version) is not int or version < 1:
        raise ValidationError({"version": "Envíe la versión entera positiva del portafolio."})
    if portfolio.version != version:
        raise ConflictoVersion(portfolio.version)
    return actor, portfolio


def _validar_modelo(instance):
    try:
        instance.full_clean(validate_unique=False, validate_constraints=False)
    except ModelValidationError as exc:
        raise ValidationError(exc.message_dict)


def _guardar_portafolio(portfolio):
    if Portafolio.objects.filter(usuario_id=portfolio.usuario_id, nombre=portfolio.nombre).exclude(pk=portfolio.pk).exists():
        raise ValidationError({"nombre": "Ya tiene un portafolio con ese nombre, incluso si está eliminado."})
    _validar_modelo(portfolio)
    try:
        with transaction.atomic():
            portfolio.save()
    except IntegrityError as exc:
        if getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None) == "portafolio_usuario_nombre_uq":
            raise ValidationError({"nombre": "Ya tiene un portafolio con ese nombre."}) from exc
        raise


@transaction.atomic
def crear_portafolio(usuario, datos, *, ip=None):
    actor = _usuario_actual(usuario)
    exigir_escritura(actor)
    portfolio = Portafolio(usuario=actor, **datos)
    portfolio.nombre = portfolio.nombre.strip()
    _guardar_portafolio(portfolio)
    registrar_actividad(usuario=actor, accion="CREAR", entidad="Portafolio", entidad_id=portfolio.pk, ip=ip,
                        detalle={"operacion": "crear_portafolio", "version": portfolio.version})
    return portfolio


@transaction.atomic
def editar_portafolio(usuario, portfolio_id, version, datos, *, ip=None):
    actor, portfolio = _bloquear(usuario, portfolio_id, version)
    if "es_publico" in datos and datos["es_publico"] != portfolio.es_publico:
        exigir_edicion(actor, portfolio, solo_propietario=True)
    for field, value in datos.items():
        setattr(portfolio, field, value.strip() if field == "nombre" else value)
    portfolio.version += 1
    _guardar_portafolio(portfolio)
    registrar_actividad(usuario=actor, accion="EDITAR", entidad="Portafolio", entidad_id=portfolio.pk, ip=ip,
                        detalle={"operacion": "editar_portafolio", "version": portfolio.version, "campos": sorted(datos)})
    return portfolio


@transaction.atomic
def eliminar_portafolio(usuario, portfolio_id, version, *, ip=None):
    actor, portfolio = _bloquear(usuario, portfolio_id, version, solo_propietario=True)
    portfolio.activo = False
    portfolio.version += 1
    portfolio.save(update_fields=["activo", "version", "fecha_modificacion"])
    registrar_actividad(usuario=actor, accion="ELIMINAR", entidad="Portafolio", entidad_id=portfolio.pk, ip=ip,
                        detalle={"operacion": "eliminar_portafolio", "version": portfolio.version})
    return portfolio


def _validar_posicion(portfolio, position):
    _validar_modelo(position)
    try:
        country = Pais.objects.get(pk=position.pais_id, activo=True)
    except Pais.DoesNotExist:
        raise ValidationError({"pais": "Seleccione un país existente y activo."})
    if position.tipo_activo == "MONEDA" and country.moneda_id == "USD":
        raise ValidationError({"tipo_activo": "No se permite MONEDA para un país cuya moneda principal es USD."})
    if position.fecha_salida is not None:
        return
    others = portfolio.posiciones.filter(fecha_salida__isnull=True).exclude(pk=position.pk)
    total = others.aggregate(total=Sum("monto_inversion_usd"))["total"] or Decimal("0")
    if total + position.monto_inversion_usd > Decimal("50000000"):
        raise ValidationError({"monto_inversion_usd": "El capital activo no puede superar 50.000.000 USD."})
    if others.filter(pais_id=position.pais_id, tipo_activo=position.tipo_activo).count() >= 2:
        raise ValidationError({"tipo_activo": "Solo se permiten dos posiciones activas por país y tipo de activo."})


def _incrementar_version(portfolio):
    portfolio.version += 1
    portfolio.save(update_fields=["version", "fecha_modificacion"])


def _posicion(portfolio, position_id):
    try:
        return portfolio.posiciones.get(pk=position_id)
    except Posicion.DoesNotExist:
        raise NotFound("Posición no encontrada en este portafolio.")


@transaction.atomic
def agregar_posicion(usuario, portfolio_id, version, datos, *, ip=None):
    actor, portfolio = _bloquear(usuario, portfolio_id, version)
    position = Posicion(portafolio=portfolio, **datos)
    _validar_posicion(portfolio, position)
    position.save()
    _incrementar_version(portfolio)
    registrar_actividad(usuario=actor, accion="CREAR", entidad="Posicion", entidad_id=position.pk, ip=ip,
                        detalle={"operacion": "agregar_posicion", "portafolio_id": portfolio.pk, "version": portfolio.version})
    return position, portfolio


@transaction.atomic
def editar_posicion(usuario, portfolio_id, position_id, version, datos, *, ip=None):
    actor, portfolio = _bloquear(usuario, portfolio_id, version)
    position = _posicion(portfolio, position_id)
    for field, value in datos.items():
        setattr(position, field, value)
    _validar_posicion(portfolio, position)
    position.save()
    _incrementar_version(portfolio)
    registrar_actividad(usuario=actor, accion="EDITAR", entidad="Posicion", entidad_id=position.pk, ip=ip,
                        detalle={"operacion": "editar_posicion", "portafolio_id": portfolio.pk,
                                 "version": portfolio.version, "campos": sorted(datos)})
    return position, portfolio


@transaction.atomic
def cerrar_posicion(usuario, portfolio_id, position_id, version, fecha_salida=None, *, ip=None):
    actor, portfolio = _bloquear(usuario, portfolio_id, version)
    position = _posicion(portfolio, position_id)
    if position.fecha_salida is not None:
        raise ValidationError({"fecha_salida": "La posición ya está cerrada."})
    position.fecha_salida = fecha_salida or timezone.localdate()
    _validar_modelo(position)
    position.save(update_fields=["fecha_salida"])
    _incrementar_version(portfolio)
    registrar_actividad(usuario=actor, accion="ELIMINAR", entidad="Posicion", entidad_id=position.pk, ip=ip,
                        detalle={"operacion": "cerrar_posicion", "portafolio_id": portfolio.pk, "version": portfolio.version})
    return position, portfolio
