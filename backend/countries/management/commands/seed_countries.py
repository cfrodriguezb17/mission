from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from countries.models import Moneda, Pais

# Coordenadas, monedas y regiones del enunciado. Poblaciones redondeadas,
# ilustrativas para demostración: no son cifras oficiales actualizadas.
COUNTRIES = [
    ("CO", "Colombia", "COP", "Peso colombiano", "ANDINA", "4.5709", "-74.2973", 52_000_000),
    ("BR", "Brasil", "BRL", "Real brasileño", "CONO_SUR", "-14.2350", "-51.9253", 216_000_000),
    ("MX", "México", "MXN", "Peso mexicano", "CENTROAMERICA", "23.6345", "-102.5528", 129_000_000),
    ("AR", "Argentina", "ARS", "Peso argentino", "CONO_SUR", "-38.4161", "-63.6167", 46_000_000),
    ("CL", "Chile", "CLP", "Peso chileno", "CONO_SUR", "-35.6751", "-71.5430", 20_000_000),
    ("PE", "Perú", "PEN", "Sol peruano", "ANDINA", "-9.1900", "-75.0152", 34_000_000),
    ("EC", "Ecuador", "USD", "Dólar estadounidense", "ANDINA", "-1.8312", "-78.1834", 18_000_000),
    ("UY", "Uruguay", "UYU", "Peso uruguayo", "CONO_SUR", "-32.5228", "-55.7658", 3_400_000),
    ("PY", "Paraguay", "PYG", "Guaraní paraguayo", "CONO_SUR", "-23.4425", "-58.4438", 7_000_000),
    ("PA", "Panamá", "PAB", "Balboa panameño", "CENTROAMERICA", "8.5380", "-80.7821", 4_400_000),
]


class Command(BaseCommand):
    help = "Carga 10 países y monedas de demostración; conserva registros existentes salvo --update."

    def add_arguments(self, parser):
        parser.add_argument("--update", action="store_true", help="Reemplaza los campos de los países y monedas incluidos con los datos de demostración.")

    @transaction.atomic
    def handle(self, *args, **options):
        created_countries = created_currencies = 0
        for code, name, currency, currency_name, region, lat, lon, population in COUNTRIES:
            currency_method = Moneda.objects.update_or_create if options["update"] else Moneda.objects.get_or_create
            moneda, created = currency_method(codigo=currency, defaults={"nombre": currency_name})
            created_currencies += created
            defaults = {
                "nombre": name, "moneda": moneda, "region": region,
                "latitud": Decimal(lat), "longitud": Decimal(lon), "poblacion": population,
                "bandera_url": f"https://flagcdn.com/w320/{code.lower()}.png", "activo": True,
            }
            Pais(codigo_iso=code, **defaults).full_clean(validate_unique=False)
            country_method = Pais.objects.update_or_create if options["update"] else Pais.objects.get_or_create
            _, created = country_method(codigo_iso=code, defaults=defaults)
            created_countries += created
        self.stdout.write(self.style.SUCCESS(
            f"Países creados: {created_countries}; monedas creadas: {created_currencies}. "
            "Poblaciones ilustrativas de demostración."
        ))
