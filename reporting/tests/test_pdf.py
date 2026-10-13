from io import BytesIO
from unittest.mock import patch

from pypdf import PdfReader

from audit.models import LogActividad
from portfolios.models import Posicion
from portfolios.tests.base import PortfolioTestCase
from risk.models import IndiceRiesgo


class PDFTests(PortfolioTestCase):
    def url(self, portfolio=None):
        return f"/api/portafolios/{(portfolio or self.public).pk}/export/pdf/"

    def text(self, response):
        return "\n".join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages)

    def test_export_contains_positions_totals_risk_and_audit(self):
        Posicion.objects.create(portafolio=self.public, **self.position_data(notas="Nota visible"))
        IndiceRiesgo.objects.create(pais=self.co, score_economico=80, score_cambiario=80,
            score_estabilidad=80, indice_compuesto=80, version_formula="test",
            detalle_calculo={"datos_parciales": True, "contiene_simulaciones": True})
        response = self.api.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertIn("attachment", response["Content-Disposition"])
        text = self.text(response)
        for value in ["Compartido", "1,000.00 USD", "Colombia", "Nota visible", "BAJO", "datos incompletos", "simulados"]:
            self.assertIn(value, text)
        event = LogActividad.objects.get(accion="EXPORT")
        self.assertEqual(event.usuario, self.owner)
        self.assertEqual(event.detalle["version"], self.public.version)

    def test_viewer_can_export_public_but_not_another_users_private(self):
        self.api.force_authenticate(self.viewer)
        self.assertEqual(self.api.get(self.url()).status_code, 200)
        self.assertEqual(self.api.get(self.url(self.private)).status_code, 404)
        self.assertEqual(LogActividad.objects.filter(accion="EXPORT").count(), 1)

    def test_explicit_pdf_accept_returns_download(self):
        for accept in ("application/pdf", "*/*", "application/json"):
            with self.subTest(accept=accept):
                response = self.api.get(self.url(), HTTP_ACCEPT=accept)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "application/pdf")
                self.assertEqual(response["Cache-Control"], "private, no-store")
                self.assertIn("attachment", response["Content-Disposition"])
                self.assertIn("Compartido", self.text(response))

    def test_pdf_accept_preserves_json_errors_and_permissions(self):
        self.api.force_authenticate(None)
        unauthorized = self.api.get(self.url(), HTTP_ACCEPT="application/pdf")
        self.api.force_authenticate(self.viewer)
        hidden = self.api.get(self.url(self.private), HTTP_ACCEPT="application/pdf")
        unsupported_method = self.api.post(self.url(), {}, format="json", HTTP_ACCEPT="application/pdf")
        for response, status, code in ((unauthorized, 401, "autenticacion"),
                                       (hidden, 404, "no_encontrado"),
                                       (unsupported_method, 405, "metodo_no_permitido")):
            with self.subTest(status=status):
                self.assertEqual(response.status_code, status)
                self.assertEqual(response["Content-Type"], "application/json")
                self.assertEqual(response.json()["error"]["codigo"], code)
        self.assertFalse(LogActividad.objects.filter(accion="EXPORT").exists())

    def test_pdf_accept_metadata_and_unsupported_format(self):
        response = self.api.options(self.url(), HTTP_ACCEPT="application/pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("application/pdf", response.json()["renders"])
        response = self.api.get(self.url(), HTTP_ACCEPT="application/xml")
        self.assertEqual(response.status_code, 406)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json()["error"]["codigo"], "formato_no_admitido")

    def test_admin_can_export_private_and_deleted_portfolio_is_unavailable(self):
        self.api.force_authenticate(self.admin)
        self.assertEqual(self.api.get(self.url(self.private)).status_code, 200)
        self.public.activo = False
        self.public.save()
        self.assertEqual(self.api.get(self.url()).status_code, 404)

    def test_closed_positions_are_visible_but_not_in_active_total(self):
        from datetime import timedelta
        from django.utils import timezone
        Posicion.objects.create(portafolio=self.public, **self.position_data(
            fecha_salida=timezone.localdate() - timedelta(days=1), notas="Cerrada"))
        text = self.text(self.api.get(self.url()))
        self.assertIn("0.00 USD", text)
        self.assertIn("Cerrada", text)
        self.assertIn("1,000.00", text)

    def test_missing_risk_and_empty_portfolio_are_explicit(self):
        empty = self.text(self.api.get(self.url()))
        self.assertIn("Sin posiciones.", empty)
        Posicion.objects.create(portafolio=self.public, **self.position_data())
        text = self.text(self.api.get(self.url()))
        self.assertIn("Países sin índice: CO", text)
        self.assertIn("Sin datos", text)

    def test_long_text_and_many_rows_paginate_without_html_execution(self):
        self.public.nombre = "Portafolio <b>literal</b> & demostración"
        self.public.descripcion = "Descripción extensa " * 25
        self.public.save()
        Posicion.objects.bulk_create([Posicion(portafolio=self.public, **self.position_data(notas="Detalle " * 20)) for _ in range(60)])
        response = self.api.get(self.url())
        reader = PdfReader(BytesIO(response.content))
        self.assertGreater(len(reader.pages), 2)
        text = self.text(response)
        self.assertIn("<b>literal</b>", text)
        self.assertEqual(text.count("RENTA_FIJA"), 61)  # Distribución y 60 posiciones.

    def test_failed_generation_does_not_record_successful_export_or_expose_exception(self):
        with patch("reporting.views.generar_pdf", side_effect=RuntimeError("contraseña-secreta")):
            response = self.api.get(self.url(), HTTP_ACCEPT="application/pdf")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertNotIn("contraseña-secreta", str(response.content))
        self.assertFalse(LogActividad.objects.filter(accion="EXPORT").exists())

    def test_unauthenticated_export_is_rejected(self):
        self.api.force_authenticate(None)
        self.assertEqual(self.api.get(self.url()).status_code, 401)
