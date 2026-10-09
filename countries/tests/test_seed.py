from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from countries.models import Moneda, Pais


class CountrySeedTests(TestCase):
    def seed(self, *args):
        call_command("seed_countries", *args, stdout=StringIO())

    def test_seed_creates_complete_ten_country_dataset(self):
        self.seed()
        self.assertEqual(set(Pais.objects.values_list("pk", flat=True)), {
            "CO", "BR", "MX", "AR", "CL", "PE", "EC", "UY", "PY", "PA",
        })
        self.assertEqual(Moneda.objects.count(), 10)
        for country in Pais.objects.all():
            country.full_clean()
            self.assertTrue(country.bandera_url.startswith("https://"))
        self.assertEqual(Pais.objects.get(pk="EC").moneda_id, "USD")
        self.assertEqual(Pais.objects.get(pk="PA").moneda_id, "PAB")

    def test_repeated_seed_preserves_existing_edits(self):
        self.seed()
        Pais.objects.filter(pk="CO").update(nombre="Nombre editado", activo=False)
        Moneda.objects.filter(pk="COP").update(nombre="Moneda editada")
        self.seed()
        self.assertEqual(Pais.objects.count(), 10)
        self.assertEqual(Moneda.objects.count(), 10)
        country = Pais.objects.select_related("moneda").get(pk="CO")
        self.assertEqual(country.nombre, "Nombre editado")
        self.assertFalse(country.activo)
        self.assertEqual(country.moneda.nombre, "Moneda editada")

    def test_explicit_update_restores_seed_values(self):
        self.seed()
        Pais.objects.filter(pk="CO").update(nombre="Nombre editado", activo=False)
        self.seed("--update")
        country = Pais.objects.get(pk="CO")
        self.assertEqual(country.nombre, "Colombia")
        self.assertTrue(country.activo)
