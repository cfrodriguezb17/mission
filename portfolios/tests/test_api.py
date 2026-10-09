from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from portfolios.models import Portafolio, Posicion
from portfolios.services import agregar_posicion

from .base import PortfolioTestCase


class PortfolioAPITests(PortfolioTestCase):
    def url(self, portfolio=None):
        return f"/api/portafolios/{(portfolio or self.public).pk}/"

    def test_authentication_and_viewer_cannot_write_even_owned_portfolio(self):
        self.api.force_authenticate(None)
        self.assertEqual(self.api.get("/api/portafolios/").status_code, 401)
        self.api.force_authenticate(self.viewer)
        owned = Portafolio.objects.create(usuario=self.viewer, nombre="Del lector")
        self.assertEqual(self.api.post("/api/portafolios/", {"nombre": "Nuevo"}, format="json").status_code, 403)
        for portfolio in (self.public, owned):
            self.assertEqual(self.api.put(self.url(portfolio), {"version": 1, "nombre": "Cambio"}, format="json").status_code, 403)
            self.assertEqual(self.api.delete(self.url(portfolio), {"version": 1}, format="json").status_code, 403)
            self.assertEqual(self.api.post(self.url(portfolio) + "posiciones/", self.api_position(), format="json").status_code, 403)

    def test_list_and_detail_do_not_leak_private_portfolios(self):
        self.api.force_authenticate(self.other)
        data = self.api.get("/api/portafolios/").data
        self.assertEqual([row["id"] for row in data["results"]], [self.public.pk])
        self.assertEqual(self.api.get(self.url(self.private)).status_code, 404)
        self.assertEqual(self.api.get(self.url(self.private) + "resumen/").status_code, 404)
        self.assertEqual(self.api.put(self.url(self.private), {"version": 1, "nombre": "Cambio"}, format="json").status_code, 404)
        self.api.force_authenticate(self.admin)
        self.assertEqual(self.api.get("/api/portafolios/").data["count"], 2)
        self.assertEqual(self.api.get(self.url(self.private)).status_code, 200)

    def test_analyst_edits_shared_portfolio_without_changing_owner(self):
        self.api.force_authenticate(self.other)
        data = self.api.get(self.url()).data
        self.assertTrue(data["puede_editar"])
        self.assertFalse(data["puede_eliminar"])
        self.assertFalse(data["puede_cambiar_visibilidad"])
        response = self.api.put(self.url(), {"version": 1, "nombre": "Editado por colega", "es_publico": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.data["version"], response.data["usuario"]), (2, self.owner.pk))
        self.assertEqual(response.data["resumen"]["version"], 2)

    def test_only_owner_or_admin_changes_visibility_or_deletes(self):
        self.api.force_authenticate(self.other)
        self.assertEqual(self.api.put(self.url(), {"version": 1, "es_publico": False}, format="json").status_code, 403)
        self.assertEqual(self.api.delete(self.url(), {"version": 1}, format="json").status_code, 403)
        self.api.force_authenticate(self.admin)
        response = self.api.put(self.url(self.private), {"version": 1, "es_publico": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.api.force_authenticate(self.owner)
        self.assertEqual(self.api.put(self.url(), {"version": 1, "es_publico": False}, format="json").status_code, 200)
        self.assertEqual(self.api.delete(self.url(), {"version": 2}, format="json").status_code, 204)
        self.public.refresh_from_db()
        self.assertFalse(self.public.activo)
        self.assertEqual(self.public.version, 3)

    def test_stale_version_returns_409_and_preserves_first_change(self):
        self.assertEqual(self.api.put(self.url(), {"version": 1, "nombre": "Primer cambio"}, format="json").status_code, 200)
        self.api.force_authenticate(self.other)
        response = self.api.put(self.url(), {"version": 1, "nombre": "Segundo cambio"}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["codigo"], "version_desactualizada")
        self.assertEqual(response.data["version_actual"], 2)
        self.public.refresh_from_db()
        self.assertEqual((self.public.nombre, self.public.version), ("Primer cambio", 2))

    def test_version_required_for_all_mutations_and_readonly_fields_rejected(self):
        for body in ({"nombre": "Sin version"}, {"version": 0}, {"version": True}, {"version": "x"},
                     {"version": 1, "usuario": self.other.pk}, {"version": 1, "activo": False}):
            with self.subTest(body=body):
                self.assertEqual(self.api.put(self.url(), body, format="json").status_code, 400)
        self.assertEqual(self.api.delete(self.url(), {}, format="json").status_code, 400)
        self.assertEqual(self.api.post(self.url() + "posiciones/", {k: v for k, v in self.api_position().items() if k != "version"}, format="json").status_code, 400)
        self.assertEqual(self.api.post("/api/portafolios/", {"nombre": "Otro", "usuario": self.other.pk}, format="json").status_code, 400)

    def test_create_validates_name_description_and_owner_uniqueness(self):
        for body in ({"nombre": "a"}, {"nombre": "   "}, {"nombre": "x" * 101}, {"nombre": "Largo", "descripcion": "x" * 501}):
            with self.subTest(body=body):
                self.assertEqual(self.api.post("/api/portafolios/", body, format="json").status_code, 400)
        response = self.api.post("/api/portafolios/", {"nombre": "  Mi inversión  "}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual((response.data["nombre"], response.data["usuario"], response.data["version"]), ("Mi inversión", self.owner.pk, 1))
        self.assertEqual(self.api.post("/api/portafolios/", {"nombre": "Mi inversión"}, format="json").status_code, 400)
        self.api.force_authenticate(self.other)
        self.assertEqual(self.api.post("/api/portafolios/", {"nombre": "Mi inversión"}, format="json").status_code, 201)

    def test_rename_uses_owner_uniqueness_and_failed_write_keeps_version(self):
        response = self.api.put(self.url(), {"version": 1, "nombre": self.private.nombre}, format="json")
        self.assertEqual(response.status_code, 400)
        self.public.refresh_from_db()
        self.assertEqual((self.public.version, self.public.nombre), (1, "Compartido"))

    def test_filters_search_ordering_and_pagination(self):
        for index in range(22):
            Portafolio.objects.create(usuario=self.owner, nombre=f"Inversión {index:02}")
        response = self.api.get("/api/portafolios/?search=Inversión&ordering=nombre&page_size=2")
        self.assertEqual(response.data["count"], 22)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertIsNotNone(response.data["next"])
        self.assertEqual(response.data["results"][0]["nombre"], "Inversión 00")
        self.assertEqual(len(self.api.get("/api/portafolios/").data["results"]), 20)
        self.api.force_authenticate(self.other)
        self.assertEqual(self.api.get("/api/portafolios/?propios=true").data["count"], 0)
        self.assertEqual(self.api.get("/api/portafolios/?es_publico=true&propios=false").data["count"], 1)
        for query in ("es_publico=bad", "propios=bad", "ordering=usuario", "ordering="):
            self.assertEqual(self.api.get("/api/portafolios/?" + query).status_code, 400)

    def test_shared_position_changes_increment_portfolio_version_and_close_preserves_row(self):
        self.api.force_authenticate(self.other)
        response = self.api.post(self.url() + "posiciones/", self.api_position(), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["version_portafolio"], 2)
        position_url = self.url() + f"posiciones/{response.data['id']}/"
        self.assertEqual(self.api.put(position_url, {"version": 1, "notas": "Viejo"}, format="json").status_code, 409)
        response = self.api.put(position_url, {"version": 2, "monto_inversion_usd": "2500.50"}, format="json")
        self.assertEqual((response.status_code, response.data["version_portafolio"]), (200, 3))
        response = self.api.delete(position_url, {"version": 3}, format="json")
        self.assertEqual((response.status_code, response.data["version_portafolio"]), (200, 4))
        position = Posicion.objects.get(pk=response.data["id"])
        self.assertEqual(position.fecha_salida, timezone.localdate())
        detail = self.api.get(self.url()).data
        self.assertEqual(len(detail["posiciones"]), 1)
        self.assertEqual(detail["resumen"]["total_invertido_usd"], "0.00")
        self.assertEqual(self.api.delete(position_url, {"version": 4}, format="json").status_code, 400)

    def test_viewer_cannot_edit_or_close_positions(self):
        position, portfolio = agregar_posicion(self.owner, self.public.pk, 1, self.position_data())
        self.api.force_authenticate(self.viewer)
        url = self.url() + f"posiciones/{position.pk}/"
        self.assertEqual(self.api.put(url, {"version": portfolio.version, "notas": "Cambio"}, format="json").status_code, 403)
        self.assertEqual(self.api.delete(url, {"version": portfolio.version}, format="json").status_code, 403)

    def test_cannot_target_another_portfolios_position(self):
        position, _ = agregar_posicion(self.owner, self.private.pk, 1, self.position_data())
        url = self.url() + f"posiciones/{position.pk}/"
        self.assertEqual(self.api.put(url, {"version": 1, "notas": "Cruce"}, format="json").status_code, 404)
        self.assertEqual(self.api.delete(url, {"version": 1}, format="json").status_code, 404)

    def test_deletion_keeps_positions_and_hides_portfolio(self):
        position, portfolio = agregar_posicion(self.owner, self.public.pk, 1, self.position_data())
        self.assertEqual(self.api.delete(self.url(), {"version": portfolio.version}, format="json").status_code, 204)
        self.assertTrue(Posicion.objects.filter(pk=position.pk).exists())
        self.assertEqual(self.api.get(self.url()).status_code, 404)
        self.assertEqual(self.api.get(self.url() + "resumen/").status_code, 404)
        self.assertEqual(self.api.get("/api/portafolios/").data["count"], 1)
        self.assertEqual(self.api.post(self.url() + "posiciones/", self.api_position(), format="json").status_code, 404)

    def test_position_validation_errors_and_failed_writes_preserve_version(self):
        examples = [
            {"monto_inversion_usd": "999.99"}, {"monto_inversion_usd": "10000000.01"},
            {"monto_inversion_usd": "NaN"}, {"monto_inversion_usd": "1000.001"},
            {"fecha_entrada": (timezone.localdate() + timedelta(days=1)).isoformat()},
            {"fecha_salida": (timezone.localdate() - timedelta(days=2)).isoformat()},
            {"tipo_activo": "INVALID"}, {"pais": "ZZ"}, {"pais": "EC", "tipo_activo": "MONEDA"},
            {"notas": "x" * 201}, {"usuario": self.other.pk}, {"portafolio": self.private.pk},
        ]
        for invalid in examples:
            with self.subTest(invalid=invalid):
                self.assertEqual(self.api.post(self.url() + "posiciones/", self.api_position() | invalid, format="json").status_code, 400)
        self.public.refresh_from_db()
        self.assertEqual((self.public.version, self.public.posiciones.count()), (1, 0))

    def test_same_day_close_requires_explicit_later_exit_date(self):
        position, portfolio = agregar_posicion(self.owner, self.public.pk, 1, self.position_data(fecha_entrada=timezone.localdate()))
        url = self.url() + f"posiciones/{position.pk}/"
        self.assertEqual(self.api.delete(url, {"version": portfolio.version}, format="json").status_code, 400)
        position.refresh_from_db()
        self.assertIsNone(position.fecha_salida)

    def test_django_superuser_does_not_bypass_business_role(self):
        user = get_user_model().objects.create_superuser(email="portfolio-super@example.com", password="SuperClave!872z", rol="VIEWER")
        self.api.force_authenticate(user)
        self.assertEqual(self.api.post("/api/portafolios/", {"nombre": "Prohibido"}, format="json").status_code, 403)
