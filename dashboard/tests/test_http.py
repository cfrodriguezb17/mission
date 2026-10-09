import json
from io import BytesIO, StringIO
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.core.management import call_command
from django.test import LiveServerTestCase
from pypdf import PdfReader

from audit.models import LogActividad


class DeliveryHTTPTests(LiveServerTestCase):
    def request(self, path, *, token=None, data=None, method=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(self.live_server_url + path, headers=headers, method=method,
                          data=json.dumps(data).encode() if data is not None else None)
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            content = response.read()
            return response.status, (content if response.headers.get_content_type() == "application/pdf"
                                     else json.loads(content))

    def test_seed_jwt_dashboard_export_roles_and_conflicts_over_real_http(self):
        call_command("seed_data", stdout=StringIO())
        tokens = {}
        for role in ("admin", "analista", "viewer"):
            status, result = self.request("/api/auth/login/", data={"email": f"{role}@datapulse.com", "password": "DataPulse2026!"})
            self.assertEqual(status, 200)
            tokens[role] = result["access"]
        status, summary = self.request("/api/dashboard/resumen/", token=tokens["analista"])
        self.assertEqual(status, 200)
        self.assertEqual(summary["portafolios_usuario"], 2)
        self.assertEqual(summary["paises_con_riesgo"], 10)
        self.assertEqual(summary["paises_con_datos_parciales"], 0)
        self.assertEqual(self.request("/api/dashboard/mapa/", token=tokens["viewer"])[1]["count"], 10)
        self.assertEqual(self.request("/api/dashboard/tendencias/?tipo=PIB&paises=CO,BR,MX", token=tokens["viewer"])[1]["count"], 3)
        _, portfolios = self.request("/api/portafolios/", token=tokens["analista"])
        public = next(row for row in portfolios["results"] if row["es_publico"])
        private = next(row for row in portfolios["results"] if not row["es_publico"])
        status, pdf = self.request(f"/api/portafolios/{public['id']}/export/pdf/", token=tokens["viewer"])
        self.assertEqual(status, 200)
        text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
        self.assertIn("250,000.00 USD", text)
        self.assertIn("simulados", text)
        self.assertEqual(self.request(f"/api/portafolios/{private['id']}/export/pdf/", token=tokens["viewer"])[0], 404)
        self.assertEqual(self.request("/api/portafolios/", token=tokens["viewer"], data={"nombre": "No permitido"})[0], 403)
        path = f"/api/portafolios/{public['id']}/"
        payload = {"version": public["version"], "descripcion": "Actualizado por HTTP"}
        self.assertEqual(self.request(path, token=tokens["analista"], data=payload, method="PUT")[0], 200)
        status, conflict = self.request(path, token=tokens["admin"], data=payload, method="PUT")
        self.assertEqual(status, 409)
        self.assertEqual(conflict["error"]["codigo"], "conflicto")
        self.assertTrue(LogActividad.objects.filter(accion="EXPORT", usuario__rol="VIEWER").exists())
