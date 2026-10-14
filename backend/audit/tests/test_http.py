import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase

from audit.models import LogActividad


class AuditHTTPTests(LiveServerTestCase):
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

    def test_jwt_login_create_and_read_persist_audit_over_real_http(self):
        user = get_user_model().objects.create_user(email="audit-http@example.com", nombre_completo="HTTP",
                                                   password="TemporalClave!842z", rol="ANALISTA")
        self.assertEqual(self.request("/api/portafolios/")[0], 401)
        status, tokens = self.request("/api/auth/login/", {"email": user.email, "password": "TemporalClave!842z"})
        self.assertEqual(status, 200)
        status, portfolio = self.request("/api/portafolios/", {"nombre": "Prueba HTTP"}, tokens["access"])
        self.assertEqual(status, 201)
        self.assertEqual(self.request(f"/api/portafolios/{portfolio['id']}/", token=tokens["access"])[0], 200)
        events = LogActividad.objects.order_by("id")
        self.assertEqual(list(events.values_list("accion", flat=True)), ["LOGIN", "CREAR", "CONSULTAR"])
        self.assertTrue(all(e.usuario_id == user.pk and e.ip_address == "127.0.0.1" for e in events))
        self.assertNotIn(tokens["access"], str(list(events.values())))
        self.assertNotIn("TemporalClave!842z", str(list(events.values())))
