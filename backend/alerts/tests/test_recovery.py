import json
from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.db import IntegrityError, connections, transaction
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from alerts.models import Alerta
from alerts.services import generar_alertas
from backend.workflows import sincronizar_y_recalcular
from countries.models import Moneda, Pais
from economics.models import IndicadorEconomico, LoteActualizacion, TipoCambio
from economics.services import actualizar_tipos_cambio, cargar_catalogo, guardar_cotizacion, sincronizar_indicadores


def provider(value="100"):
    client = Mock()
    client.indicadores.return_value = [{"codigo_world_bank": "NY.GDP.MKTP.CD", "anio": 2025,
                                       "valor": Decimal(value)}]
    return client


def sync(client, *, workflow=False, paises=("CO",)):
    service = sincronizar_y_recalcular if workflow else sincronizar_indicadores
    return service(paises=list(paises), anio_inicio=2025, anio_fin=2025, client=client)


class PersistentInfoRecoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_countries", stdout=StringIO())
        cargar_catalogo()

    def test_quote_returning_to_old_rate_delivers_three_distinct_info_events(self):
        currency = Moneda.objects.get(pk="COP")
        evidence = []
        for rate in ("0.00025", "0.00020", "0.00025"):
            events = []
            guardar_cotizacion(currency, date(2026, 10, 10), Decimal(rate), eventos=events)
            evidence.extend({**event, "pais": "CO"} for event in events)
            result = generar_alertas(datos_nuevos=evidence[-1:], paises=["CO"])
            self.assertEqual(result, {"creadas": 1, "errores": [], "pendientes": 0})
        self.assertEqual(LoteActualizacion.objects.count(), 3)
        alerts = Alerta.objects.filter(severidad="INFO", tipo_alerta="TIPO_CAMBIO")
        self.assertEqual(alerts.count(), 3)
        self.assertEqual(len(set(alerts.values_list("clave_evento", flat=True))), 3)
        self.assertEqual({row.detalle["evidencia"]["datos"][0]["revision"] for row in alerts}, {1, 2, 3})
        # Reenviar cada respuesta original reutiliza el lote y la identidad.
        for event in evidence:
            self.assertEqual(generar_alertas(datos_nuevos=[event], paises=["CO"])["creadas"], 0)
        self.assertEqual(guardar_cotizacion(currency, date(2026, 10, 10), Decimal("0.00025")), "sin_cambios")
        self.assertEqual(generar_alertas(paises=["CO"])["creadas"], 0)
        self.assertEqual(LoteActualizacion.objects.count(), 3)
        self.assertEqual(Alerta.objects.count(), 3)

    def test_failed_quote_delivery_recovers_original_revisions_with_limit_and_shared_currency(self):
        Pais.objects.filter(pk="BR").update(moneda_id="COP")
        currency = Moneda.objects.get(pk="COP")
        for rate in ("0.00025", "0.00020", "0.00025"):
            guardar_cotizacion(currency, date(2026, 10, 10), Decimal(rate))
        # Tres cambios efectivos: una cotización y tres lotes por país.
        self.assertEqual(TipoCambio.objects.count(), 1)
        self.assertEqual(LoteActualizacion.objects.count(), 6)
        with patch("alerts.services.Alerta.objects.get_or_create", side_effect=IntegrityError("controlled")):
            first = generar_alertas(paises=["CO"], limite=1)
        self.assertEqual(first["creadas"], 0)
        self.assertEqual(first["pendientes"], 3)
        self.assertEqual(len(first["errores"]), 1)
        self.assertFalse(Alerta.objects.exists())
        self.assertEqual(generar_alertas(paises=["CO"], limite=2),
                         {"creadas": 2, "errores": [], "pendientes": 1})
        self.assertEqual(generar_alertas(paises=["CO"]), {"creadas": 1, "errores": [], "pendientes": 0})
        self.assertEqual(LoteActualizacion.objects.filter(pais_id="BR", fecha_alerta__isnull=True).count(), 3)
        self.assertEqual(generar_alertas(paises=["BR"]), {"creadas": 3, "errores": [], "pendientes": 0})
        self.assertEqual(generar_alertas()["creadas"], 0)
        self.assertEqual(Alerta.objects.count(), 6)
        for code in ("CO", "BR"):
            revisions = {row.detalle["evidencia"]["datos"][0]["revision"]
                         for row in Alerta.objects.filter(pais_id=code)}
            self.assertEqual(revisions, {1, 2, 3})

    def test_failed_outer_economic_transaction_leaves_no_orphan_event(self):
        with self.assertRaises(RuntimeError), transaction.atomic():
            guardar_cotizacion(Moneda.objects.get(pk="COP"), date(2026, 10, 10), Decimal("0.00025"))
            raise RuntimeError("controlled-rollback")
        self.assertFalse(TipoCambio.objects.exists())
        self.assertFalse(LoteActualizacion.objects.exists())
        self.assertEqual(generar_alertas()["creadas"], 0)
        self.assertFalse(Alerta.objects.exists())

    def test_unchanged_sync_recovers_failed_info_without_original_response(self):
        client = provider()
        with patch("alerts.services.Alerta.objects.get_or_create", side_effect=IntegrityError("private")):
            first = sync(client, workflow=True)
        self.assertTrue(first["alertas_pendientes"])
        self.assertEqual(first["alertas"]["pendientes"], 1)
        lote = LoteActualizacion.objects.get()
        original = lote.datos
        self.assertIsNone(lote.fecha_alerta)
        self.assertEqual(IndicadorEconomico.objects.count(), 1)
        self.assertNotIn("private", str(first["alertas"]))
        second = sync(client, workflow=True)
        self.assertEqual(second["datos_nuevos"], [])
        self.assertEqual(second["alertas"]["creadas"], 1)
        self.assertEqual(second["alertas"]["pendientes"], 0)
        self.assertFalse(second["alertas_pendientes"])
        self.assertEqual(Alerta.objects.get().detalle["evidencia"]["datos"], original)
        lote.refresh_from_db()
        self.assertIsNotNone(lote.fecha_alerta)
        self.assertEqual(sync(client, workflow=True)["alertas"]["creadas"], 0)
        self.assertEqual(LoteActualizacion.objects.count(), 1)

    def test_command_recovers_original_batches_after_new_values_are_saved(self):
        sync(provider("100"))
        sync(provider("200"))
        self.assertEqual(Alerta.objects.count(), 0)
        self.assertEqual(LoteActualizacion.objects.count(), 2)
        output = StringIO()
        call_command("generar_alertas", paises=["CO"], stdout=output)
        result = json.loads(output.getvalue())
        self.assertEqual(result["creadas"], 2)
        self.assertEqual(result["pendientes"], 0)
        values = {row.detalle["evidencia"]["datos"][0]["valor"] for row in Alerta.objects.all()}
        self.assertEqual(values, {"100.000000", "200.000000"})
        call_command("generar_alertas", stdout=StringIO())
        self.assertEqual(Alerta.objects.count(), 2)

    def test_alert_and_delivery_marker_roll_back_together(self):
        sync(provider())
        lote = LoteActualizacion.objects.get()
        with patch.object(LoteActualizacion, "save", side_effect=IntegrityError("private-marker")):
            result = generar_alertas()
        self.assertEqual(result["creadas"], 0)
        self.assertEqual(result["pendientes"], 1)
        self.assertEqual(len(result["errores"]), 1)
        self.assertNotIn("private-marker", str(result))
        self.assertEqual(Alerta.objects.count(), 0)
        lote.refresh_from_db()
        self.assertIsNone(lote.fecha_alerta)
        self.assertEqual(generar_alertas()["creadas"], 1)

    def test_failed_batch_registration_rolls_back_its_indicator_changes(self):
        with patch("economics.services.LoteActualizacion.objects.get_or_create", side_effect=IntegrityError("private")):
            result = sync(provider())
        self.assertTrue(result["errores"])
        self.assertNotIn("private", str(result))
        self.assertEqual(result["paises_procesados"], [])
        self.assertEqual(IndicadorEconomico.objects.count(), 0)
        self.assertEqual(LoteActualizacion.objects.count(), 0)

    def test_exchange_updates_have_recoverable_batches(self):
        client = Mock()
        client.cotizaciones.return_value = (date(2026, 1, 2), {"COP": Decimal("4000")})
        actualizar_tipos_cambio(client=client)
        lote = LoteActualizacion.objects.get(pais_id="CO")
        self.assertEqual(lote.datos[0]["tasa"], "0.000250000000")
        actualizar_tipos_cambio(client=client)
        self.assertEqual(LoteActualizacion.objects.count(), 1)
        call_command("generar_alertas", paises=["co"], stdout=StringIO())
        self.assertEqual(Alerta.objects.get().tipo_alerta, "TIPO_CAMBIO")
        self.assertEqual(Alerta.objects.get().detalle["evidencia"]["datos"], lote.datos)

    def test_shared_currency_has_one_quote_and_one_durable_batch_per_country(self):
        Pais.objects.filter(pk="BR").update(moneda_id="COP")
        client = Mock()
        client.cotizaciones.return_value = (date(2026, 1, 2), {"COP": Decimal("4000")})
        actualizar_tipos_cambio(client=client)
        self.assertEqual(TipoCambio.objects.count(), 1)
        self.assertEqual(set(LoteActualizacion.objects.values_list("pais_id", flat=True)), {"CO", "BR"})
        call_command("generar_alertas", stdout=StringIO())
        self.assertEqual(set(Alerta.objects.values_list("pais_id", flat=True)), {"CO", "BR"})

    def test_http_sync_reports_pending_then_recovers_without_reposting_evidence(self):
        admin = get_user_model().objects.create_user(email="info-recovery@example.com",
                                                     nombre_completo="Recuperación INFO", rol="ADMIN")
        api = APIClient()
        api.force_authenticate(admin)
        payload = {"paises": ["CO"], "anio_inicio": 2025, "anio_fin": 2025}
        with patch("integrations.world_bank.WorldBankClient.indicadores", return_value=provider().indicadores.return_value):
            with patch("alerts.services.Alerta.objects.get_or_create", side_effect=IntegrityError("private")):
                first = api.post("/api/paises/sync-indicadores/", payload, format="json")
            self.assertEqual(first.status_code, 200)
            self.assertTrue(first.data["alertas_pendientes"])
            self.assertEqual(first.data["alertas"]["pendientes"], 1)
            self.assertNotIn("private", str(first.data))
            second = api.post("/api/paises/sync-indicadores/", payload, format="json")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["datos_nuevos"], [])
        self.assertEqual(second.data["alertas"]["creadas"], 1)
        self.assertEqual(second.data["alertas"]["pendientes"], 0)
        self.assertFalse(second.data["alertas_pendientes"])
        self.assertEqual(Alerta.objects.count(), 1)

    def test_batch_failure_rolls_back_quote_and_preserves_other_currencies(self):
        client = Mock()
        client.cotizaciones.return_value = (date(2026, 1, 2), {"COP": Decimal("4000"), "BRL": Decimal("5")})
        register = LoteActualizacion.objects.get_or_create

        def fail_colombia(*args, **kwargs):
            if kwargs["defaults"]["pais_id"] == "CO":
                raise IntegrityError("private")
            return register(*args, **kwargs)

        with patch("economics.services.LoteActualizacion.objects.get_or_create", side_effect=fail_colombia):
            result = actualizar_tipos_cambio(client=client)
        self.assertNotIn("CO", result["paises_procesados"])
        self.assertIn("BR", result["paises_procesados"])
        self.assertFalse(TipoCambio.objects.filter(moneda_origen_id="COP").exists())
        self.assertEqual(list(LoteActualizacion.objects.values_list("pais_id", flat=True)), ["BR"])

    def test_command_filters_batches_and_recovers_inactive_countries(self):
        sync(provider(), paises=("CO", "BR"))
        Pais.objects.filter(pk="CO").update(activo=False)
        call_command("generar_alertas", paises=["co"], stdout=StringIO())
        self.assertEqual(list(Alerta.objects.values_list("pais_id", flat=True)), ["CO"])
        self.assertEqual(LoteActualizacion.objects.filter(fecha_alerta__isnull=True).get().pais_id, "BR")
        call_command("generar_alertas", stdout=StringIO())
        self.assertEqual(Alerta.objects.count(), 2)

    def test_limit_preserves_remaining_batches_and_reports_nonzero_exit(self):
        for value in ("100", "200", "300"):
            sync(provider(value))
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command("generar_alertas", limite=1, stdout=output)
        self.assertEqual(json.loads(output.getvalue())["pendientes"], 2)
        self.assertEqual(Alerta.objects.count(), 1)
        call_command("generar_alertas", limite=2, stdout=StringIO())
        self.assertEqual(Alerta.objects.count(), 3)
        for invalid in (0, 1001):
            with self.subTest(invalid=invalid), self.assertRaises(CommandError):
                call_command("generar_alertas", limite=invalid, stdout=StringIO())

    def test_workflow_keeps_pending_flag_when_limit_leaves_batches(self):
        with patch("backend.workflows.generar_alertas", return_value={"creadas": 0, "errores": [], "pendientes": 1}):
            result = sync(provider(), workflow=True)
            self.assertTrue(result["alertas_pendientes"])
            self.assertTrue(result["recalculo_y_alertas_pendientes"])
            with self.assertRaises(CommandError):
                call_command("calcular_riesgos", paises=["CO"], stdout=StringIO())

    def test_no_batch_for_missing_or_preserved_manual_data(self):
        IndicadorEconomico.objects.create(pais_id="CO", tipo_id="PIB", anio=2025, valor=17, fuente="MANUAL")
        sync(provider())
        empty = provider()
        empty.indicadores.return_value[0]["valor"] = None
        sync(empty)
        self.assertFalse(LoteActualizacion.objects.exists())


class InterruptedWorkflowRecoveryTests(TransactionTestCase):
    def test_committed_batch_survives_interruption_before_alert_generation(self):
        call_command("seed_countries", stdout=StringIO())
        with patch("backend.workflows.recalcular_riesgos", side_effect=RuntimeError("interrupcion-controlada")):
            with self.assertRaises(RuntimeError):
                sync(provider(), workflow=True)
        connections.close_all()
        self.assertEqual(IndicadorEconomico.objects.count(), 1)
        self.assertEqual(LoteActualizacion.objects.filter(fecha_alerta__isnull=True).count(), 1)
        call_command("generar_alertas", stdout=StringIO())
        self.assertEqual(Alerta.objects.count(), 1)
        self.assertFalse(LoteActualizacion.objects.filter(fecha_alerta__isnull=True).exists())
