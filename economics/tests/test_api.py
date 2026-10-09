from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from countries.models import Pais
from economics.models import IndicadorEconomico, TipoCambio

from .base import EconomicsTestCase


class EconomicAPITests(EconomicsTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = get_user_model().objects.create_user(email="economics@example.com", nombre_completo="Prueba")
        for year in (2024, 2025):
            for code in ("PIB", "INFLACION"):
                IndicadorEconomico.objects.create(pais_id="CO", tipo_id=code, anio=year, valor=100, fuente="WORLD_BANK")
        for day, rate in ((1, "0.0002"), (2, "0.00022"), (4, "0.00023")):
            TipoCambio.objects.create(moneda_origen_id="COP", fecha=date(2026, 1, day), tasa=rate, fuente="EXCHANGE_RATE")
        # Otro par no debe contaminar el cálculo del día anterior.
        TipoCambio.objects.create(moneda_origen_id="COP", moneda_destino_id="BRL", fecha=date(2026, 1, 3), tasa=1, fuente="MANUAL")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.indicators = reverse("economics:indicadores", args=["co"])
        self.quotes = reverse("economics:tipo-cambio", args=["CO"])
        self.sync = reverse("economics:sync-indicadores")

    def test_endpoints_require_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.indicators).status_code, 401)
        self.assertEqual(self.client.get(self.quotes).status_code, 401)
        self.assertEqual(self.client.post(self.sync, {}, format="json").status_code, 401)

    def test_indicator_filters_pagination_order_and_unit(self):
        response = self.client.get(self.indicators, {"tipo": " pib ", "anio": 2025, "page_size": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["unidad"], "USD")
        self.assertEqual(response.data["results"][0]["tipo"], "PIB")
        response = self.client.get(self.indicators, {"ordering": "anio,-tipo", "page_size": 2})
        self.assertEqual(response.data["results"][0]["anio"], 2024)
        self.assertIsNotNone(response.data["next"])

    def test_indicator_invalid_parameters_and_read_only(self):
        for params in ({"tipo": "X"}, {"anio": "abc"}, {"anio": 0}, {"ordering": "secret"}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get(self.indicators, params).status_code, 400)
        for method in ("post", "put", "delete"):
            self.assertEqual(getattr(self.client, method)(self.indicators).status_code, 405)

    def test_country_detail_includes_normalized_indicators(self):
        response = self.client.get(reverse("countries:detail", args=["CO"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["indicadores"]), 4)
        self.assertTrue(all("unidad" in item for item in response.data["indicadores"]))

    def test_unknown_and_inactive_country(self):
        for name in ("indicadores", "tipo-cambio"):
            self.assertEqual(self.client.get(reverse(f"economics:{name}", args=["ZZ"])).status_code, 404)
        Pais.objects.filter(pk="CO").update(activo=False)
        self.assertEqual(self.client.get(self.indicators).status_code, 404)
        self.assertEqual(self.client.get(self.quotes).status_code, 404)

    def test_variation_uses_calendar_yesterday_even_outside_requested_range(self):
        response = self.client.get(self.quotes, {"fecha_inicio": "2026-01-02", "fecha_fin": "2026-01-04", "ordering": "fecha"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["results"][0]["variacion_porcentual"], "10.000000")
        self.assertFalse(response.data["results"][0]["dato_anterior_faltante"])
        self.assertIsNone(response.data["results"][1]["variacion_porcentual"])
        self.assertTrue(response.data["results"][1]["dato_anterior_faltante"])

    def test_quote_invalid_ranges_and_empty_history(self):
        for params in ({"fecha_inicio": "abc"}, {"fecha_fin": "2026-02-30"},
                       {"fecha_inicio": "2026-01-04", "fecha_fin": "2026-01-01"}, {"ordering": "valor"}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get(self.quotes, params).status_code, 400)
        self.assertEqual(self.client.get(self.quotes, {"fecha_inicio": "2027-01-01"}).data["count"], 0)

    def test_variation_supports_extremes_of_valid_stored_decimal_precision(self):
        TipoCambio.objects.filter(moneda_origen_id="COP", moneda_destino_id="USD", fecha=date(2026, 1, 1)).update(tasa=Decimal("0.000000000001"))
        TipoCambio.objects.filter(moneda_origen_id="COP", moneda_destino_id="USD", fecha=date(2026, 1, 2)).update(tasa=Decimal("999999999999.999999999999"))
        response = self.client.get(self.quotes, {"fecha_inicio": "2026-01-02", "fecha_fin": "2026-01-02"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["variacion_porcentual"], "99999999999999999999999800.000000")

    def test_usd_identity_is_paginated_and_never_persisted(self):
        response = self.client.get(reverse("economics:tipo-cambio", args=["EC"]), {
            "fecha_inicio": "2026-01-01", "fecha_fin": "2026-01-04", "page_size": 2, "ordering": "fecha",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 4)
        self.assertEqual(response.data["results"][0]["fecha"], "2026-01-01")
        self.assertEqual(response.data["results"][0]["tasa"], "1.000000000000")
        self.assertIsNotNone(response.data["next"])
        self.assertFalse(TipoCambio.objects.filter(moneda_origen_id="USD", moneda_destino_id="USD").exists())
        self.assertEqual(self.client.get(reverse("economics:tipo-cambio", args=["EC"]), {
            "fecha_inicio": "2020-01-01", "fecha_fin": "2026-01-01",
        }).status_code, 400)

    def test_list_queries_do_not_grow_with_number_of_results(self):
        for url in (self.indicators, self.quotes):
            with self.assertNumQueries(4):  # país, conteo, datos y un INSERT de auditoría
                self.assertEqual(self.client.get(url).status_code, 200)

    @patch("economics.views.sincronizar_indicadores")
    def test_sync_requires_business_admin_even_for_django_superuser(self, sync):
        for role in ("VIEWER", "ANALISTA"):
            self.user.rol = role
            self.user.is_superuser = True
            self.user.save()
            self.assertEqual(self.client.post(self.sync, {}, format="json").status_code, 403)
        sync.assert_not_called()
        self.user.rol = "ADMIN"
        self.user.save()
        sync.return_value = {"errores": [], "paises_procesados": ["CO"]}
        self.assertEqual(self.client.post(self.sync, {"paises": ["CO"]}, format="json").status_code, 200)
        self.assertEqual(sync.call_args.kwargs["paises"], ["CO"])
        self.assertEqual(sync.call_args.kwargs["presupuesto"], 25)

    @patch("economics.views.sincronizar_indicadores")
    def test_sync_validation_and_provider_failure(self, sync):
        self.user.rol = "ADMIN"
        self.user.save()
        for data in ({"paises": []}, {"paises": ["US"]}, {"anio_inicio": 2025, "anio_fin": 2024},
                     {"anio_inicio": 2000, "anio_fin": 2025}, {"anio_fin": 9999}, {"url": "https://example.org"}):
            with self.subTest(data=data):
                self.assertEqual(self.client.post(self.sync, data, format="json").status_code, 400)
        sync.assert_not_called()
        sync.return_value = {"errores": [{"pais": "CO", "mensaje": "No disponible"}], "paises_procesados": []}
        self.assertEqual(self.client.post(self.sync, {}, format="json").status_code, 503)
