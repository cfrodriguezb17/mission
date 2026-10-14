from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from alerts.models import Alerta
from alerts.services import generar_alertas
from countries.models import Moneda
from economics.models import LoteActualizacion, TipoCambio
from economics.services import guardar_cotizacion, registrar_actualizacion


class QuoteRevisionMigrationTests(TransactionTestCase):
    def test_incremental_migration_preserves_quotes_batches_and_existing_alerts(self):
        call_command("seed_countries", stdout=StringIO())
        previous = [("economics", "0003_lotes_actualizacion")]
        executor = MigrationExecutor(connection)
        current = executor.loader.graph.leaf_nodes()
        executor.migrate(previous)
        try:
            apps = executor.loader.project_state(previous).apps
            OldQuote = apps.get_model("economics", "TipoCambio")
            quote = OldQuote.objects.create(moneda_origen_id="COP", moneda_destino_id="USD",
                fecha=date(2026, 10, 10), tasa=Decimal("0.00025"), fuente="EXCHANGE_RATE")
            event = {"pais": "CO", "tipo": "TIPO_CAMBIO", "id": quote.pk, "moneda_origen": "COP",
                     "moneda_destino": "USD", "fecha": quote.fecha.isoformat(),
                     "tasa": "0.000250000000", "fuente": "EXCHANGE_RATE"}
            registrar_actualizacion("CO", [event])
            self.assertEqual(generar_alertas()["creadas"], 1)
            registrar_actualizacion("CO", [{**event, "fecha": "2026-10-09"}])
            batches = list(LoteActualizacion.objects.values())
            alerts = list(Alerta.objects.values())
            quote_id = quote.pk
        finally:
            MigrationExecutor(connection).migrate(current)

        quote = TipoCambio.objects.get(pk=quote_id)
        self.assertEqual(quote.revision, 0)
        self.assertEqual(quote.tasa, Decimal("0.00025"))
        self.assertEqual(quote.fecha, date(2026, 10, 10))
        self.assertEqual(quote.fuente, "EXCHANGE_RATE")
        self.assertFalse(quote.es_simulado)
        self.assertEqual(list(LoteActualizacion.objects.values()), batches)
        self.assertEqual(list(Alerta.objects.values()), alerts)
        currency = Moneda.objects.get(pk="COP")
        self.assertEqual(guardar_cotizacion(currency, quote.fecha, quote.tasa), "sin_cambios")
        self.assertEqual(TipoCambio.objects.get(pk=quote_id).revision, 0)
        self.assertEqual(LoteActualizacion.objects.count(), 2)
        # El pendiente antiguo sigue recuperable; el entregado no se repite.
        self.assertEqual(generar_alertas(), {"creadas": 1, "errores": [], "pendientes": 0})
        for revision, rate in enumerate(("0.00020", "0.00025"), start=1):
            guardar_cotizacion(currency, quote.fecha, Decimal(rate))
            self.assertEqual(TipoCambio.objects.get(pk=quote_id).revision, revision)
            self.assertEqual(generar_alertas()["creadas"], 1)
        self.assertEqual(Alerta.objects.count(), 4)
        self.assertEqual(generar_alertas()["creadas"], 0)
