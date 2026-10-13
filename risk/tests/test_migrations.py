from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from alerts.models import Alerta
from alerts.services import generar_alertas
from countries.models import Pais
from risk.models import IndiceRiesgo


class PendingIndexMigrationTests(TransactionTestCase):
    def test_preserves_history_and_alerts_only_latest_per_country_is_pending(self):
        call_command("seed_countries", stdout=StringIO())
        Pais.objects.filter(pk="BR").update(activo=False)
        previous = [("risk", "0001_initial")]
        executor = MigrationExecutor(connection)
        current = executor.loader.graph.leaf_nodes()
        executor.migrate(previous)
        try:
            apps = executor.loader.project_state(previous).apps
            OldIndex = apps.get_model("risk", "IndiceRiesgo")
            stamp = timezone.now()

            def old_index(score, country="CO"):
                return OldIndex.objects.create(pais_id=country, fecha_calculo=stamp,
                    indice_compuesto=score, score_economico=score, score_cambiario=score,
                    score_estabilidad=score, version_formula="fixture", detalle_calculo={})

            # Caída anterior perdida: no debe desencadenar notificaciones masivas.
            older = old_index(80)
            lost_drop = old_index(60)
            latest_co = old_index(60)
            latest_br = old_index(20, "BR")
            # Simular una alerta anterior: la clave de evidencia se conserva.
            existing = Alerta.objects.create(pais_id="BR", tipo_alerta="RIESGO", severidad="INFO",
                                             titulo="Previa", mensaje="Previa", detalle={"original": True})
            old_rows = list(OldIndex.objects.order_by("pk").values())
            old_alerts = list(Alerta.objects.values())
        finally:
            MigrationExecutor(connection).migrate(current)

        fields = list(old_rows[0])
        self.assertEqual(list(IndiceRiesgo.objects.order_by("pk").values(*fields)), old_rows)
        self.assertEqual(list(Alerta.objects.values()), old_alerts)
        self.assertEqual(set(IndiceRiesgo.objects.filter(fecha_alertas_procesadas__isnull=True)
                             .values_list("pk", flat=True)), {latest_co.pk, latest_br.pk})
        self.assertEqual(set(IndiceRiesgo.objects.filter(fecha_alertas_procesadas__isnull=False)
                             .values_list("pk", flat=True)), {older.pk, lost_drop.pk})
        # Solo se revisa el último de cada país, aun inactivo, sin reenviar la caída perdida.
        self.assertEqual(generar_alertas(), {"creadas": 1, "errores": [], "pendientes": 0})
        self.assertFalse(Alerta.objects.filter(detalle__regla="CAIDA_IRPC").exists())
        self.assertEqual(Alerta.objects.get(pk=existing.pk).detalle, {"original": True})
        self.assertEqual(generar_alertas()["creadas"], 0)
        # Después del corte todos los índices nuevos quedan pendientes, incluidos históricos.
        new = IndiceRiesgo.objects.create(pais_id="CO", indice_compuesto=20,
            score_economico=20, score_cambiario=20, score_estabilidad=20,
            version_formula="fixture", detalle_calculo={})
        self.assertIsNone(new.fecha_alertas_procesadas)
        self.assertEqual(generar_alertas()["creadas"], 2)  # crítico + caída del último 60.
