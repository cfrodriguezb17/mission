from io import StringIO
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import DatabaseError
from django.test import LiveServerTestCase

class RiskHTTPTests(LiveServerTestCase):
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

    def test_calculate_ranking_and_history_over_http(self):
        self.assertEqual(self.request("/api/riesgo/")[0], 401)
        token = self.login()
        status, data = self.request("/api/riesgo/calcular/", {"paises": ["CO", "EC"]}, token=token)
        self.assertEqual(status, 200)
        self.assertEqual(len(data["calculados"]), 2)
        status, data = self.request("/api/riesgo/?page_size=1", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(data["count"], 2)
        self.assertIsNotNone(data["next"])
        status, data = self.request("/api/riesgo/EC/", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(data["ultimo"]["score_cambiario"], "100.00")
        self.assertTrue(data["ultimo"]["detalle_calculo"]["cambiario"]["no_aplica"])
        self.assertEqual(data["historico"]["count"], 1)
        status, data = self.request("/api/riesgo/CO/historico/?fecha_inicio=invalid", token=token)
        self.assertEqual(status, 400)

    def test_failed_recalculation_over_http_has_safe_503_envelope(self):
        with patch("risk.services.calcular_pais", side_effect=DatabaseError("diagnostico-privado")):
            status, data = self.request("/api/riesgo/calcular/", {"paises": ["CO"]}, token=self.login())
        self.assertEqual(status, 503)
        self.assertEqual(data["error"]["codigo"], "servicio_no_disponible")
        self.assertEqual(data["error"]["detalles"]["errores"], data["errores"])
        self.assertEqual(data["calculados"], [])
        self.assertNotIn("diagnostico-privado", json.dumps(data))
