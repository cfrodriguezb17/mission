from datetime import timedelta
from types import SimpleNamespace

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from audit.models import LogActividad
from countries.models import Pais
from portfolios.models import Portafolio, Posicion
from portfolios.serializers import PortafolioDetailSerializer
from risk.models import IndiceRiesgo

from .base import PortfolioTestCase


class PortfolioQueryTests(PortfolioTestCase):
    def setUp(self):
        super().setUp()
        self.br = Pais.objects.get(pk="BR")
        IndiceRiesgo.objects.create(
            pais=self.co, indice_compuesto="80", score_economico="80",
            score_cambiario="80", score_estabilidad="80", version_formula="test",
            detalle_calculo={},
        )

    def add_positions(self, closed=0):
        Posicion.objects.create(portafolio=self.public, **self.position_data())
        Posicion.objects.create(portafolio=self.public, **self.position_data(pais=self.br))
        for _ in range(closed):
            Posicion.objects.create(portafolio=self.public, **self.position_data(
                monto_inversion_usd="9000", fecha_salida=timezone.localdate() - timedelta(days=1)))

    def test_serialization_uses_two_queries_independent_of_history_size(self):
        self.add_positions()
        for closed in (0, 25):
            if closed:
                for _ in range(closed):
                    Posicion.objects.create(portafolio=self.public, **self.position_data(
                        monto_inversion_usd="9000", fecha_salida=timezone.localdate()))
            portfolio = Portafolio.objects.get(pk=self.public.pk)
            with self.subTest(closed=closed), self.assertNumQueries(2):
                data = PortafolioDetailSerializer(
                    portfolio, context={"request": SimpleNamespace(user=self.owner)}).data
            self.assertEqual(len(data["posiciones"]), 2 + closed)
            self.assertEqual({row["nombre_pais"] for row in data["posiciones"]},
                             {self.co.nombre, self.br.nombre})
            self.assertEqual(data["resumen"]["total_invertido_usd"], "2000.00")
            self.assertEqual(data["resumen"]["posiciones_activas"], 2)
            self.assertEqual(data["resumen"]["riesgo_promedio_ponderado"], "80.00")
            self.assertEqual(data["resumen"]["monto_sin_riesgo_usd"], "1000.00")
            self.assertEqual(data["resumen"]["paises_sin_riesgo"], ["BR"])
            self.assertTrue(data["resumen"]["riesgo_incompleto"])

    def test_detail_keeps_lock_and_audit_with_constant_select_count(self):
        self.add_positions(closed=25)
        with CaptureQueriesContext(connection) as queries:
            response = self.api.get(f"/api/portafolios/{self.public.pk}/")
        self.assertEqual(response.status_code, 200)
        selects = [row["sql"] for row in queries if row["sql"].startswith("SELECT")]
        self.assertEqual(len(selects), 3)  # portafolio, posiciones/países, riesgos
        self.assertIn("FOR UPDATE", selects[0])
        self.assertEqual(len(response.data["posiciones"]), 27)
        self.assertEqual(response.data["resumen"]["version"], response.data["version"])
        self.assertTrue(LogActividad.objects.filter(
            usuario=self.owner, accion="CONSULTAR", entidad_afectada="Portafolio",
            entidad_id=str(self.public.pk)).exists())

    def test_put_returns_updated_detail_and_summary(self):
        self.add_positions(closed=3)
        response = self.api.put(f"/api/portafolios/{self.public.pk}/",
                               {"version": 1, "nombre": "Actualizado"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["nombre"], "Actualizado")
        self.assertEqual(response.data["version"], 2)
        self.assertEqual(response.data["resumen"]["version"], 2)
        self.assertEqual(len(response.data["posiciones"]), 5)
        self.assertEqual(response.data["resumen"]["total_invertido_usd"], "2000.00")
