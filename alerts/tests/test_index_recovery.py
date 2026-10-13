import json
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from alerts.models import Alerta
from alerts.services import generar_alertas, generar_para_indice
from audit.models import LogActividad
from backend.workflows import recalcular_con_alertas
from countries.models import Pais
from economics.models import LoteActualizacion
from economics.services import registrar_actualizacion
from risk.models import IndiceRiesgo
from risk.services import calcular_pais


def index(score=80, *, country="CO", inflation=None):
    detail = {"indicadores": {}, "cotizaciones": []}
    if inflation is not None:
        detail["indicadores"]["INFLACION"] = {"valor": str(inflation), "anio": 2025}
    return IndiceRiesgo.objects.create(
        pais_id=country, score_economico=score, score_cambiario=score,
        score_estabilidad=score, indice_compuesto=score,
        version_formula="fixture", detalle_calculo=detail)


class HistoricalIndexRecoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_countries", stdout=StringIO())

    def test_failed_drop_recovers_after_new_index_without_supplying_ids(self):
        index(80)
        dropped = index(60)
        with patch("alerts.services.Alerta.objects.get_or_create", side_effect=IntegrityError("private")):
            failed = generar_alertas()
        self.assertEqual(failed["creadas"], 0)
        self.assertEqual(failed["pendientes"], 1)
        self.assertEqual(failed["errores"][0]["indice"], dropped.pk)
        self.assertNotIn("private", str(failed))
        newest = index(60)
        output = StringIO()
        call_command("generar_alertas", stdout=output)
        self.assertEqual(json.loads(output.getvalue()), {"creadas": 1, "errores": [], "pendientes": 0})
        alert = Alerta.objects.get()
        self.assertEqual(alert.detalle["regla"], "CAIDA_IRPC")
        self.assertEqual(alert.detalle["evidencia"]["indice_actual"], dropped.pk)
        self.assertNotEqual(alert.detalle["evidencia"]["indice_actual"], newest.pk)
        call_command("generar_alertas", stdout=StringIO())
        self.assertEqual(Alerta.objects.count(), 1)
        self.assertFalse(IndiceRiesgo.objects.filter(fecha_alertas_procesadas__isnull=True).exists())

    def test_no_rules_is_processed_and_does_not_evaluate_again(self):
        row = index(80)
        self.assertEqual(generar_para_indice(row.pk), 0)
        row.refresh_from_db()
        stamp = row.fecha_alertas_procesadas
        self.assertIsNotNone(stamp)
        # El consumidor debe salir antes de volver a consultar las reglas.
        with patch("alerts.services.crear_evento", side_effect=AssertionError("already processed")), \
                patch("alerts.services.IndiceRiesgo.objects.filter", side_effect=AssertionError("already processed")):
            self.assertEqual(generar_para_indice(row.pk), 0)
        row.refresh_from_db()
        self.assertEqual(row.fecha_alertas_procesadas, stamp)

    def test_marker_failure_rolls_back_alert_and_retry_delivers_once(self):
        row = index(20)
        with patch.object(IndiceRiesgo, "save", side_effect=IntegrityError("private-marker")):
            result = generar_alertas()
        self.assertEqual(result["creadas"], 0)
        self.assertEqual(result["pendientes"], 1)
        self.assertEqual(len(result["errores"]), 1)
        self.assertFalse(Alerta.objects.exists())
        row.refresh_from_db()
        self.assertIsNone(row.fecha_alertas_procesadas)
        self.assertEqual(generar_alertas(), {"creadas": 1, "errores": [], "pendientes": 0})
        self.assertEqual(generar_alertas()["creadas"], 0)

    def test_failure_in_second_rule_rolls_back_first_rule_and_marker(self):
        row = index(20, inflation=60)
        create = Alerta.objects.get_or_create

        def fail_inflation(*args, **kwargs):
            if kwargs["defaults"]["detalle"]["regla"] == "INFLACION_CRITICA":
                raise IntegrityError("controlled")
            return create(*args, **kwargs)

        with patch("alerts.services.Alerta.objects.get_or_create", side_effect=fail_inflation):
            self.assertEqual(generar_alertas()["pendientes"], 1)
        self.assertFalse(Alerta.objects.exists())
        row.refresh_from_db()
        self.assertIsNone(row.fecha_alertas_procesadas)
        self.assertEqual(generar_alertas()["creadas"], 2)
        self.assertEqual(generar_alertas()["creadas"], 0)

    def test_rolled_back_calculation_has_no_pending_work_or_event(self):
        with self.assertRaises(RuntimeError), transaction.atomic():
            row = calcular_pais("CO")
            self.assertIsNone(row.fecha_alertas_procesadas)
            raise RuntimeError("controlled")
        self.assertFalse(IndiceRiesgo.objects.exists())
        self.assertEqual(generar_alertas(), {"creadas": 0, "errores": [], "pendientes": 0})
        self.assertFalse(Alerta.objects.exists())

    def test_limit_is_shared_with_info_and_no_rules_still_consumes_budget(self):
        oldest = index(80)
        with transaction.atomic():
            registrar_actualizacion("CO", [{"pais": "CO", "tipo": "PIB", "valor": "100", "id": 1}])
        newest = index(60)
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command("generar_alertas", limite=1, stdout=output)
        self.assertEqual(json.loads(output.getvalue()), {"creadas": 0, "errores": [], "pendientes": 2})
        oldest.refresh_from_db()
        newest.refresh_from_db()
        self.assertIsNotNone(oldest.fecha_alertas_procesadas)
        self.assertIsNone(newest.fecha_alertas_procesadas)
        self.assertIsNone(LoteActualizacion.objects.get().fecha_alerta)
        # El lote es anterior al segundo índice y recibe el próximo turno.
        self.assertEqual(generar_alertas(limite=1), {"creadas": 1, "errores": [], "pendientes": 1})
        self.assertEqual(Alerta.objects.get().severidad, "INFO")
        self.assertEqual(generar_alertas(limite=1), {"creadas": 1, "errores": [], "pendientes": 0})
        self.assertEqual(Alerta.objects.filter(detalle__regla="CAIDA_IRPC").count(), 1)

    def test_failed_job_consumes_budget_and_command_reports_pending(self):
        row = index(20)
        index(20, country="BR")
        output = StringIO()
        with patch("alerts.services.crear_evento", side_effect=IntegrityError("private")):
            with self.assertRaises(CommandError):
                call_command("generar_alertas", limite=1, stdout=output)
        result = json.loads(output.getvalue())
        self.assertEqual(result["pendientes"], 2)
        self.assertEqual(len(result["errores"]), 1)
        self.assertEqual(result["errores"][0]["indice"], row.pk)
        self.assertNotIn("private", str(result))

    def test_filter_counts_only_its_scope_and_includes_inactive_country(self):
        co = index(20)
        br = index(20, country="BR")
        Pais.objects.filter(pk="CO").update(activo=False)
        output = StringIO()
        call_command("generar_alertas", paises=["co"], stdout=output)
        self.assertEqual(json.loads(output.getvalue())["pendientes"], 0)
        self.assertEqual(list(Alerta.objects.values_list("pais_id", flat=True)), ["CO"])
        co.refresh_from_db()
        br.refresh_from_db()
        self.assertIsNotNone(co.fecha_alertas_procesadas)
        self.assertIsNone(br.fecha_alertas_procesadas)
        self.assertEqual(generar_alertas(paises=iter(["BR"]))["creadas"], 1)

    def test_explicit_ids_cannot_bypass_country_filter_or_processing_limit(self):
        co = index(20)
        br = index(20, country="BR")
        result = generar_alertas([{"id": br.pk, "pais": "BR"}, {"id": co.pk, "pais": "CO"}],
                                 paises=["CO"], limite=1)
        self.assertEqual(result, {"creadas": 1, "errores": [], "pendientes": 0})
        self.assertEqual(Alerta.objects.get().pais_id, "CO")
        br.refresh_from_db()
        self.assertIsNone(br.fecha_alertas_procesadas)

    def test_workflow_flags_pending_history_even_without_generation_errors(self):
        # 101 trabajos sin reglas: el presupuesto es 100, más el nuevo cálculo.
        for _ in range(101):
            index(80)
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command("calcular_riesgos", paises=["CO"], stdout=output)
        result = json.loads(output.getvalue())
        self.assertEqual(result["alertas"]["errores"], [])
        self.assertEqual(result["alertas"]["pendientes"], 2)
        self.assertTrue(result["alertas_pendientes"])
        self.assertEqual(LogActividad.objects.get().detalle["estado"], "PARCIAL")
        self.assertEqual(generar_alertas()["pendientes"], 0)

    def test_http_recalculation_reports_failed_history_then_recovers(self):
        index(80)
        dropped = index(60)
        user = get_user_model().objects.create_user(email="risk-recovery@example.com",
                                                    nombre_completo="Recuperación IRPC", rol="ADMIN")
        api = APIClient()
        api.force_authenticate(user)
        with patch("alerts.services.crear_evento", side_effect=IntegrityError("private")):
            response = api.post("/api/riesgo/calcular/", {"paises": ["CO"]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["alertas_pendientes"])
        self.assertEqual(response.data["alertas"]["pendientes"], 1)
        self.assertEqual(response.data["alertas"]["errores"][0]["indice"], dropped.pk)
        self.assertNotIn("private", str(response.data))
        response = api.post("/api/riesgo/calcular/", {"paises": ["CO"]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["alertas_pendientes"])
        self.assertEqual(response.data["alertas"]["pendientes"], 0)
        self.assertEqual(Alerta.objects.get().detalle["evidencia"]["indice_actual"], dropped.pk)

    def test_equal_timestamps_recovery_uses_id_for_predecessor_and_budget(self):
        first, dropped, latest = index(80), index(60), index(60)
        IndiceRiesgo.objects.update(fecha_calculo=timezone.now() - timedelta(days=1))
        self.assertEqual(generar_alertas(limite=2), {"creadas": 1, "errores": [], "pendientes": 1})
        evidence = Alerta.objects.get().detalle["evidencia"]
        self.assertEqual((evidence["indice_anterior"], evidence["indice_actual"]), (first.pk, dropped.pk))
        latest.refresh_from_db()
        self.assertIsNone(latest.fecha_alertas_procesadas)
        self.assertEqual(generar_alertas()["pendientes"], 0)

    def test_service_rejects_invalid_limits(self):
        for invalid in (0, 1001, True, "1", None):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                generar_alertas(limite=invalid)


class InterruptedIndexRecoveryTests(TransactionTestCase):
    def test_committed_calculation_survives_interruption_before_alert_generation(self):
        call_command("seed_countries", stdout=StringIO())
        with patch("backend.workflows.generar_alertas", side_effect=RuntimeError("interrupted")):
            with self.assertRaises(RuntimeError):
                recalcular_con_alertas(paises=["CO"])
        connections.close_all()
        self.assertEqual(IndiceRiesgo.objects.filter(fecha_alertas_procesadas__isnull=True).count(), 1)
        call_command("generar_alertas", stdout=StringIO())
        self.assertFalse(IndiceRiesgo.objects.filter(fecha_alertas_procesadas__isnull=True).exists())
