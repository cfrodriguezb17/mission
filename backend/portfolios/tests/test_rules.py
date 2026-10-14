from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from countries.models import Pais
from portfolios.admin import PortafolioAdmin, PosicionAdmin
from portfolios.models import Portafolio, Posicion
from portfolios.selectors import resumen_portafolio
from portfolios.services import agregar_posicion, editar_portafolio, editar_posicion, cerrar_posicion
from risk.models import IndiceRiesgo

from .base import PortfolioTestCase


class PortfolioRulesTests(PortfolioTestCase):
    def test_database_constraints_and_protected_relations(self):
        for invalid in ({"nombre": "a"}, {"nombre": "   "}, {"nombre": "Compartido"}, {"version": 0}, {"descripcion": "x" * 501}):
            with self.subTest(invalid=invalid), self.assertRaises(IntegrityError), transaction.atomic():
                Portafolio.objects.create(usuario=self.owner, **({"nombre": "Prueba"} | invalid))
        for invalid in ({"monto_inversion_usd": Decimal("999")}, {"monto_inversion_usd": Decimal("10000001")},
                        {"tipo_activo": "INVALID"}, {"fecha_salida": self.position_data()["fecha_entrada"]}):
            with self.subTest(invalid=invalid), self.assertRaises(IntegrityError), transaction.atomic():
                Posicion.objects.create(portafolio=self.public, **self.position_data(**invalid))
        position = Posicion.objects.create(portafolio=self.public, **self.position_data())
        for instance in (self.owner, self.public, self.co):
            with self.subTest(instance=instance), self.assertRaises(ProtectedError):
                instance.delete()
        self.assertTrue(Posicion.objects.filter(pk=position.pk).exists())

    def test_two_active_positions_limit_allows_replacement_after_close(self):
        first, portfolio = agregar_posicion(self.owner, self.public.pk, 1, self.position_data())
        _, portfolio = agregar_posicion(self.other, portfolio.pk, portfolio.version, self.position_data())
        with self.assertRaises(ValidationError):
            agregar_posicion(self.other, portfolio.pk, portfolio.version, self.position_data())
        portfolio.refresh_from_db()
        self.assertEqual((portfolio.version, portfolio.posiciones.count()), (3, 2))
        _, portfolio = cerrar_posicion(self.other, portfolio.pk, first.pk, portfolio.version)
        _, portfolio = agregar_posicion(self.owner, portfolio.pk, portfolio.version, self.position_data())
        self.assertEqual(portfolio.posiciones.filter(fecha_salida__isnull=True).count(), 2)

    def test_editing_country_or_type_rechecks_combination_limit(self):
        for _ in range(2):
            _, self.public = agregar_posicion(self.owner, self.public.pk, self.public.version, self.position_data())
        third, self.public = agregar_posicion(self.owner, self.public.pk, self.public.version,
                                             self.position_data(tipo_activo="COMMODITIES"))
        with self.assertRaises(ValidationError):
            editar_posicion(self.other, self.public.pk, third.pk, self.public.version, {"tipo_activo": "RENTA_FIJA"})
        third.refresh_from_db()
        self.assertEqual(third.tipo_activo, "COMMODITIES")

    def test_capital_limit_applies_to_creation_editing_and_reopening(self):
        for code in ("CO", "BR", "MX", "CL"):
            _, self.public = agregar_posicion(self.owner, self.public.pk, self.public.version,
                self.position_data(pais=Pais.objects.get(pk=code), monto_inversion_usd=Decimal("10000000")))
        small, self.public = agregar_posicion(self.owner, self.public.pk, self.public.version,
            self.position_data(pais=Pais.objects.get(pk="PE"), monto_inversion_usd=Decimal("9999000")))
        sixth, self.public = agregar_posicion(self.owner, self.public.pk, self.public.version,
                                             self.position_data(tipo_activo="COMMODITIES"))
        self.assertEqual(resumen_portafolio(self.public)["total_invertido_usd"], "50000000.00")
        version = self.public.version
        with self.assertRaises(ValidationError):
            agregar_posicion(self.other, self.public.pk, version, self.position_data(tipo_activo="MONEDA"))
        with self.assertRaises(ValidationError):
            editar_posicion(self.other, self.public.pk, small.pk, version, {"monto_inversion_usd": Decimal("10000000")})
        _, self.public = cerrar_posicion(self.other, self.public.pk, sixth.pk, version)
        _, self.public = agregar_posicion(self.other, self.public.pk, self.public.version,
                                         self.position_data(tipo_activo="MONEDA"))
        with self.assertRaises(ValidationError):
            editar_posicion(self.other, self.public.pk, sixth.pk, self.public.version, {"fecha_salida": None})
        sixth.refresh_from_db()
        self.assertIsNotNone(sixth.fecha_salida)

    def test_direct_service_rechecks_actor_role_and_inactive_users(self):
        get_user_model().objects.filter(pk=self.other.pk).update(rol="VIEWER")
        with self.assertRaises(PermissionDenied):
            editar_portafolio(self.other, self.public.pk, 1, {"nombre": "Prohibido"})
        get_user_model().objects.filter(pk=self.owner.pk).update(is_active=False)
        with self.assertRaises(NotFound):
            agregar_posicion(self.owner, self.public.pk, 1, self.position_data())

    def test_inactive_country_is_rejected_even_with_previously_loaded_object(self):
        Pais.objects.filter(pk="CO").update(activo=False)
        with self.assertRaises(ValidationError):
            agregar_posicion(self.owner, self.public.pk, 1, self.position_data())
        self.public.refresh_from_db()
        self.assertEqual(self.public.version, 1)

    def test_editing_rechecks_usd_currency_and_dates(self):
        position, portfolio = agregar_posicion(self.owner, self.public.pk, 1, self.position_data(tipo_activo="MONEDA"))
        with self.assertRaises(ValidationError):
            editar_posicion(self.owner, portfolio.pk, position.pk, portfolio.version, {"pais": Pais.objects.get(pk="EC")})
        with self.assertRaises(ValidationError):
            editar_posicion(self.owner, portfolio.pk, position.pk, portfolio.version, {"fecha_entrada": timezone.localdate() + timedelta(days=1)})
        with self.assertRaises(ValidationError):
            cerrar_posicion(self.owner, portfolio.pk, position.pk, portfolio.version, position.fecha_entrada)

    def test_summary_weights_latest_risk_and_excludes_closed_positions(self):
        for code, score in (("CO", 90), ("BR", 30)):
            IndiceRiesgo.objects.create(pais_id=code, indice_compuesto=10, score_economico=10,
                score_cambiario=10, score_estabilidad=10, version_formula="test", detalle_calculo={})
            IndiceRiesgo.objects.create(pais_id=code, indice_compuesto=score, score_economico=score,
                score_cambiario=score, score_estabilidad=score, version_formula="test", detalle_calculo={})
        _, self.public = agregar_posicion(self.owner, self.public.pk, self.public.version, self.position_data())
        _, self.public = agregar_posicion(self.owner, self.public.pk, self.public.version,
            self.position_data(pais=Pais.objects.get(pk="BR"), monto_inversion_usd=Decimal("3000"), tipo_activo="MONEDA"))
        closed, self.public = agregar_posicion(self.owner, self.public.pk, self.public.version,
            self.position_data(monto_inversion_usd=Decimal("10000000"), tipo_activo="COMMODITIES"))
        _, self.public = cerrar_posicion(self.owner, self.public.pk, closed.pk, self.public.version)
        summary = resumen_portafolio(self.public)
        self.assertEqual(summary["total_invertido_usd"], "4000.00")
        self.assertEqual(summary["riesgo_promedio_ponderado"], "45.00")
        self.assertEqual(summary["posiciones_activas"], 2)
        self.assertFalse(summary["riesgo_incompleto"])
        self.assertEqual({row["codigo"]: row["porcentaje"] for row in summary["distribucion_por_pais"]}, {"CO": "25.00", "BR": "75.00"})
        self.assertEqual({row["codigo"] for row in summary["distribucion_por_riesgo"]}, {"BAJO", "ALTO"})

    def test_summary_marks_missing_risk_without_treating_it_as_zero(self):
        empty = resumen_portafolio(self.public)
        self.assertEqual(empty["total_invertido_usd"], "0.00")
        self.assertIsNone(empty["riesgo_promedio_ponderado"])
        IndiceRiesgo.objects.create(pais_id="CO", indice_compuesto=80, score_economico=80,
            score_cambiario=80, score_estabilidad=80, version_formula="test", detalle_calculo={})
        _, self.public = agregar_posicion(self.owner, self.public.pk, 1, self.position_data())
        _, self.public = agregar_posicion(self.owner, self.public.pk, self.public.version,
                                         self.position_data(pais=Pais.objects.get(pk="BR"), monto_inversion_usd=Decimal("3000")))
        summary = resumen_portafolio(self.public)
        self.assertEqual(summary["riesgo_promedio_ponderado"], "80.00")
        self.assertTrue(summary["riesgo_incompleto"])
        self.assertEqual(summary["monto_sin_riesgo_usd"], "3000.00")
        self.assertEqual(summary["paises_sin_riesgo"], ["BR"])

    def test_seed_is_repeatable_and_preserves_existing_edits_and_users(self):
        users_before = get_user_model().objects.count()
        call_command("seed_portafolios", usuario=self.owner.email, stdout=StringIO())
        examples = Portafolio.objects.filter(usuario=self.owner, nombre__startswith="Demo")
        self.assertEqual(examples.count(), 2)
        self.assertEqual(Posicion.objects.count(), 4)
        example = examples.get(es_publico=True)
        editar_portafolio(self.other, example.pk, example.version, {"descripcion": "Edición real"})
        call_command("seed_portafolios", usuario=self.owner.email, stdout=StringIO())
        example.refresh_from_db()
        self.assertEqual(example.descripcion, "Edición real")
        self.assertEqual((Posicion.objects.count(), get_user_model().objects.count()), (4, users_before))

    def test_seed_rejects_viewer_missing_user_and_rolls_back_partial_dataset(self):
        for email in (self.viewer.email, "missing@example.com"):
            with self.assertRaises(CommandError):
                call_command("seed_portafolios", usuario=email, stdout=StringIO())
        Pais.objects.filter(pk="PE").update(activo=False)
        with self.assertRaises(CommandError):
            call_command("seed_portafolios", usuario=self.owner.email, stdout=StringIO())
        self.assertEqual((Portafolio.objects.count(), Posicion.objects.count()), (2, 0))

    def test_admin_cannot_bypass_api_constraints_and_hides_private_rows(self):
        from django.contrib.admin.sites import AdminSite

        request = RequestFactory().get("/admin/")
        request.user = self.other
        for model, admin_class in ((Portafolio, PortafolioAdmin), (Posicion, PosicionAdmin)):
            registered = admin_class(model, AdminSite())
            self.assertFalse(registered.has_add_permission(request))
            self.assertFalse(registered.has_change_permission(request))
            self.assertFalse(registered.has_delete_permission(request))
        registered = PortafolioAdmin(Portafolio, AdminSite())
        self.assertEqual(list(registered.get_queryset(request)), [self.public])
