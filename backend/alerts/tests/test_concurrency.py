from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from io import StringIO
from threading import Barrier

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connections
from django.db import transaction
from django.test import TransactionTestCase, skipUnlessDBFeature

from alerts.models import Alerta, LecturaAlerta
from alerts.services import generar_alertas, leer_todas
from countries.models import Moneda, Pais
from risk.models import IndiceRiesgo
from economics.models import LoteActualizacion, TipoCambio
from economics.services import guardar_cotizacion, registrar_actualizacion


class AlertConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_two_recoverers_deliver_historical_drop_once_and_process_all_indices(self):
        from alerts.tests.test_index_recovery import index

        call_command("seed_countries", stdout=StringIO())
        first, dropped, newest = index(80), index(60), index(60)
        results = self.run_concurrently(generar_alertas)
        self.assertTrue(all(not result["errores"] for result in results))
        self.assertEqual(sum(result["creadas"] for result in results), 1)
        alert = Alerta.objects.get()
        self.assertEqual(alert.detalle["evidencia"]["indice_actual"], dropped.pk)
        self.assertEqual(alert.detalle["evidencia"]["indice_anterior"], first.pk)
        self.assertFalse(IndiceRiesgo.objects.filter(fecha_alertas_procesadas__isnull=True).exists())
        self.assertEqual(generar_alertas()["creadas"], 0)

    def run_concurrently(self, operation):
        barrier = Barrier(2)
        def run():
            try:
                barrier.wait(timeout=10)
                return operation()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run) for _ in range(2)]
            return [future.result(timeout=15) for future in futures]

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_quote_writers_and_recovery_preserve_each_revision_once(self):
        call_command("seed_countries", stdout=StringIO())
        Pais.objects.filter(pk="BR").update(moneda_id="COP")
        currency = Moneda.objects.get(pk="COP")
        for revision, rate in enumerate(("0.00025", "0.00020", "0.00025"), start=1):
            writes = self.run_concurrently(lambda: guardar_cotizacion(currency, date(2026, 10, 10), Decimal(rate)))
            self.assertCountEqual(writes, ["creados" if revision == 1 else "actualizados", "sin_cambios"])
            self.assertEqual(TipoCambio.objects.get().revision, revision)
        results = self.run_concurrently(generar_alertas)
        self.assertEqual(sum(result["creadas"] for result in results), 6)
        self.assertTrue(all(not result["errores"] for result in results))
        self.assertEqual(LoteActualizacion.objects.count(), 6)
        self.assertEqual(Alerta.objects.count(), 6)
        self.assertFalse(LoteActualizacion.objects.filter(fecha_alerta__isnull=True).exists())
        self.assertEqual(generar_alertas()["creadas"], 0)

    def test_concurrent_generation_deduplicates_same_event(self):
        call_command("seed_countries", stdout=StringIO())
        index = IndiceRiesgo.objects.create(pais_id="CO", score_economico=20, score_cambiario=20,
            score_estabilidad=20, indice_compuesto=20, version_formula="test", detalle_calculo={})
        results = self.run_concurrently(lambda: generar_alertas([{"id": index.pk, "pais": "CO"}]))
        self.assertEqual(sum(result["creadas"] for result in results), 1)
        self.assertEqual(Alerta.objects.count(), 1)
        self.assertTrue(all(not result["errores"] for result in results))

    def test_concurrent_read_all_reports_actual_new_rows(self):
        call_command("seed_countries", stdout=StringIO())
        user = get_user_model().objects.create_user(email="read-all@example.com", nombre_completo="Lecturas")
        for _ in range(3):
            Alerta.objects.create(pais_id="CO", tipo_alerta="RIESGO", severidad="INFO", titulo="Global", mensaje="Test")
        counts = self.run_concurrently(lambda: leer_todas(user))
        self.assertEqual(sorted(counts), [0, 3])
        self.assertEqual(LecturaAlerta.objects.count(), 3)

    def test_concurrent_recovery_delivers_each_batch_once(self):
        call_command("seed_countries", stdout=StringIO())
        with transaction.atomic():
            registrar_actualizacion("CO", [{"pais": "CO", "tipo": "PIB", "valor": "100", "id": 1}])
        results = self.run_concurrently(generar_alertas)
        self.assertEqual(sum(result["creadas"] for result in results), 1)
        self.assertTrue(all(not result["errores"] for result in results))
        self.assertEqual(Alerta.objects.count(), 1)
        self.assertFalse(LoteActualizacion.objects.filter(fecha_alerta__isnull=True).exists())
