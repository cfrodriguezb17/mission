from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from countries.models import Moneda, Pais
from economics.models import IndicadorEconomico, TipoCambio, TipoIndicador

from .base import EconomicsTestCase


class EconomicModelTests(EconomicsTestCase):
    def indicator(self, **kwargs):
        fields = {"pais_id": "CO", "tipo_id": "PIB", "anio": 2025,
                  "valor": Decimal("300000000000.123456"), "fuente": "WORLD_BANK"}
        return IndicadorEconomico.objects.create(**(fields | kwargs))

    def quote(self, **kwargs):
        fields = {"moneda_origen_id": "COP", "fecha": date(2026, 1, 1),
                  "tasa": Decimal("0.000250123456"), "fuente": "EXCHANGE_RATE"}
        return TipoCambio.objects.create(**(fields | kwargs))

    def test_catalog_contains_six_normalized_types(self):
        self.assertEqual(TipoIndicador.objects.count(), 6)
        self.assertEqual(TipoIndicador.objects.get(pk="PIB").unidad, "USD")
        columns = {f.name for f in IndicadorEconomico._meta.fields}
        self.assertNotIn("unidad", columns)
        self.assertNotIn("variacion_porcentual", {f.name for f in TipoCambio._meta.fields})

    def test_decimal_precision_negative_values_and_uniqueness(self):
        observation = self.indicator()
        observation.refresh_from_db()
        self.assertEqual(observation.valor, Decimal("300000000000.123456"))
        self.indicator(tipo_id="BALANZA_COMERCIAL", valor="-4.2")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.indicator()

    def test_year_source_and_simulation_constraints(self):
        for invalid in ({"anio": 0}, {"anio": 10000}, {"fuente": "INVALID"}, {"es_simulado": True}):
            with self.subTest(invalid=invalid), self.assertRaises(IntegrityError), transaction.atomic():
                self.indicator(**invalid)

    def test_quote_constraints_and_currency_protection(self):
        quote = self.quote()
        quote.refresh_from_db()
        self.assertEqual(quote.tasa, Decimal("0.000250123456"))
        for invalid in ({}, {"tasa": 0}, {"tasa": -1}, {"moneda_origen_id": "USD"}, {"fuente": " "}):
            with self.subTest(invalid=invalid), self.assertRaises(IntegrityError), transaction.atomic():
                self.quote(**invalid)
        with self.assertRaises(ProtectedError):
            Moneda.objects.get(pk="USD").delete()

    def test_country_and_type_are_protected(self):
        self.indicator()
        for model, code in ((Pais, "CO"), (TipoIndicador, "PIB")):
            with self.assertRaises(ProtectedError):
                model.objects.get(pk=code).delete()

    def test_catalog_rejects_invalid_units_codes_and_duplicate_provider(self):
        for fields in ({"unidad": "EUROS"}, {"codigo": "INVALID"}, {"nombre": " "}, {"codigo_world_bank": " "}):
            with self.subTest(fields=fields), self.assertRaises(IntegrityError), transaction.atomic():
                TipoIndicador.objects.filter(pk="PIB").update(**fields)
        with self.assertRaises(IntegrityError), transaction.atomic():
            TipoIndicador.objects.filter(pk="INFLACION").update(codigo_world_bank="NY.GDP.MKTP.CD")
