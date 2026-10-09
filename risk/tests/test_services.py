from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import StringIO
import json
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from backend.workflows import actualizar_y_recalcular, sincronizar_y_recalcular
from economics.models import IndicadorEconomico, TipoCambio
from risk.models import IndiceRiesgo
from risk.services import calcular_pais, recalcular_riesgos


class RiskServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_countries", stdout=StringIO())
        cls.now = datetime(2026, 1, 31, 12, tzinfo=timezone.utc)
        for code, value in {"PIB_PERCAPITA": 12000, "INFLACION": 11, "DESEMPLEO": 11,
                            "DEUDA_PIB": 40, "BALANZA_COMERCIAL": -1, "PIB": 103}.items():
            IndicadorEconomico.objects.create(pais_id="CO", tipo_id=code, valor=value,
                anio=2025, fuente="MANUAL", es_simulado=True)
        IndicadorEconomico.objects.create(pais_id="CO", tipo_id="PIB", valor=100, anio=2024, fuente="WORLD_BANK")
        for offset in range(31):
            TipoCambio.objects.create(moneda_origen_id="COP", tasa=Decimal(100) - Decimal(offset) * Decimal("0.4"),
                fecha=cls.now.date() - timedelta(days=30 - offset), fuente="MANUAL")

    @patch("risk.services.timezone.now")
    def test_persisted_formula_and_snapshot_survive_edits(self, now):
        now.return_value = self.now
        index = calcular_pais("CO")
        self.assertEqual(index.indice_compuesto, Decimal("69.00"))
        self.assertEqual(index.version_formula, "irpc-v1")
        self.assertFalse(index.detalle_calculo["datos_parciales"])
        self.assertTrue(index.detalle_calculo["contiene_simulaciones"])
        self.assertEqual(len(index.detalle_calculo["cotizaciones"]), 31)
        original = index.detalle_calculo
        IndicadorEconomico.objects.filter(pais_id="CO", tipo_id="INFLACION").update(valor=99)
        TipoCambio.objects.filter(moneda_origen_id="COP").update(tasa=1)
        index.refresh_from_db()
        self.assertEqual(index.detalle_calculo, original)
        second = calcular_pais("CO")
        self.assertNotEqual(second.pk, index.pk)
        self.assertEqual(second.fecha_calculo, index.fecha_calculo)
        self.assertNotEqual(second.indice_compuesto, index.indice_compuesto)

    @patch("risk.services.timezone.now")
    def test_latest_per_indicator_no_future_year_and_no_skipped_gdp_year(self, now):
        now.return_value = self.now
        IndicadorEconomico.objects.create(pais_id="CO", tipo_id="INFLACION", valor=99, anio=2026, fuente="MANUAL")
        IndicadorEconomico.objects.filter(pais_id="CO", tipo_id="PIB", anio=2024).update(anio=2023)
        index = calcular_pais("CO")
        self.assertEqual(index.detalle_calculo["indicadores"]["INFLACION"]["anio"], 2025)
        self.assertIsNone(index.detalle_calculo["crecimiento_pib"])
        self.assertIn("CRECIMIENTO_PIB", index.detalle_calculo["missing_indicators"])

    @patch("risk.services.timezone.now")
    def test_missing_and_identity_can_be_persisted(self, now):
        now.return_value = self.now
        for country in ("BR", "EC"):
            index = calcular_pais(country)
            self.assertEqual(index.indice_compuesto, 100)
            self.assertTrue(index.detalle_calculo["datos_parciales"])
        self.assertEqual(index.score_cambiario, 100)
        self.assertTrue(index.detalle_calculo["cambiario"]["no_aplica"])
        self.assertNotIn("VOLATILIDAD", index.detalle_calculo["missing_indicators"])

    def test_batch_continues_for_invalid_country_and_deduplicates(self):
        result = recalcular_riesgos(["ZZ", "CO", "CO", "EC"])
        self.assertEqual(len(result["calculados"]), 2)
        self.assertEqual(result["errores"][0]["pais"], "ZZ")

    @patch("risk.services.IndiceRiesgo.save", side_effect=IntegrityError("test"))
    def test_persistence_failure_is_reported_without_internal_error_details(self, save):
        result = recalcular_riesgos(["CO"])
        self.assertEqual(result["calculados"], [])
        self.assertEqual(len(result["errores"]), 1)
        self.assertNotIn("test", result["errores"][0]["mensaje"])
        self.assertEqual(IndiceRiesgo.objects.count(), 0)

    @patch("backend.workflows.sincronizar_indicadores")
    def test_sync_coordinator_recalculates_only_processed_countries(self, sync):
        sync.return_value = {"paises_procesados": ["CO"], "errores": [{"pais": "BR"}], "estado": "PARCIAL"}
        result = sincronizar_y_recalcular(paises=["CO", "BR"])
        self.assertEqual(result["riesgos"]["calculados"][0]["pais"], "CO")
        self.assertFalse(result["recalculo_pendiente"])
        self.assertTrue(result["alertas_pendientes"])
        self.assertEqual(IndiceRiesgo.objects.count(), 1)

    @patch("backend.workflows.actualizar_tipos_cambio")
    def test_quote_coordinator_and_failed_sync(self, sync):
        sync.return_value = {"paises_procesados": ["EC"], "errores": [], "estado": "COMPLETO"}
        result = actualizar_y_recalcular()
        self.assertEqual(len(result["riesgos"]["calculados"]), 1)
        sync.return_value = {"paises_procesados": [], "errores": [{"pais": None}], "estado": "PARCIAL"}
        result = actualizar_y_recalcular()
        self.assertEqual(result["riesgos"]["calculados"], [])

    def test_command_and_invalid_country_exit(self):
        output = StringIO()
        call_command("calcular_riesgos", paises=["co", "EC"], stdout=output)
        self.assertEqual(len(json.loads(output.getvalue())["calculados"]), 2)
        with self.assertRaises(CommandError):
            call_command("calcular_riesgos", paises=["ZZ"], stdout=StringIO())

    def test_admin_calculation_validation_and_roles(self):
        user = get_user_model().objects.create_user(email="calculate@example.com", nombre_completo="Cálculo",
                                                    is_superuser=True)
        client = APIClient()
        url = reverse("risk:calcular")
        self.assertEqual(client.post(url, {}, format="json").status_code, 401)
        client.force_authenticate(user)
        for role in ("ANALISTA", "VIEWER"):
            user.rol = role
            self.assertEqual(client.post(url, {}, format="json").status_code, 403)
        self.assertEqual(IndiceRiesgo.objects.count(), 0)
        user.rol = "ADMIN"
        user.save()
        for data in ({"paises": []}, {"paises": ["ZZ"]}, {"pais": "CO"}, {"paises": ["COL"]}):
            self.assertEqual(client.post(url, data, format="json").status_code, 400)
        response = client.post(url, {"paises": ["co", "CO"]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["calculados"]), 1)
        self.assertEqual(IndiceRiesgo.objects.count(), 1)
        self.assertEqual(client.get(url).status_code, 405)
