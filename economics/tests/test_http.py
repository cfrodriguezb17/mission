"""Verificación por sockets HTTP reales sobre PostgreSQL de pruebas."""
import json
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import LiveServerTestCase


class EconomicsHTTPTests(LiveServerTestCase):
    def setUp(self):
        call_command("seed_economics", stdout=StringIO())
        get_user_model().objects.create_user(email="http-economics@example.com", nombre_completo="Prueba HTTP",
                                            password="TemporalClave!842z", rol="ADMIN")

    def request(self, path, data=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(self.live_server_url + path, headers=headers,
                          data=json.dumps(data).encode() if data is not None else None)
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, json.load(response)
        except HTTPError as response:
            return response.code, json.load(response)

    def login(self):
        status, tokens = self.request("/api/auth/login/", {"email": "http-economics@example.com", "password": "TemporalClave!842z"})
        self.assertEqual(status, 200)
        return tokens["access"]

    def test_jwt_seeded_indicators_quotes_identity_and_detail_over_http(self):
        self.assertEqual(self.request("/api/paises/CO/indicadores/")[0], 401)
        token = self.login()
        status, data = self.request("/api/paises/CO/indicadores/?tipo=PIB&page_size=2", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(data["count"], 5)
        self.assertEqual(len(data["results"]), 2)
        self.assertTrue(data["results"][0]["es_simulado"])
        status, data = self.request("/api/paises/CO/tipo-cambio/?ordering=fecha", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(data["count"], 30)
        self.assertIsNone(data["results"][0]["variacion_porcentual"])
        self.assertIsNotNone(data["results"][1]["variacion_porcentual"])
        status, data = self.request("/api/paises/EC/tipo-cambio/", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(data["results"][0]["fuente"], "IDENTIDAD")
        status, data = self.request("/api/paises/CO/", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(len(data["indicadores"]), 30)
        self.assertEqual(self.request("/api/paises/CO/indicadores/?anio=invalid", token=token)[0], 400)

    @patch("integrations.world_bank.WorldBankClient.indicadores")
    def test_admin_sync_over_http_persists_provider_data(self, provider):
        provider.return_value = [{"codigo_world_bank": "NY.GDP.MKTP.CD", "anio": 2025, "valor": Decimal("777")}]
        token = self.login()
        status, data = self.request("/api/paises/sync-indicadores/", {
            "paises": ["CO"], "anio_inicio": 2025, "anio_fin": 2025,
        }, token=token)
        self.assertEqual(status, 200)
        self.assertEqual(data["actualizados"], 1)
        status, data = self.request("/api/paises/CO/indicadores/?tipo=PIB&anio=2025", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(data["results"][0]["valor"], "777.000000")
        self.assertFalse(data["results"][0]["es_simulado"])
