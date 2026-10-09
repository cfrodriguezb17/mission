from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from rest_framework.test import APITestCase

from countries.models import Pais


class CountryAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_countries", stdout=StringIO())
        cls.user = get_user_model().objects.create_user(
            email="viewer@example.com", nombre_completo="Analista de prueba",
            password="PruebaSegura!842z",
        )

    def setUp(self):
        # Obtener el JWT a través del endpoint real de login del backend.
        login = self.client.post(reverse("accounts:login"), {
            "email": self.user.email, "password": "PruebaSegura!842z",
        }, format="json")
        self.assertEqual(login.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        self.list_url = reverse("countries:list")

    def test_list_and_detail_require_authentication(self):
        self.client.credentials()
        for url in [self.list_url, reverse("countries:detail", args=["CO"])]:
            self.assertEqual(self.client.get(url).status_code, 401)

    def test_list_is_paginated_and_exposes_related_currency(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"count", "next", "previous", "results"})
        self.assertEqual(response.data["count"], 10)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertIsNone(response.data["next"])
        country = next(item for item in response.data["results"] if item["codigo_iso"] == "CO")
        self.assertEqual(country["moneda_codigo"], "COP")
        self.assertEqual(country["moneda_nombre"], "Peso colombiano")
        self.assertNotIn("moneda", country)

    def test_region_search_and_ordering_can_be_combined(self):
        response = self.client.get(self.list_url, {
            "region": " andina ", "search": "COP", "ordering": "-poblacion",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["codigo_iso"] for item in response.data["results"]], ["CO"])
        response = self.client.get(self.list_url, {"region": "ANDINA", "ordering": "-poblacion"})
        self.assertEqual([item["codigo_iso"] for item in response.data["results"]], ["CO", "PE", "EC"])
        response = self.client.get(self.list_url, {"search": "Colom"})
        self.assertEqual(response.data["count"], 1)

    def test_invalid_region_returns_descriptive_error(self):
        response = self.client.get(self.list_url, {"region": "EUROPA"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Región inválida", str(response.data["region"]))

    def test_custom_page_size_and_navigation(self):
        response = self.client.get(self.list_url, {"page_size": 3, "ordering": "codigo_iso"})
        self.assertEqual(len(response.data["results"]), 3)
        self.assertIsNotNone(response.data["next"])
        second = self.client.get(self.list_url, {"page_size": 3, "page": 2, "ordering": "codigo_iso"})
        self.assertEqual(len(second.data["results"]), 3)
        self.assertTrue(set(item["codigo_iso"] for item in response.data["results"]).isdisjoint(
            item["codigo_iso"] for item in second.data["results"]
        ))
        self.assertEqual(self.client.get(self.list_url, {"page": 99}).status_code, 404)

    def test_page_size_is_capped_at_one_hundred(self):
        self.assertEqual(self.client.get(self.list_url, {"page_size": 1000}).data["count"], 10)
        # Verificar el límite efectivo, no solo un dataset menor al límite.
        from common.pagination import StandardPagination
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory
        request = Request(APIRequestFactory().get("/", {"page_size": 1000}))
        self.assertEqual(StandardPagination().get_page_size(request), 100)

    def test_detail_accepts_iso_case_and_returns_404_for_unknown_or_inactive_country(self):
        response = self.client.get(reverse("countries:detail", args=["co"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["codigo_iso"], "CO")
        self.assertEqual(response.data["latitud"], "4.570900")
        self.assertEqual(self.client.get(reverse("countries:detail", args=["ZZ"])).status_code, 404)
        Pais.objects.filter(pk="CO").update(activo=False)
        self.assertEqual(self.client.get(reverse("countries:detail", args=["CO"])).status_code, 404)
        self.assertEqual(self.client.get(self.list_url).data["count"], 9)

    def test_all_roles_can_read_but_api_does_not_allow_writes(self):
        for role in get_user_model().Rol.values:
            with self.subTest(role=role):
                self.user.rol = role
                self.user.save(update_fields=["rol"])
                self.assertEqual(self.client.get(self.list_url).status_code, 200)
                self.assertEqual(self.client.post(self.list_url, {}, format="json").status_code, 405)
                for method in ["put", "patch", "delete"]:
                    response = getattr(self.client, method)(reverse("countries:detail", args=["CO"]))
                    self.assertEqual(response.status_code, 405)

    def test_list_uses_one_join_for_currencies(self):
        self.client.force_authenticate(user=self.user)
        # Un conteo para paginación y una consulta con JOIN; no una por país.
        with self.assertNumQueries(2):
            response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
