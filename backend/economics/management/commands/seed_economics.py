from datetime import date, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from countries.models import Pais
from economics.catalog import COUNTRY_CODES, INDICATORS
from economics.models import IndicadorEconomico, TipoCambio, TipoIndicador
from economics.services import cargar_catalogo, decimal_campo

# Valores exclusivamente ilustrativos, reproducibles y marcados en cada registro.
BASE_VALUES = {"PIB": "300000000000", "INFLACION": "6", "DESEMPLEO": "8",
               "BALANZA_COMERCIAL": "-2", "DEUDA_PIB": "45", "PIB_PERCAPITA": "7000"}
LOCAL_PER_USD = {"COP": "4000", "BRL": "5", "MXN": "18", "ARS": "1000", "CLP": "900",
                 "PEN": "3.7", "UYU": "40", "PYG": "7500", "PAB": "1"}


class Command(BaseCommand):
    help = "Carga 5 años de indicadores y 31 cotizaciones diarias SIMULADAS para 30 variaciones, sin reemplazar registros."

    def add_arguments(self, parser):
        parser.add_argument("--fecha-fin", type=date.fromisoformat, default=None,
                            help="Último día simulado (AAAA-MM-DD); por defecto hoy UTC.")

    @transaction.atomic
    def handle(self, *args, **options):
        end = options["fecha_fin"] or timezone.now().date()
        if end > timezone.now().date() or end.year < 6:
            raise CommandError("Use una fecha no futura y con al menos cinco años previos completos.")
        call_command("seed_countries", stdout=self.stdout)
        cargar_catalogo()
        types = {t.codigo: t for t in TipoIndicador.objects.all()}
        observations = quotes = 0
        currencies = set()
        for country in Pais.objects.filter(pk__in=COUNTRY_CODES, activo=True).order_by("pk"):
            factor = Decimal(COUNTRY_CODES.index(country.pk) + 10) / 10
            for year in range(end.year - 5, end.year):
                for code, _, _, _ in INDICATORS:
                    base = Decimal(BASE_VALUES[code])
                    value = base * factor * (1 + Decimal(year - (end.year - 5)) / 100)
                    _, created = IndicadorEconomico.objects.get_or_create(
                        pais=country, tipo=types[code], anio=year,
                        defaults={"valor": decimal_campo(value, 6), "fuente": "MANUAL", "es_simulado": True},
                    )
                    observations += created
            if country.moneda_id == "USD" or country.moneda_id in currencies:
                continue
            if country.moneda_id not in LOCAL_PER_USD:
                raise CommandError(f"No existe una tasa simulada para {country.moneda_id}.")
            currencies.add(country.moneda_id)
            for offset in range(31):
                day = end - timedelta(days=30 - offset)
                # Mantener los valores del seed previo de 30 días al añadir el extremo inicial.
                local_rate = Decimal(LOCAL_PER_USD[country.moneda_id]) * (1 + Decimal(offset - 1) / 10000)
                _, created = TipoCambio.objects.get_or_create(
                    moneda_origen=country.moneda, moneda_destino_id="USD", fecha=day,
                    defaults={"tasa": decimal_campo(1 / local_rate, 12), "fuente": "DEMO_SIMULADO", "es_simulado": True},
                )
                quotes += created
        self.stdout.write(self.style.SUCCESS(
            f"Datos SIMULADOS creados: {observations} indicadores y {quotes} cotizaciones. Registros previos conservados."
        ))
