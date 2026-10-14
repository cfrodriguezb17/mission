from io import StringIO
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import LiveServerTestCase

from alerts.models import Alerta


class AlertsHTTPTests(LiveServerTestCase):
    def setUp(self):
        call_command("seed_countries", stdout=StringIO())
        self.users = [get_user_model().objects.create_user(email=f"alert-http-{i}@example.com",
            nombre_completo="Prueba HTTP", password="TemporalClave!842z") for i in range(2)]
        self.alert = Alerta.objects.create(pais_id="CO", tipo_alerta="RIESGO", severidad="CRITICAL", titulo="Global", mensaje="Test")
        self.private = Alerta.objects.create(pais_id="CO", usuario=self.users[0], tipo_alerta="INDICADOR",
            severidad="INFO", titulo="Privada", mensaje="Test")

    def request(self, path, method="GET", data=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(self.live_server_url + path, method=method, headers=headers,
                          data=json.dumps(data).encode() if data is not None else None)
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, json.load(response)
        except HTTPError as response:
            return response.code, json.load(response)

    def token(self, user):
        status, tokens = self.request("/api/auth/login/", method="POST", data={"email": user.email, "password": "TemporalClave!842z"})
        self.assertEqual(status, 200)
        return tokens["access"]

    def test_jwt_private_visibility_and_independent_reads_over_http(self):
        self.assertEqual(self.request("/api/alertas/")[0], 401)
        tokens = [self.token(user) for user in self.users]
        status, data = self.request("/api/alertas/", token=tokens[0])
        self.assertEqual((status, data["count"]), (200, 2))
        status, data = self.request(f"/api/alertas/{self.alert.pk}/leer/", method="PUT", data={}, token=tokens[0])
        self.assertEqual(status, 200)
        self.assertTrue(data["leida"])
        status, data = self.request("/api/alertas/?leida=false", token=tokens[1])
        self.assertEqual((status, data["count"]), (200, 1))
        self.assertEqual(self.request(f"/api/alertas/{self.private.pk}/leer/", method="PUT", data={}, token=tokens[1])[0], 404)
        status, data = self.request("/api/alertas/leer-todas/", method="PUT", data={}, token=tokens[1])
        self.assertEqual((status, data["marcadas"]), (200, 1))
        self.assertEqual(self.request("/api/alertas/resumen/", token=tokens[1])[1]["no_leidas"], 0)
