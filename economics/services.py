"""Persistencia acotada por país/par; llamadas HTTP fuera de transacciones."""
import logging
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from countries.models import Moneda, Pais
from integrations.exchange_rate import ExchangeRateClient
from integrations.http import JsonClient, ProviderError
from integrations.world_bank import WorldBankClient

from .catalog import COUNTRY_CODES, INDICATORS
from .models import IndicadorEconomico, TipoCambio, TipoIndicador

logger = logging.getLogger(__name__)


def cargar_catalogo():
    for code, name, unit, wb in INDICATORS:
        TipoIndicador.objects.get_or_create(codigo=code, defaults={
            "nombre": name, "unidad": unit, "codigo_world_bank": wb,
        })


def decimal_campo(value, places, max_digits=24):
    try:
        result = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    except (InvalidOperation, AttributeError) as exc:
        raise ProviderError("Valor fuera de la precisión admitida.") from exc
    if not result.is_finite() or abs(result) >= Decimal(10) ** (max_digits - places):
        raise ProviderError("Valor fuera de la precisión admitida.")
    return result


def _resultado():
    return {"creados": 0, "actualizados": 0, "sin_cambios": 0, "manuales_conservados": 0,
            "faltantes": [], "paises_procesados": [], "errores": [], "datos_nuevos": []}


def _log(event, result):
    logger.info(event, extra={"sincronizacion": result})


def _error(result, pais, message):
    result["errores"].append({"pais": pais, "mensaje": message})
    logger.error("Fallo de sincronización", extra={"pais": pais, "motivo": message})


@transaction.atomic
def guardar_indicadores(pais, observations, catalog, start, end):
    # Serializa escrituras del mismo país, incluso si aún no existe la observación.
    Pais.objects.select_for_update().get(pk=pais.pk)
    counts = {"creados": 0, "actualizados": 0, "sin_cambios": 0, "manuales_conservados": 0}
    present = set()
    events = []
    for row in observations:
        tipo = catalog[row["codigo_world_bank"]]
        key = (tipo.codigo, row["anio"])
        if row["valor"] is None:
            continue
        if key in present:
            raise ProviderError("World Bank devolvió observaciones duplicadas.")
        present.add(key)
        value = decimal_campo(row["valor"], 6)
        existing = IndicadorEconomico.objects.filter(pais=pais, tipo=tipo, anio=row["anio"]).first()
        if existing and existing.fuente == "MANUAL" and not existing.es_simulado:
            counts["manuales_conservados"] += 1
            continue
        if existing and existing.valor == value and existing.fuente == "WORLD_BANK" and not existing.es_simulado:
            counts["sin_cambios"] += 1
            continue
        observation = existing or IndicadorEconomico(pais=pais, tipo=tipo, anio=row["anio"])
        observation.valor = value
        observation.fuente = "WORLD_BANK"
        observation.es_simulado = False
        observation.full_clean()
        observation.save()
        events.append({"pais": pais.pk, "tipo": tipo.codigo, "id": observation.pk, "anio": observation.anio,
                       "valor": str(observation.valor), "fuente": observation.fuente,
                       "fecha_actualizacion": observation.fecha_actualizacion.isoformat()})
        counts["actualizados" if existing else "creados"] += 1
    counts["faltantes"] = [{"pais": pais.pk, "tipo": code, "anio": year}
                            for code, _, _, _ in INDICATORS for year in range(start, end + 1)
                            if (code, year) not in present]
    counts["datos_nuevos"] = events
    return counts


def sincronizar_indicadores(*, paises=None, anio_inicio=None, anio_fin=None, presupuesto=180, client=None):
    end = anio_fin if anio_fin is not None else timezone.now().year - 1
    start = anio_inicio if anio_inicio is not None else end - 4
    if start < 1 or end > timezone.now().year or start > end or end - start > 19:
        raise ValueError("Use un rango de hasta 20 años, ordenado y sin años futuros.")
    codes = list(dict.fromkeys(paises if paises is not None else COUNTRY_CODES))
    if not codes or set(codes) - set(COUNTRY_CODES):
        raise ValueError("Seleccione países incluidos en el alcance de DataPulse.")
    result = _resultado()
    deadline = time.monotonic() + presupuesto
    client = client or WorldBankClient(JsonClient(deadline=deadline))
    cargar_catalogo()
    catalog = {t.codigo_world_bank: t for t in TipoIndicador.objects.all()}
    countries = {p.pk: p for p in Pais.objects.filter(pk__in=codes, activo=True)}
    _log("Inicio de sincronización de indicadores", {"paises": codes, "anio_inicio": start, "anio_fin": end})
    for code in codes:
        if code not in countries:
            _error(result, code, "País no cargado o inactivo; ejecute seed_countries.")
            continue
        try:
            if time.monotonic() >= deadline:
                raise ProviderError("Se agotó el tiempo de sincronización; reintente los países pendientes.")
            observations = client.indicadores(code, list(catalog), start, end)
            counts = guardar_indicadores(countries[code], observations, catalog, start, end)
            for key in ("creados", "actualizados", "sin_cambios", "manuales_conservados"):
                result[key] += counts[key]
            result["faltantes"].extend(counts["faltantes"])
            result["datos_nuevos"].extend(counts["datos_nuevos"])
            result["paises_procesados"].append(code)
        except (ProviderError, ValidationError, IntegrityError) as exc:
            _error(result, code, str(exc))
    result["estado"] = "PARCIAL" if result["errores"] or result["faltantes"] else "COMPLETO"
    result["recalculo_y_alertas_pendientes"] = True
    _log("Fin de sincronización de indicadores", result)
    return result


@transaction.atomic
def guardar_cotizacion(moneda, fecha, tasa, eventos=None):
    Moneda.objects.select_for_update().get(pk=moneda.pk)
    value = decimal_campo(tasa, 12)
    if value <= 0:
        raise ProviderError("La tasa es demasiado pequeña o no es positiva.")
    existing = TipoCambio.objects.filter(moneda_origen=moneda, moneda_destino_id="USD", fecha=fecha).first()
    if existing and not existing.es_simulado and existing.fuente != "EXCHANGE_RATE":
        return "manuales_conservados"
    if existing and existing.tasa == value and not existing.es_simulado:
        return "sin_cambios"
    quote = existing or TipoCambio(moneda_origen=moneda, moneda_destino_id="USD", fecha=fecha)
    quote.tasa = value
    quote.fuente = "EXCHANGE_RATE"
    quote.es_simulado = False
    quote.full_clean()
    quote.save()
    if eventos is not None:
        eventos.append({"tipo": "TIPO_CAMBIO", "id": quote.pk, "moneda_origen": moneda.pk,
                       "moneda_destino": "USD", "tasa": str(quote.tasa), "fecha": fecha.isoformat(),
                       "fuente": quote.fuente})
    return "actualizados" if existing else "creados"


def actualizar_tipos_cambio(*, client=None):
    result = _resultado()
    _log("Inicio de actualización cambiaria", {})
    client = client or ExchangeRateClient(JsonClient(deadline=time.monotonic() + 30))
    if not Moneda.objects.filter(pk="USD").exists():
        _error(result, None, "Falta la moneda USD; ejecute seed_countries.")
        result["estado"] = "PARCIAL"
        _log("Fin de actualización cambiaria", result)
        return result
    try:
        date, rates = client.cotizaciones()
    except ProviderError as exc:
        _error(result, None, str(exc))
        result["estado"] = "PARCIAL"
        _log("Fin de actualización cambiaria", result)
        return result
    # Un solo llamado HTTP y una cotización por moneda aunque varios países la usen.
    countries = list(Pais.objects.filter(pk__in=COUNTRY_CODES, activo=True).select_related("moneda"))
    processed = set()
    currency_events = {}
    for pais in countries:
        if pais.moneda_id == "USD":
            result["paises_procesados"].append(pais.pk)
            continue
        try:
            if pais.moneda_id not in processed:
                if pais.moneda_id not in rates:
                    raise ProviderError("El proveedor no devolvió esta moneda.")
                events = []
                key = guardar_cotizacion(pais.moneda, date, ExchangeRateClient.invertir(rates[pais.moneda_id]), eventos=events)
                result[key] += 1
                currency_events[pais.moneda_id] = events
                processed.add(pais.moneda_id)
            result["datos_nuevos"].extend({**event, "pais": pais.pk} for event in currency_events[pais.moneda_id])
            result["paises_procesados"].append(pais.pk)
        except (ProviderError, ValidationError, IntegrityError) as exc:
            _error(result, pais.pk, str(exc))
    result["fecha"] = date.isoformat()
    result["estado"] = "PARCIAL" if result["errores"] else "COMPLETO"
    result["alertas_pendientes"] = True
    _log("Fin de actualización cambiaria", result)
    return result
