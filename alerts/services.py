"""Lecturas privadas por usuario y eventos automáticos idempotentes."""
from datetime import date, timedelta
from decimal import Decimal, localcontext
import hashlib
import json
import logging

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from countries.models import Pais
from economics.models import LoteActualizacion
from economics.services import registrar_actualizacion
from risk.models import IndiceRiesgo
from audit.services import registrar_actividad

from .models import Alerta, LecturaAlerta
from .selectors import alertas_visibles

logger = logging.getLogger(__name__)


@transaction.atomic
def leer_alerta(usuario, alerta_id, *, ip=None):
    get_user_model().objects.select_for_update().get(pk=usuario.pk)
    alerta = get_object_or_404(alertas_visibles(usuario).select_for_update(), pk=alerta_id)
    lectura, created = LecturaAlerta.objects.get_or_create(usuario=usuario, alerta=alerta)
    if created:
        registrar_actividad(usuario=usuario, accion="EDITAR", entidad="Alerta", entidad_id=alerta.pk, ip=ip,
                            detalle={"operacion": "leer_alerta"})
    return lectura


@transaction.atomic
def leer_todas(usuario, *, ip=None):
    get_user_model().objects.select_for_update().get(pk=usuario.pk)
    ids = list(alertas_visibles(usuario).filter(leida=False).values_list("pk", flat=True))
    LecturaAlerta.objects.bulk_create([LecturaAlerta(usuario=usuario, alerta_id=pk) for pk in ids], ignore_conflicts=True)
    if ids:
        registrar_actividad(usuario=usuario, accion="EDITAR", entidad="Alerta", ip=ip,
                            detalle={"operacion": "leer_todas", "marcadas": len(ids)})
    return len(ids)


def crear_evento(pais, rule, evidence, tipo, severidad, titulo, mensaje, usuario=None):
    payload = {"regla": rule, "pais": pais.pk, "usuario": usuario.pk if usuario else None, "evidencia": evidence}
    key = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    _, created = Alerta.objects.get_or_create(clave_evento=key, defaults={
        "pais": pais, "usuario": usuario, "tipo_alerta": tipo, "severidad": severidad,
        "titulo": titulo, "mensaje": mensaje, "detalle": payload})
    return int(created)


@transaction.atomic
def generar_para_indice(index_id):
    code = IndiceRiesgo.objects.values_list("pais_id", flat=True).get(pk=index_id)
    # Igual que el productor: país antes del índice. Se relee el marcador
    # después del bloqueo para que un segundo trabajador no lo procese otra vez.
    pais = Pais.objects.select_for_update().get(pk=code)
    index = IndiceRiesgo.objects.select_for_update().get(pk=index_id)
    if index.fecha_alertas_procesadas is not None:
        return 0
    previous = IndiceRiesgo.objects.filter(pais=pais).filter(
        # timestamp + id reproduce el orden utilizado por el ranking.
        Q(fecha_calculo__lt=index.fecha_calculo) | Q(fecha_calculo=index.fecha_calculo, pk__lt=index.pk)
    ).order_by("-fecha_calculo", "-pk").first()
    detail = index.detalle_calculo
    indicators = detail.get("indicadores", {})
    quotes = detail.get("cotizaciones", [])
    created = 0
    if index.indice_compuesto < 25:
        evidence = {"version_formula": index.version_formula, "indice_compuesto": str(index.indice_compuesto),
                    "indicadores": indicators, "pib_anterior": detail.get("pib_anterior"), "cotizaciones": quotes,
                    "datos_parciales": detail.get("datos_parciales", False)}
        created += crear_evento(pais, "IRPC_CRITICO", evidence, "RIESGO", "CRITICAL",
                               "Riesgo crítico", f"IRPC de {pais.nombre}: {index.indice_compuesto} (<25).")
    if previous and previous.indice_compuesto - index.indice_compuesto > 15:
        created += crear_evento(pais, "CAIDA_IRPC", {"indice_anterior": previous.pk, "indice_actual": index.pk,
            "valor_anterior": str(previous.indice_compuesto), "valor_actual": str(index.indice_compuesto)},
            "RIESGO", "WARNING", "Caída del IRPC", f"El IRPC de {pais.nombre} cayó más de 15 puntos.")
    inflation = indicators.get("INFLACION")
    if inflation and Decimal(inflation["valor"]) > 50:
        created += crear_evento(pais, "INFLACION_CRITICA", inflation, "INDICADOR", "CRITICAL",
            "Inflación superior al 50 %", f"Inflación de {pais.nombre}: {inflation['valor']} %.")
    by_date = {date.fromisoformat(row["fecha"]): row for row in quotes}
    if by_date:
        day = max(by_date)
        current, prior = by_date[day], by_date.get(day - timedelta(days=1))
        if prior:
            with localcontext() as context:
                context.prec = 64
                variation = (Decimal(current["tasa"]) / Decimal(prior["tasa"]) - 1) * 100
            # Magnitud absoluta: alerta tanto depreciación como apreciación fuertes.
            if variation.copy_abs() > 3:
                created += crear_evento(pais, "VARIACION_CAMBIARIA", {"actual": current, "anterior": prior,
                    "variacion_porcentual": str(variation)}, "TIPO_CAMBIO", "WARNING",
                    "Variación cambiaria superior al 3 %", f"Variación diaria de {pais.nombre}: {variation:.6f} %.")
    # También se confirma cuando ninguna regla se activa. Un fallo en cualquier
    # regla o al guardar este marcador revierte todos los eventos del índice.
    index.fecha_alertas_procesadas = timezone.now()
    index.save(update_fields=["fecha_alertas_procesadas"])
    return created


@transaction.atomic
def generar_para_lote(lote_id, pais_id):
    # Mismo orden que el productor: país antes del lote. El marcador se guarda
    # junto a la alerta, evitando pérdidas o duplicados al fallar o competir.
    pais = Pais.objects.select_for_update().get(pk=pais_id)
    lote = LoteActualizacion.objects.select_for_update().get(pk=lote_id)
    if lote.fecha_alerta is not None:
        return 0
    # La revisión de la cotización permanece en la evidencia que crear_evento
    # incluye en el hash de Alerta, además del hash del propio lote.
    created = crear_evento(pais, "DATOS_NUEVOS", {"datos": lote.datos},
        "TIPO_CAMBIO" if all(item["tipo"] == "TIPO_CAMBIO" for item in lote.datos) else "INDICADOR",
        "INFO", "Datos actualizados", f"Se sincronizaron {len(lote.datos)} datos nuevos de {pais.nombre}.")
    lote.fecha_alerta = timezone.now()
    lote.save(update_fields=["fecha_alerta"])
    return created


def generar_alertas(indices=(), datos_nuevos=(), *, paises=None, limite=100):
    if type(limite) is not int or not 1 <= limite <= 1000:
        raise ValueError("El límite de trabajos debe estar entre 1 y 1000.")
    # Materializar para reutilizar un filtro iterable durante selección y conteo.
    paises = set(paises) if paises is not None else None
    result = {"creadas": 0, "errores": []}
    # Compatibilidad con referencias explícitas de workflows existentes. No
    # eluden el límite ni restringen la recuperación a los índices más nuevos.
    for item in indices:
        if paises is not None and item["pais"] not in paises:
            continue
        if not IndiceRiesgo.objects.filter(pk=item["id"], pais_id=item["pais"]).exists():
            result["errores"].append({"pais": item["pais"], "indice": item["id"],
                                      "mensaje": "Índice de riesgo no encontrado."})
    grouped = {}
    for item in datos_nuevos:
        grouped.setdefault(item["pais"], []).append(item)
    for code, events in grouped.items():
        try:
            with transaction.atomic():
                Pais.objects.select_for_update().get(pk=code)
                registrar_actualizacion(code, events)
        except (Pais.DoesNotExist, DatabaseError, ValidationError):
            logger.error("No se pudo registrar el lote de sincronización", extra={"pais": code})
            result["errores"].append({"pais": code, "mensaje": "No se pudo registrar el lote de sincronización."})
    pending = LoteActualizacion.objects.filter(fecha_alerta__isnull=True)
    pending_indices = IndiceRiesgo.objects.filter(fecha_alertas_procesadas__isnull=True)
    if paises is not None:
        pending = pending.filter(pais_id__in=paises)
        pending_indices = pending_indices.filter(pais_id__in=paises)
    # Un presupuesto común para ambos tipos, por antigüedad y desempate estable.
    # Basta tomar limite candidatos de cada cola; los demás no pueden entrar
    # en los primeros limite del conjunto.
    candidates = [(stamp, "indice", pk, code) for stamp, pk, code in
                  pending_indices.order_by("fecha_calculo", "pk").values_list("fecha_calculo", "pk", "pais_id")[:limite]]
    candidates += [(stamp, "lote", pk, code) for stamp, pk, code in
                   pending.order_by("fecha_creacion", "pk").values_list("fecha_creacion", "pk", "pais_id")[:limite]]
    for _, kind, job_id, code in sorted(candidates)[:limite]:
        try:
            result["creadas"] += (generar_para_indice(job_id) if kind == "indice"
                                  else generar_para_lote(job_id, code))
        except (Pais.DoesNotExist, IndiceRiesgo.DoesNotExist, LoteActualizacion.DoesNotExist,
                DatabaseError, ValidationError):
            message = ("No se pudieron generar alertas de riesgo." if kind == "indice"
                       else "No se pudo generar alerta de sincronización.")
            logger.error(message, extra={"pais": code})
            result["errores"].append({"pais": code, kind: job_id, "mensaje": message})
    result["pendientes"] = pending.count() + pending_indices.count()
    logger.info("Generación de alertas", extra={"sincronizacion": result})
    return result
