import logging
import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from economics.catalog import COUNTRY_CODES
from economics.services import decimal_campo
from integrations.http import JsonClient, ProviderError
from integrations.rest_countries import RestCountriesClient

from .models import Pais

logger = logging.getLogger(__name__)


@transaction.atomic
def guardar_pais(code, data):
    country = Pais.objects.select_for_update().get(pk=code)
    # Conservar región y moneda principal del enunciado, incluida PAB en Panamá.
    if country.moneda_id not in data["monedas"]:
        raise ProviderError("El proveedor no incluye la moneda principal configurada del país.")
    data = data.copy()
    currency_name = data.pop("monedas")[country.moneda_id]
    currency = country.moneda
    currency.nombre = currency_name
    currency.full_clean()
    currency.save(update_fields=["nombre"])
    data["latitud"] = decimal_campo(data["latitud"], 6, max_digits=9)
    data["longitud"] = decimal_campo(data["longitud"], 6, max_digits=9)
    for key, value in data.items():
        setattr(country, key, value)
    country.full_clean()
    country.save(update_fields=list(data))


def sincronizar_paises(*, client=None):
    client = client or RestCountriesClient(settings.REST_COUNTRIES_API_KEY,
                                           JsonClient(deadline=time.monotonic() + 120))
    result = {"paises_procesados": [], "errores": []}
    logger.info("Inicio de sincronización de países", extra={"sincronizacion": result})
    for code in Pais.objects.filter(pk__in=COUNTRY_CODES, activo=True).values_list("pk", flat=True):
        try:
            data = client.pais(code)
            guardar_pais(code, data)
            result["paises_procesados"].append(code)
        except (ProviderError, ValidationError, IntegrityError) as exc:
            message = {"pais": code, "mensaje": str(exc)}
            result["errores"].append(message)
            logger.error("Fallo de sincronización de país", extra={"sincronizacion": message})
    logger.info("Fin de sincronización de países", extra={"sincronizacion": result})
    return result
