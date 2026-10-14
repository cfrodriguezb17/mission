from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from alerts.models import Alerta, LecturaAlerta
from audit.models import LogActividad
from countries.models import Pais
from economics.models import IndicadorEconomico
from portfolios.models import Portafolio
from risk.models import IndiceRiesgo
from dashboard.selectors import resumen_dashboard


class DashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_countries", stdout=StringIO())
        User = get_user_model()
        cls.user = User.objects.create_user(email="dashboard@example.com", nombre_completo="Lector", rol="VIEWER")
        cls.other = User.objects.create_user(email="dashboard-other@example.com", nombre_completo="Otro", rol="ANALISTA")
        cls.admin = User.objects.create_user(email="dashboard-admin@example.com", nombre_completo="Admin", rol="ADMIN")
        cls.country = Pais.objects.get(pk="CO")
        cls.old = cls.index(cls.country, "30", timezone.now() - timedelta(days=1))
        cls.latest = cls.index(cls.country, "80", timezone.now(), partial=True)
        cls.index(Pais.objects.get(pk="BR"), "40", timezone.now())
        Portafolio.objects.create(usuario=cls.user, nombre="Propio")
        Portafolio.objects.create(usuario=cls.user, nombre="Eliminado", activo=False)
        Portafolio.objects.create(usuario=cls.other, nombre="Público", es_publico=True)
        Portafolio.objects.create(usuario=cls.other, nombre="Privado")
        cls.global_alert = Alerta.objects.create(pais=cls.country, tipo_alerta="RIESGO", severidad="WARNING",
            titulo="Global", mensaje="Prueba", clave_evento="dashboard-global")
        Alerta.objects.create(usuario=cls.other, pais=cls.country, tipo_alerta="RIESGO", severidad="CRITICAL",
            titulo="Privada", mensaje="Prueba", clave_evento="dashboard-private")
        cls.year = timezone.now().year - 1
        for year, value in [(cls.year, "100"), (cls.year - 4, "0"), (cls.year - 5, "50"), (cls.year + 1, "200")]:
            IndicadorEconomico.objects.create(pais=cls.country, tipo_id="PIB", anio=year,
                valor=value, fuente="MANUAL", es_simulado=True)

    @staticmethod
    def index(country, score, date, partial=False):
        return IndiceRiesgo.objects.create(pais=country, indice_compuesto=score,
            score_economico=score, score_cambiario=score, score_estabilidad=score,
            fecha_calculo=date, version_formula="test", detalle_calculo={"datos_parciales": partial, "contiene_simulaciones": True})

    def setUp(self):
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def test_summary_uses_only_latest_risk_and_own_active_portfolios(self):
        # Cuatro SELECT y el INSERT de auditoría, sin autenticación SQL en este cliente.
        with self.assertNumQueries(5):
            response = self.api.get("/api/dashboard/resumen/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"total_paises": 10, "alertas_activas": 1,
            "portafolios_usuario": 1, "promedio_irpc": "60.00", "paises_con_riesgo": 2,
            "paises_con_datos_parciales": 1})
        event = LogActividad.objects.get(accion="CONSULTAR", entidad_afectada="Dashboard")
        self.assertEqual(event.usuario, self.user)

    def test_summary_without_risks_preserves_null_average_and_zero_counts(self):
        IndiceRiesgo.objects.all().delete()
        with self.assertNumQueries(4):
            data = resumen_dashboard(self.user)
        self.assertIsNone(data["promedio_irpc"])
        self.assertEqual(data["paises_con_riesgo"], 0)
        self.assertEqual(data["paises_con_datos_parciales"], 0)

    def test_summary_excludes_inactive_countries_and_missing_partial_flag(self):
        Pais.objects.filter(pk="CO").update(activo=False)
        IndiceRiesgo.objects.filter(pais_id="BR").update(detalle_calculo={})
        with self.assertNumQueries(4):
            data = resumen_dashboard(self.user)
        self.assertEqual(data["total_paises"], 9)
        self.assertEqual(data["promedio_irpc"], "40.00")
        self.assertEqual(data["paises_con_riesgo"], 1)
        self.assertEqual(data["paises_con_datos_parciales"], 0)

    def test_alert_reads_are_independent_and_private_alerts_never_leak(self):
        LecturaAlerta.objects.create(usuario=self.other, alerta=self.global_alert)
        self.assertEqual(self.api.get("/api/dashboard/resumen/").data["alertas_activas"], 1)
        LecturaAlerta.objects.create(usuario=self.user, alerta=self.global_alert)
        self.assertEqual(self.api.get("/api/dashboard/resumen/").data["alertas_activas"], 0)

    def test_admin_kpi_counts_own_portfolios_not_all_visible_portfolios(self):
        self.api.force_authenticate(self.admin)
        self.assertEqual(self.api.get("/api/dashboard/resumen/").data["portafolios_usuario"], 0)

    def test_map_includes_countries_without_risk_and_preserves_zero(self):
        self.latest.indice_compuesto = Decimal("0")
        self.latest.save()
        response = self.api.get("/api/dashboard/mapa/", {"ordering": "codigo_iso", "page_size": 100})
        rows = {row["codigo_iso"]: row for row in response.data["results"]}
        self.assertEqual(rows["CO"]["indice_compuesto"], "0.00")
        self.assertEqual(rows["CO"]["color"], "#ef4444")
        self.assertTrue(rows["CO"]["datos_parciales"])
        self.assertIsNone(rows["MX"]["indice_compuesto"])
        self.assertEqual(rows["MX"]["nivel_riesgo"], "SIN_DATOS")
        self.assertEqual(response.data["count"], 10)

    def test_map_excludes_inactive_countries_and_validates_ordering(self):
        self.country.activo = False
        self.country.save()
        self.assertEqual(self.api.get("/api/dashboard/mapa/", {"page_size": 2}).data["count"], 9)
        self.assertEqual(self.api.get("/api/dashboard/mapa/", {"ordering": "password"}).status_code, 400)

    def test_trends_cover_five_complete_years_and_distinguish_zero_from_missing(self):
        response = self.api.get("/api/dashboard/tendencias/", {"tipo": "pib", "paises": "co,br"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["anio_inicio"], self.year - 4)
        self.assertEqual(response.data["anio_fin"], self.year)
        rows = {row["pais"]: row for row in response.data["results"]}
        self.assertEqual(len(rows["CO"]["valores"]), 5)
        self.assertEqual(rows["CO"]["valores"][0]["valor"], "0.000000")
        self.assertIsNone(rows["CO"]["valores"][1]["valor"])
        self.assertTrue(rows["BR"]["datos_parciales"])
        self.assertTrue(rows["CO"]["valores"][-1]["es_simulado"])

    def test_trends_paginate_series_without_losing_envelope(self):
        response = self.api.get("/api/dashboard/tendencias/", {"paises": "CO,BR,MX", "page_size": 1, "page": 2})
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(response.data["results"][0]["pais"], "CO")
        self.assertEqual(response.data["unidad"], "USD")

    def test_trend_filters_reject_unknown_duplicate_inactive_and_too_many_countries(self):
        for params in [{"tipo": "NO_EXISTE"}, {"paises": "CO,CO"}, {"paises": "XX"},
                       {"paises": "CO,BR,MX,AR"}, {"paises": ""}, {"ordering": "password"}]:
            with self.subTest(params=params):
                self.assertEqual(self.api.get("/api/dashboard/tendencias/", params).status_code, 400)
        self.country.activo = False
        self.country.save()
        self.assertEqual(self.api.get("/api/dashboard/tendencias/", {"paises": "CO"}).status_code, 400)

    def test_empty_summary_uses_null_not_zero_for_missing_risk(self):
        IndiceRiesgo.objects.all().delete()
        self.assertIsNone(self.api.get("/api/dashboard/resumen/").data["promedio_irpc"])

    def test_ranking_delta_means_score_change_and_uses_previous_snapshot(self):
        rows = {row["pais"]: row for row in self.api.get("/api/riesgo/").data["results"]}
        self.assertEqual(rows["CO"]["variacion"], "50.00")
        self.assertEqual(rows["CO"]["tendencia"], "MEJORA")
        self.assertIsNone(rows["BR"]["variacion"])
        self.assertEqual(rows["BR"]["tendencia"], "SIN_HISTORICO")

    def test_every_endpoint_requires_jwt_and_is_read_only(self):
        for endpoint in ["resumen", "mapa", "tendencias"]:
            path = f"/api/dashboard/{endpoint}/"
            self.assertEqual(self.api.post(path, {}, format="json").status_code, 405)
            self.api.force_authenticate(None)
            self.assertEqual(self.api.get(path).status_code, 401)
            self.api.force_authenticate(self.user)
