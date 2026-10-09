from datetime import timedelta
from io import StringIO
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import LiveServerTestCase
from django.utils import timezone

from portfolios.models import Portafolio, Posicion


class PortfolioHTTPTests(LiveServerTestCase):
    def setUp(self):
        call_command("seed_countries", stdout=StringIO())
        self.users = [get_user_model().objects.create_user(email=f"portfolio-http-{i}@example.com",
            nombre_completo="Prueba HTTP", rol=role, password="TemporalClave!842z")
            for i, role in enumerate(("ANALISTA", "ANALISTA", "VIEWER"))]

    def request(self, path, method="GET", data=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(self.live_server_url + path, method=method, headers=headers,
                          data=json.dumps(data).encode() if data is not None else None)
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, json.load(response) if response.status != 204 else None
        except HTTPError as response:
            return response.code, json.load(response)

    def test_shared_editing_positions_conflicts_and_viewer_permissions_with_jwt(self):
        self.assertEqual(self.request("/api/portafolios/")[0], 401)
        tokens = []
        for user in self.users:
            status, data = self.request("/api/auth/login/", "POST", {"email": user.email, "password": "TemporalClave!842z"})
            self.assertEqual(status, 200)
            tokens.append(data["access"])
        status, created = self.request("/api/portafolios/", "POST", {"nombre": "Colaborativo HTTP", "es_publico": True}, tokens[0])
        self.assertEqual(status, 201)
        path = f"/api/portafolios/{created['id']}/"
        self.assertEqual(self.request(path, "PUT", {"version": 1, "descripcion": "Cambio colega"}, tokens[1])[0], 200)
        self.assertEqual(self.request(path, "PUT", {"version": 1, "descripcion": "Viejo"}, tokens[0])[0], 409)
        status, position = self.request(path + "posiciones/", "POST", {"version": 2, "pais": "CO", "tipo_activo": "RENTA_FIJA",
            "monto_inversion_usd": "1000", "fecha_entrada": (timezone.localdate() - timedelta(days=2)).isoformat()}, tokens[1])
        self.assertEqual((status, position["version_portafolio"]), (201, 3))
        self.assertEqual(self.request(path, "PUT", {"version": 3, "nombre": "Lector"}, tokens[2])[0], 403)
        self.assertEqual(self.request(path, "DELETE", {"version": 3}, tokens[1])[0], 403)
        status, detail = self.request(path, token=tokens[2])
        self.assertEqual(status, 200)
        self.assertEqual(detail["resumen"]["total_invertido_usd"], "1000.00")
        self.assertEqual(self.request(path, "PUT", {"version": 3, "es_publico": False}, tokens[0])[0], 200)
        self.assertEqual(self.request(path, token=tokens[1])[0], 404)
        self.assertEqual(self.request(path, "DELETE", {"version": 4}, tokens[0])[0], 204)
        self.assertFalse(Portafolio.objects.get(pk=created["id"]).activo)
        self.assertEqual(Posicion.objects.count(), 1)
