from datetime import datetime
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from countries.models import Pais
from risk.models import IndiceRiesgo


class RiskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_countries", stdout=StringIO())
        cls.user = get_user_model().objects.create_user(email="risk@example.com", nombre_completo="Riesgo")
        cls.old = cls.create_index("CO", "2026-01-01T12:00:00+00:00", 99)
        cls.latest = cls.create_index("CO", "2026-01-02T23:59:59+00:00", 50)
        cls.brazil = cls.create_index("BR", "2026-01-02T12:00:00+00:00", 75)

    @staticmethod
    def create_index(country, timestamp, score):
        # Fixtures de persistencia/API, no resultados de una fórmula de negocio.
        return IndiceRiesgo.objects.create(pais_id=country, fecha_calculo=datetime.fromisoformat(timestamp),
            score_economico=score, score_cambiario=score, score_estabilidad=score,
            indice_compuesto=score, version_formula="fixture-test",
            detalle_calculo={"entradas": [{"valor": "9.2", "fuente": "MANUAL"}], "faltantes": ["DEUDA_PIB"]})

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.ranking = reverse("risk:ranking")
        self.history = reverse("risk:historico", args=["co"])
        self.detail = reverse("risk:detalle", args=["CO"])

    def test_model_constraints_apply_to_direct_database_writes(self):
        for field in ("score_economico", "score_cambiario", "score_estabilidad", "indice_compuesto"):
            for invalid in (Decimal("-0.01"), Decimal("100.01")):
                with self.subTest(field=field, invalid=invalid):
                    with self.assertRaises(IntegrityError), transaction.atomic():
                        IndiceRiesgo.objects.filter(pk=self.latest.pk).update(**{field: invalid})
        with self.assertRaises(IntegrityError), transaction.atomic():
            IndiceRiesgo.objects.filter(pk=self.latest.pk).update(version_formula="   ")

    def test_history_protects_country_and_does_not_depend_on_current_inputs(self):
        with self.assertRaises(ProtectedError):
            Pais.objects.get(pk="CO").delete()
        self.latest.refresh_from_db()
        self.assertEqual(self.latest.detalle_calculo["entradas"][0]["valor"], "9.2")
        self.assertEqual(self.latest.detalle_calculo["faltantes"], ["DEUDA_PIB"])

    def test_levels_at_boundaries(self):
        for score, level, color in ((0, "CRITICO", "#ef4444"), (Decimal("24.99"), "CRITICO", "#ef4444"),
            (25, "ALTO", "#f97316"), (Decimal("49.99"), "ALTO", "#f97316"),
            (50, "MODERADO", "#eab308"), (Decimal("74.99"), "MODERADO", "#eab308"),
            (75, "BAJO", "#22c55e"), (100, "BAJO", "#22c55e")):
            with self.subTest(score=score):
                index = IndiceRiesgo(indice_compuesto=score)
                self.assertEqual((index.nivel_riesgo, index.color), (level, color))

    def test_all_endpoints_require_authentication_and_are_read_only(self):
        for url in (self.ranking, self.history, self.detail):
            self.client.force_authenticate(None)
            self.assertEqual(self.client.get(url).status_code, 401)
            self.client.force_authenticate(self.user)
            for method in ("post", "put", "patch", "delete"):
                self.assertEqual(getattr(self.client, method)(url).status_code, 405)

    def test_all_roles_can_read(self):
        for role in ("ADMIN", "ANALISTA", "VIEWER"):
            self.user.rol = role
            self.user.save()
            for url in (self.ranking, self.history, self.detail):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_ranking_uses_latest_not_highest_score_and_supports_pagination(self):
        data = self.client.get(self.ranking, {"page_size": 1}).data
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["results"][0]["pais"], "BR")
        self.assertIsNotNone(data["next"])
        results = self.client.get(self.ranking).data["results"]
        self.assertEqual(results[1]["id"], self.latest.pk)
        self.assertEqual(results[1]["indice_compuesto"], "50.00")

    def test_same_timestamp_is_resolved_by_latest_id(self):
        last = self.create_index("CO", self.latest.fecha_calculo.isoformat(), 25)
        rows = self.client.get(self.ranking).data["results"]
        self.assertEqual([row["id"] for row in rows if row["pais"] == "CO"], [last.pk])

    def test_history_date_range_is_inclusive_and_latest_is_unfiltered(self):
        data = self.client.get(self.history, {"fecha_inicio": "2026-01-02", "fecha_fin": "2026-01-02"}).data
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["id"], self.latest.pk)
        data = self.client.get(self.detail, {"fecha_fin": "2026-01-01"}).data
        self.assertEqual(data["ultimo"]["id"], self.latest.pk)
        self.assertEqual(data["historico"]["results"][0]["id"], self.old.pk)

    def test_detail_includes_evidence_and_paginated_history(self):
        response = self.client.get(self.detail, {"page_size": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["ultimo"]["detalle_calculo"], self.latest.detalle_calculo)
        self.assertEqual(response.data["historico"]["count"], 2)
        self.assertIsNotNone(response.data["historico"]["next"])

    def test_invalid_ranges_and_ordering(self):
        for params in ({"fecha_inicio": "abc"}, {"fecha_fin": "2026-02-30"},
                       {"fecha_inicio": "2026-01-03", "fecha_fin": "2026-01-01"},
                       {"ordering": "password"}, {"ordering": "--id"}, {"ordering": ""}):
            for url in (self.history, self.detail):
                with self.subTest(url=url, params=params):
                    self.assertEqual(self.client.get(url, params).status_code, 400)

    def test_unknown_inactive_and_country_without_calculations(self):
        for name in ("detalle", "historico"):
            self.assertEqual(self.client.get(reverse(f"risk:{name}", args=["ZZ"])).status_code, 404)
        data = self.client.get(reverse("risk:detalle", args=["EC"])).data
        self.assertIsNone(data["ultimo"])
        self.assertEqual(data["historico"]["count"], 0)
        Pais.objects.filter(pk="CO").update(activo=False)
        self.assertEqual(self.client.get(self.history).status_code, 404)
        self.assertEqual(self.client.get(self.detail).status_code, 404)
        self.assertEqual(self.client.get(self.ranking).data["count"], 1)

    def test_ordering_and_query_count(self):
        with self.assertNumQueries(2):
            response = self.client.get(self.ranking, {"ordering": "indice_compuesto,pais"})
            self.assertEqual(response.data["results"][0]["pais"], "CO")
        with self.assertNumQueries(3):
            response = self.client.get(self.history, {"ordering": "fecha_calculo"})
            self.assertEqual(response.data["results"][0]["id"], self.old.pk)
