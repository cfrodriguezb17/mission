"""Registro explícito: solo metadatos tipados, nunca payloads ni respuestas."""
from ipaddress import ip_address
import logging

from django.db import DatabaseError, transaction

from .models import LogActividad

logger = logging.getLogger(__name__)


OPERACIONES = {
    "registro", "perfil", "login", "consulta", "crear_portafolio", "editar_portafolio",
    "eliminar_portafolio", "agregar_posicion", "editar_posicion", "cerrar_posicion",
    "sync_indicadores", "update_tipos_cambio", "calcular_riesgos", "sync_countries",
    "leer_alerta", "leer_todas", "export_pdf",
    "admin",
}
CAMPOS = {
    "email", "nombre_completo", "nombre", "descripcion", "es_publico", "pais",
    "tipo_activo", "monto_inversion_usd", "fecha_entrada", "fecha_salida", "notas",
    "rol", "is_active", "is_staff", "is_superuser", "groups", "user_permissions",
    "codigo", "codigo_iso", "moneda", "region", "latitud", "longitud", "poblacion",
    "bandera_url", "activo", "unidad", "codigo_world_bank", "tipo", "valor", "anio",
    "fuente", "es_simulado", "moneda_origen", "moneda_destino", "tasa", "fecha",
}
CONTADORES = {"portafolio_id", "version", "creados", "actualizados", "calculados", "errores", "marcadas"}


def obtener_ip(request):
    # No confiar en X-Forwarded-For sin una política explícita de proxies confiables.
    return normalizar_ip(request.META.get("REMOTE_ADDR")) if request is not None else None


def normalizar_ip(value):
    try:
        return str(ip_address(value)) if value else None
    except ValueError:
        return None


def detalle_seguro(detalle):
    if not isinstance(detalle, dict):
        raise ValueError("El detalle de auditoría debe ser un objeto de metadatos.")
    safe = {}
    for key, value in detalle.items():
        valid = False
        if key == "operacion":
            valid = isinstance(value, str) and value in OPERACIONES
        elif key == "origen":
            valid = value in ("HTTP", "COMANDO", "ADMIN")
        elif key == "estado":
            valid = value in ("COMPLETO", "PARCIAL", "ERROR")
        elif key in CONTADORES:
            valid = type(value) is int and value >= 0
        elif key == "credenciales_actualizadas":
            valid = type(value) is bool
        elif key == "campos":
            valid = isinstance(value, list) and all(isinstance(v, str) and v in CAMPOS for v in value)
            value = sorted(set(value)) if valid else value
        elif key == "paises":
            valid = isinstance(value, list) and all(
                isinstance(v, str) and len(v) == 2 and v.isascii() and v.isalpha() and v.isupper()
                for v in value)
        if not valid:
            raise ValueError(f"Metadato de auditoría no permitido: {key}.")
        safe[key] = value
    return safe


def registrar_actividad(*, usuario=None, accion, entidad, entidad_id="", detalle=None, ip=None):
    event = LogActividad(
        usuario=usuario, accion=accion, entidad_afectada=entidad, entidad_id=str(entidad_id),
        detalle=detalle_seguro({} if detalle is None else detalle), ip_address=normalizar_ip(ip),
    )
    # La FK y los constraints los garantiza PostgreSQL. Validar campos sin
    # consultas adicionales: auditar una lectura requiere solo un INSERT.
    event.full_clean(exclude=["usuario"], validate_unique=False, validate_constraints=False)
    event.save()
    return event


def registrar_resultado(result, **event):
    """Los trabajos ya persistidos no se revierten si falla su resumen final."""
    try:
        with transaction.atomic():
            registrar_actividad(**event)
    except DatabaseError:
        logger.error("No se pudo guardar el resumen de auditoría de la tarea.")
        result["auditoria_pendiente"] = True
        result["estado"] = "PARCIAL"
    return result
