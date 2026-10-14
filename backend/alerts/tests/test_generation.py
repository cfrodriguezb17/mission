from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import TestCase

from alerts.models import Alerta
from alerts.services import generar_alertas
from backend.workflows import recalcular_con_alertas, sincronizar_y_recalcular
from economics.models import TipoCambio
from risk.models import IndiceRiesgo


class GenerationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_countries", stdout=StringIO())

    def index(self, score=100, inflation=None, rate=None, previous_rate="100", gap=False, country="CO"):
        detail = {"indicadores": {}, "cotizaciones": [], "datos_parciales": False}
        if inflation is not None:
            detail["indicadores"]["INFLACION"] = {"id": 1, "valor": str(inflation), "anio": 2025, "fuente": "MANUAL"}
        if rate is not None:
            detail["cotizaciones"] = [{"fecha": "2026-01-02", "tasa": str(rate), "moneda_origen": "COP", "moneda_destino": "USD"},
                {"fecha": "2025-12-31" if gap else "2026-01-01", "tasa": previous_rate, "moneda_origen": "COP", "moneda_destino": "USD"}]
        return IndiceRiesgo.objects.create(pais_id=country, indice_compuesto=score, score_economico=score,
            score_cambiario=score, score_estabilidad=score, version_formula="fixture", detalle_calculo=detail)

    def generate(self, index):
        return generar_alertas([{"id": index.pk, "pais": index.pais_id}])

    def test_critical_boundaries_and_repeated_calculation_same_data(self):
        index = self.index(25, inflation=50)
        self.assertEqual(self.generate(index)["creadas"], 0)
        critical = self.index(Decimal("24.99"), inflation="50.01")
        self.assertEqual(self.generate(critical)["creadas"], 2)
        self.assertEqual(self.generate(critical)["creadas"], 0)
        self.assertEqual(self.generate(self.index(Decimal("24.99"), inflation="50.01"))["creadas"], 0)
        self.assertEqual(Alerta.objects.filter(severidad="CRITICAL").count(), 2)
        self.assertTrue(all(alert.usuario is None for alert in Alerta.objects.all()))

    def test_drop_strict_boundary_and_predecessor_with_equal_timestamps(self):
        first = self.index(80)
        boundary = self.index(65)
        self.assertEqual(self.generate(boundary)["creadas"], 0)
        lower = self.index(Decimal("49.99"))
        IndiceRiesgo.objects.filter(pk__in=[first.pk, boundary.pk, lower.pk]).update(fecha_calculo=first.fecha_calculo)
        self.assertEqual(self.generate(lower)["creadas"], 1)
        alert = Alerta.objects.get()
        self.assertEqual(alert.detalle["evidencia"]["indice_anterior"], boundary.pk)
        self.assertEqual(self.generate(lower)["creadas"], 0)

    def test_exchange_absolute_threshold_both_directions_and_no_gap_bridging(self):
        for rate, expected in (("103", 0), ("97", 0), ("103.000001", 1), ("96.999999", 1)):
            with self.subTest(rate=rate):
                index = self.index(rate=rate)
                result = self.generate(index)
                self.assertEqual(result["creadas"], expected)
                self.assertEqual(self.generate(index)["creadas"], 0)
        self.assertEqual(self.generate(self.index(rate="200", gap=True))["creadas"], 0)
        self.assertEqual(Alerta.objects.filter(tipo_alerta="TIPO_CAMBIO").count(), 2)

    def test_new_data_info_is_per_country_and_idempotent_under_reordering(self):
        events = [{"pais": "CO", "tipo": "PIB", "valor": "100", "id": 1},
                  {"pais": "CO", "tipo": "INFLACION", "valor": "11", "id": 2}]
        self.assertEqual(generar_alertas(datos_nuevos=events)["creadas"], 1)
        self.assertEqual(generar_alertas(datos_nuevos=events[::-1])["creadas"], 0)
        self.assertEqual(generar_alertas(datos_nuevos=[])["creadas"], 0)
        self.assertEqual(Alerta.objects.get().severidad, "INFO")

    def test_extreme_exchange_precision(self):
        index = self.index(rate="999999999999.999999999999", previous_rate="0.000000000001")
        self.assertEqual(self.generate(index)["creadas"], 1)
        self.assertEqual(self.generate(index)["creadas"], 0)

    def test_unknown_index_partial_failure_and_retry(self):
        result = generar_alertas([{"id": 99999, "pais": "CO"}, {"id": self.index(20).pk, "pais": "CO"}])
        self.assertEqual(result["creadas"], 1)
        self.assertEqual(len(result["errores"]), 1)

    @patch("alerts.services.Alerta.objects.get_or_create", side_effect=IntegrityError("internal"))
    def test_failure_is_reported_and_rolls_back(self, create):
        index = self.index(20)
        result = self.generate(index)
        self.assertEqual(result["creadas"], 0)
        self.assertNotIn("internal", result["errores"][0]["mensaje"])
        self.assertEqual(Alerta.objects.count(), 0)

    def test_world_bank_workflow_changes_only_and_partial_failures(self):
        from integrations.http import ProviderError
        provider = Mock()
        provider.indicadores.side_effect = [ProviderError("offline"), [
            {"codigo_world_bank": "FP.CPI.TOTL.ZG", "anio": 2025, "valor": Decimal("60")}]]
        result = sincronizar_y_recalcular(paises=["CO", "BR"], anio_inicio=2025, anio_fin=2025, client=provider)
        self.assertEqual(result["paises_procesados"], ["BR"])
        self.assertEqual(result["alertas"]["creadas"], 2)  # inflación + INFO
        self.assertFalse(result["alertas_pendientes"])
        provider.indicadores.side_effect = None
        provider.indicadores.return_value = [{"codigo_world_bank": "FP.CPI.TOTL.ZG", "anio": 2025, "valor": Decimal("60")}]
        result = sincronizar_y_recalcular(paises=["BR"], anio_inicio=2025, anio_fin=2025, client=provider)
        self.assertEqual(result["datos_nuevos"], [])
        self.assertEqual(result["alertas"]["creadas"], 0)

    def test_exchange_workflow_info_and_warning_and_repeat(self):
        from backend.workflows import actualizar_y_recalcular
        from unittest.mock import Mock
        from django.utils import timezone
        from datetime import timedelta
        today = timezone.now().date()
        TipoCambio.objects.create(moneda_origen_id="COP", fecha=today - timedelta(days=1), tasa=1, fuente="MANUAL")
        provider = Mock()
        provider.cotizaciones.return_value = (today, {"COP": Decimal("2")})  # hoy: 0.5 USD/COP, -50 %
        result = actualizar_y_recalcular(client=provider)
        self.assertEqual(result["alertas"]["creadas"], 2)
        self.assertEqual(result["datos_nuevos"][0]["pais"], "CO")
        result = actualizar_y_recalcular(client=provider)
        self.assertEqual(result["alertas"]["creadas"], 0)

    @patch("backend.workflows.generar_alertas", return_value={"creadas": 0, "errores": [{"pais": "CO"}]})
    def test_pending_flags_and_command_nonzero_on_alert_failure(self, alerts):
        result = recalcular_con_alertas(paises=["CO"])
        self.assertTrue(result["alertas_pendientes"])
        with self.assertRaises(CommandError):
            call_command("calcular_riesgos", paises=["CO"], stdout=StringIO())

    def test_simulated_input_evidence_is_preserved(self):
        index = self.index(20)
        index.detalle_calculo["cotizaciones"] = [{"fecha": "2026-01-01", "tasa": "100", "es_simulado": True}]
        index.save()
        self.generate(index)
        self.assertTrue(Alerta.objects.get().detalle["evidencia"]["cotizaciones"][0]["es_simulado"])

    def test_recovery_command_processes_pending_and_is_idempotent(self):
        self.index(20)
        call_command("generar_alertas", paises=["co"], stdout=StringIO())
        self.assertEqual(Alerta.objects.count(), 1)
        call_command("generar_alertas", stdout=StringIO())
        self.assertEqual(Alerta.objects.count(), 1)
        with self.assertRaises(CommandError):
            call_command("generar_alertas", paises=["ZZ"], stdout=StringIO())
