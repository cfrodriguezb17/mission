from django.test import SimpleTestCase
from rest_framework.test import APIClient


class DocumentationTests(SimpleTestCase):
    def test_public_documentation_is_accessible_and_includes_every_new_endpoint(self):
        response = APIClient().get("/api/docs/")
        self.assertEqual(response.status_code, 200)
        text = response.data["contenido"]
        for endpoint in ("/dashboard/resumen/", "/dashboard/mapa/", "/dashboard/tendencias/", "/portafolios/{id}/export/pdf/",
                         "/portafolios/validar-nombre/"):
            self.assertIn(endpoint, text)
