from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient


class SharedAPIContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_countries", stdout=StringIO())
        cls.user = get_user_model().objects.create_user(email="common@example.com", nombre_completo="Pruebas compartidas", rol="ADMIN")

    def setUp(self):
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.lists = [
            ("/api/paises/", "codigo_iso"),
            ("/api/paises/CO/indicadores/", "id"),
            ("/api/paises/CO/tipo-cambio/", "fecha"),
            ("/api/paises/EC/tipo-cambio/", "fecha"),
            ("/api/riesgo/", "id"),
            ("/api/riesgo/CO/historico/", "id"),
            ("/api/alertas/", "id"),
            ("/api/portafolios/", "id"),
        ]

    def test_invalid_ordering_is_rejected_consistently_in_every_list(self):
        for path, field in self.lists:
            for ordering in ("", " ", "password", "--" + field, field + ",password", field + ",", "," + field):
                with self.subTest(path=path, ordering=ordering):
                    response = self.api.get(path, {"ordering": ordering})
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(str(response.data["ordering"]), "Campos de ordenamiento inválidos.")

    def test_valid_ordering_and_defaults_work_in_every_list(self):
        for path, field in self.lists:
            for params in ({}, {"ordering": field}, {"ordering": f" {field}, -{field} "}):
                with self.subTest(path=path, params=params):
                    response = self.api.get(path, params)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("results", response.data)
        ascending = self.api.get("/api/paises/EC/tipo-cambio/", {"ordering": "fecha"}).data["results"]
        descending = self.api.get("/api/paises/EC/tipo-cambio/", {"ordering": "-fecha"}).data["results"]
        self.assertLess(ascending[0]["fecha"], descending[0]["fecha"])

    def test_date_ranges_share_validation_without_rejecting_pagination_params(self):
        for path in ("/api/paises/CO/tipo-cambio/", "/api/paises/EC/tipo-cambio/", "/api/riesgo/CO/historico/"):
            with self.subTest(path=path):
                response = self.api.get(path, {"fecha_inicio": "2026-01-02", "fecha_fin": "2026-01-01"})
                self.assertEqual(response.status_code, 400)
                self.assertIn("fecha_fin", response.data)
                self.assertEqual(self.api.get(path, {"fecha_inicio": "2026-02-30"}).status_code, 400)
                self.assertEqual(self.api.get(path, {"fecha_inicio": "2026-01-01", "fecha_fin": "2026-01-02", "page_size": 1}).status_code, 200)

    def test_unknown_body_fields_are_rejected_before_business_operations(self):
        for path in ("/api/paises/sync-indicadores/", "/api/riesgo/calcular/", "/api/portafolios/"):
            with self.subTest(path=path):
                response = self.api.post(path, {"nombre": "Ejemplo", "url": "https://example.com"}, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn("url", response.data)
