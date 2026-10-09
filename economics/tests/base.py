from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from economics.services import cargar_catalogo


class EconomicsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_countries", stdout=StringIO())
        cargar_catalogo()
