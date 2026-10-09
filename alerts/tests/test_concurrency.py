from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connections
from django.test import TransactionTestCase

from alerts.models import Alerta, LecturaAlerta
from alerts.services import generar_alertas, leer_todas
from risk.models import IndiceRiesgo


class AlertConcurrencyTests(TransactionTestCase):
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
