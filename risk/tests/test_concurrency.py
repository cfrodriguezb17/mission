from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier

from django.core.management import call_command
from django.db import connections
from django.test import TransactionTestCase

from risk.models import IndiceRiesgo
from risk.services import calcular_pais


class RiskConcurrencyTests(TransactionTestCase):
    def test_simultaneous_calculations_preserve_both_snapshots(self):
        call_command("seed_countries", stdout=StringIO())
        barrier = Barrier(2)

        def calculate():
            try:
                barrier.wait(timeout=10)
                return calcular_pais("CO").pk
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(calculate) for _ in range(2)]
            ids = [future.result(timeout=15) for future in futures]
        self.assertEqual(len(set(ids)), 2)
        self.assertEqual(IndiceRiesgo.objects.filter(pk__in=ids).count(), 2)
