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

from countries.models import Pais
from risk.models import IndiceRiesgo

from .models import Alerta, LecturaAlerta
from .selectors import alertas_visibles

logger = logging.getLogger(__name__)


@transaction.atomic
def leer_alerta(usuario, alerta_id):
    get_user_model().objects.select_for_update().get(pk=usuario.pk)
    alerta = get_object_or_404(alertas_visibles(usuario).select_for_update(), pk=alerta_id)
    return LecturaAlerta.objects.get_or_create(usuario=usuario, alerta=alerta)[0]


@transaction.atomic
def leer_todas(usuario):
    get_user_model().objects.select_for_update().get(pk=usuario.pk)
    ids = list(alertas_visibles(usuario).filter(leida=False).values_list("pk", flat=True))
    LecturaAlerta.objects.bulk_create([LecturaAlerta(usuario=usuario, alerta_id=pk) for pk in ids], ignore_conflicts=True)
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
    index = IndiceRiesgo.objects.get(pk=index_id)
    pais = Pais.objects.select_for_update().get(pk=index.pais_id)
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
    return created


def generar_alertas(indices=(), datos_nuevos=()):
    result = {"creadas": 0, "errores": []}
    for item in indices:
        try:
            result["creadas"] += generar_para_indice(item["id"])
        except (IndiceRiesgo.DoesNotExist, Pais.DoesNotExist, DatabaseError, ValidationError):
            logger.error("No se pudieron generar alertas de riesgo", extra={"pais": item["pais"]})
            result["errores"].append({"pais": item["pais"], "mensaje": "No se pudieron generar alertas de riesgo."})
    grouped = {}
    for item in datos_nuevos:
        grouped.setdefault(item["pais"], []).append(item)
    for code, events in grouped.items():
        try:
            with transaction.atomic():
                pais = Pais.objects.select_for_update().get(pk=code)
                events = sorted(events, key=lambda item: json.dumps(item, sort_keys=True))
                result["creadas"] += crear_evento(pais, "DATOS_NUEVOS", {"datos": events},
                    "TIPO_CAMBIO" if all(item["tipo"] == "TIPO_CAMBIO" for item in events) else "INDICADOR",
                    "INFO", "Datos actualizados", f"Se sincronizaron {len(events)} datos nuevos de {pais.nombre}.")
        except (Pais.DoesNotExist, DatabaseError, ValidationError):
            logger.error("No se pudo generar alerta de sincronización", extra={"pais": code})
            result["errores"].append({"pais": code, "mensaje": "No se pudo generar alerta de sincronización."})
    logger.info("Generación de alertas", extra={"sincronizacion": result})
    return result
