from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from countries.models import Moneda, Pais


class CountryIntegrityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.currency = Moneda.objects.create(codigo="USD", nombre="Dólar estadounidense")

    def country(self, **overrides):
        return Pais(
            codigo_iso="EC", nombre="Ecuador", moneda=self.currency,
            region=Pais.Region.ANDINA, latitud="-1.831200", longitud="-78.183400",
            poblacion=18_000_000, **overrides,
        )

    def test_multiple_countries_can_share_one_currency_and_deletion_is_protected(self):
        country = self.country()
        country.save()
        other = self.country()
        other.codigo_iso, other.nombre = "US", "Estados Unidos"
        other.save()
        self.assertEqual(self.currency.paises.count(), 2)
        with self.assertRaises(ProtectedError):
            self.currency.delete()

    def test_database_rejects_invalid_country_data(self):
        for field, value in [
            ("codigo_iso", "ec"), ("nombre", "   "), ("region", "OTRA"),
            ("latitud", "90.000001"), ("latitud", "-90.000001"),
            ("longitud", "180.000001"), ("longitud", "-180.000001"),
            ("poblacion", -1), ("moneda_id", "XXX"),
        ]:
            with self.subTest(field=field, value=value):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    country = self.country()
                    setattr(country, field, value)
                    country.save(force_insert=True)
                    # Las FK de PostgreSQL pueden ser diferidas hasta el commit.
                    from django.db import connection
                    connection.check_constraints()

    def test_model_validation_reports_invalid_coordinates_and_codes(self):
        country = self.country()
        country.latitud, country.longitud, country.codigo_iso = 91, -181, "ec"
        with self.assertRaises(ValidationError) as error:
            country.full_clean()
        self.assertTrue({"latitud", "longitud", "codigo_iso"} <= error.exception.message_dict.keys())

    def test_database_rejects_invalid_currency_and_duplicate_primary_keys(self):
        for code, name in [("usd", "Dólar"), ("US", "Dólar"), ("EUR", " "), ("USD", "Duplicado")]:
            with self.subTest(code=code):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Moneda.objects.create(codigo=code, nombre=name)
        self.country().save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.country().save(force_insert=True)
