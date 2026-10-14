from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from countries.models import Pais
from portfolios.models import Portafolio


class PortfolioTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_countries", stdout=StringIO())
        cls.owner = get_user_model().objects.create_user(email="portfolio-owner@example.com", nombre_completo="Propietario", rol="ANALISTA")
        cls.other = get_user_model().objects.create_user(email="portfolio-other@example.com", nombre_completo="Colaborador", rol="ANALISTA")
        cls.viewer = get_user_model().objects.create_user(email="portfolio-viewer@example.com", nombre_completo="Lector", rol="VIEWER")
        cls.admin = get_user_model().objects.create_user(email="portfolio-admin@example.com", nombre_completo="Administrador", rol="ADMIN")
        cls.public = Portafolio.objects.create(usuario=cls.owner, nombre="Compartido", es_publico=True)
        cls.private = Portafolio.objects.create(usuario=cls.owner, nombre="Privado")
        cls.co = Pais.objects.get(pk="CO")

    def setUp(self):
        self.api = APIClient()
        self.api.force_authenticate(self.owner)

    def position_data(self, **overrides):
        return {"pais": self.co, "tipo_activo": "RENTA_FIJA", "monto_inversion_usd": Decimal("1000"),
                "fecha_entrada": timezone.localdate() - timedelta(days=2), **overrides}

    def api_position(self, **overrides):
        data = self.position_data(**overrides)
        data["pais"] = data["pais"].pk
        data["fecha_entrada"] = data["fecha_entrada"].isoformat()
        data["monto_inversion_usd"] = str(data["monto_inversion_usd"])
        return {"version": self.public.version, **data}
