"""Cálculos históricos desde datos persistidos, sin proveedores externos."""
from datetime import timedelta
import logging

from django.db import DatabaseError, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from countries.models import Moneda, Pais
from economics.models import IndicadorEconomico, TipoCambio

from .calculations import calculate_irpc
from .models import IndiceRiesgo

logger = logging.getLogger(__name__)


@transaction.atomic
def calcular_pais(codigo_iso):
    # Mismo bloqueo que economics: la instantánea no mezcla una escritura en curso.
    pais = Pais.objects.select_for_update().get(pk=codigo_iso, activo=True)
    Moneda.objects.select_for_update().get(pk=pais.moneda_id)
    now = timezone.now()
    end = now.date()
    rows = list(IndicadorEconomico.objects.filter(pais=pais, anio__lt=now.year).order_by("tipo_id", "-anio"))
    latest = {}
    for row in rows:
        latest.setdefault(row.tipo_id, row)
    gdp = latest.get("PIB")
    previous = next((row for row in rows if row.tipo_id == "PIB" and gdp and row.anio == gdp.anio - 1), None)
    quotes = list(TipoCambio.objects.filter(moneda_origen_id=pais.moneda_id, moneda_destino_id="USD",
                  fecha__range=(end - timedelta(days=30), end)).order_by("fecha"))
    result = calculate_irpc({code: row.valor for code, row in latest.items()},
                            previous.valor if previous else None, {row.fecha: row.tasa for row in quotes},
                            end, identity=pais.moneda_id == "USD")
    detail = result["detalle_calculo"]

    def snapshot(row):
        return {"id": row.pk, "tipo": row.tipo_id, "valor": str(row.valor), "anio": row.anio,
                "fuente": row.fuente, "es_simulado": row.es_simulado,
                "fecha_actualizacion": row.fecha_actualizacion.isoformat()}

    detail.update({"fecha_referencia": end.isoformat(), "anio_maximo": now.year - 1,
                   "indicadores": {code: snapshot(row) for code, row in latest.items()},
                   "pib_anterior": snapshot(previous) if previous else None,
                   "cotizaciones": [{"id": row.pk, "tasa": str(row.tasa), "fecha": row.fecha.isoformat(),
                        "fuente": row.fuente, "es_simulado": row.es_simulado,
                        "moneda_origen": row.moneda_origen_id, "moneda_destino": row.moneda_destino_id} for row in quotes],
                   "contiene_simulaciones": any(row.es_simulado for row in latest.values())
                       or bool(previous and previous.es_simulado) or any(row.es_simulado for row in quotes)})
    index = IndiceRiesgo(pais=pais, fecha_calculo=now, **result)
    index.full_clean()
    index.save()
    return index


def recalcular_riesgos(paises=None):
    codes = list(dict.fromkeys(paises)) if paises is not None else list(
        Pais.objects.filter(activo=True).order_by("pk").values_list("pk", flat=True))
    result = {"calculados": [], "errores": []}
    for code in codes:
        try:
            index = calcular_pais(code)
            result["calculados"].append({"pais": code, "id": index.pk, "indice_compuesto": str(index.indice_compuesto),
                                        "datos_parciales": index.detalle_calculo["datos_parciales"]})
        except Pais.DoesNotExist:
            result["errores"].append({"pais": code, "mensaje": "País no encontrado o inactivo."})
        except (ValidationError, DatabaseError):
            logger.exception("No se pudo guardar el cálculo de riesgo", extra={"pais": code})
            result["errores"].append({"pais": code, "mensaje": "No se pudo guardar el cálculo de riesgo."})
    logger.info("Recálculo de riesgos", extra={"sincronizacion": result})
    return result
