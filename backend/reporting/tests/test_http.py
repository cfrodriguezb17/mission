"""Regresión de negociación PDF y errores JSON mediante HTTP y JWT reales."""
from io import BytesIO
import json
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase
from pypdf import PdfReader

from audit.models import LogActividad
from portfolios.models import Portafolio


class PDFHTTPTests(LiveServerTestCase):
    def test_pdf_accept_download_head_and_json_errors_over_http(self):
        owner = get_user_model().objects.create_user(
            email="pdf-http@example.com", nombre_completo="Prueba PDF HTTP",
            rol="ANALISTA", password="TemporalPDF!852q",
        )
        portfolio = Portafolio.objects.create(usuario=owner, nombre="Reporte por HTTP")
        path = f"/api/portafolios/{portfolio.pk}/export/pdf/"

        def request(path, *, data=None, token=None, method=None, accept="application/pdf"):
            headers = {"Accept": accept}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            if data is not None:
                headers["Content-Type"] = "application/json"
            req = Request(self.live_server_url + path, headers=headers, method=method,
                          data=json.dumps(data).encode() if data is not None else None)
            try:
                response = urlopen(req, timeout=10)
            except HTTPError as exc:
                response = exc
            with response:
                return response.status, response.headers, response.read()

        status, headers, body = request(path)
        self.assertEqual(status, 401)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(json.loads(body)["error"]["codigo"], "autenticacion")
        status, _, body = request("/api/auth/login/", data={
            "email": owner.email, "password": "TemporalPDF!852q",
        }, accept="application/json")
        self.assertEqual(status, 200)
        token = json.loads(body)["access"]
        status, headers, body = request(path, token=token)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/pdf")
        self.assertEqual(headers["Content-Disposition"], f'attachment; filename="portafolio-{portfolio.pk}.pdf"')
        self.assertEqual(headers["Cache-Control"], "private, no-store")
        self.assertTrue(body.startswith(b"%PDF-"))
        self.assertIn("Reporte por HTTP", PdfReader(BytesIO(body)).pages[0].extract_text())
        self.assertEqual(LogActividad.objects.filter(accion="EXPORT", usuario=owner).count(), 1)
        status, headers, body = request(path, token=token, method="HEAD")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/pdf")
        self.assertEqual(body, b"")
        status, headers, body = request("/api/portafolios/999999/export/pdf/", token=token)
        self.assertEqual(status, 404)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(json.loads(body)["error"]["codigo"], "no_encontrado")
        with patch("reporting.views.generar_pdf", side_effect=RuntimeError("diagnostico-privado")):
            status, headers, body = request(path, token=token)
        self.assertEqual(status, 500)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(json.loads(body)["error"]["codigo"], "error_interno")
        self.assertNotIn(b"diagnostico-privado", body)
