from audit.models import LogActividad
from portfolios.models import Portafolio

from .base import PortfolioTestCase


class PortfolioNameValidationTests(PortfolioTestCase):
    url = "/api/portafolios/validar-nombre/"

    def check_name(self, nombre, **params):
        return self.api.get(self.url, {"nombre": nombre, **params})

    def test_available_name_is_trimmed_and_query_does_not_write(self):
        portfolios = list(Portafolio.objects.values())
        audits = LogActividad.objects.count()
        response = self.check_name("  Latam  ")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"nombre": "Latam", "disponible": True})
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(list(Portafolio.objects.values()), portfolios)
        self.assertEqual(LogActividad.objects.count(), audits)

    def test_existing_name_is_unavailable_and_case_is_significant(self):
        self.assertEqual(self.check_name(" Compartido ").data, {"nombre": "Compartido", "disponible": False})
        self.assertTrue(self.check_name("compartido").data["disponible"])
        response = self.api.post("/api/portafolios/", {"nombre": "compartido"}, format="json")
        self.assertEqual(response.status_code, 201)

    def test_deleted_name_stays_reserved_but_cannot_be_excluded(self):
        self.assertEqual(self.api.delete(f"/api/portafolios/{self.private.pk}/", {"version": 1}, format="json").status_code, 204)
        self.assertFalse(self.check_name(self.private.nombre).data["disponible"])
        self.assertEqual(self.check_name(self.private.nombre, excluir=self.private.pk).status_code, 404)
        self.assertEqual(self.api.post("/api/portafolios/", {"nombre": self.private.nombre}, format="json").status_code, 400)

    def test_other_owners_names_do_not_block_creation(self):
        self.api.force_authenticate(self.other)
        self.assertTrue(self.check_name(self.private.nombre).data["disponible"])
        self.assertTrue(self.check_name(self.public.nombre).data["disponible"])
        response = self.api.post("/api/portafolios/", {"nombre": self.private.nombre}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["usuario"], self.other.pk)

    def test_own_edit_excludes_only_the_portfolio_being_edited(self):
        self.assertTrue(self.check_name(self.public.nombre, excluir=self.public.pk).data["disponible"])
        self.assertFalse(self.check_name(self.private.nombre, excluir=self.public.pk).data["disponible"])
        response = self.api.put(f"/api/portafolios/{self.public.pk}/", {"version": 1, "nombre": self.public.nombre}, format="json")
        self.assertEqual(response.status_code, 200)

    def test_shared_edit_uses_actual_owner_including_private_and_deleted_names(self):
        Portafolio.objects.create(usuario=self.owner, nombre="Reservado", activo=False)
        Portafolio.objects.create(usuario=self.other, nombre="Solo colaborador")
        self.api.force_authenticate(self.other)
        self.assertTrue(self.check_name(self.public.nombre, excluir=self.public.pk).data["disponible"])
        self.assertTrue(self.check_name("Solo colaborador", excluir=self.public.pk).data["disponible"])
        for name in (self.private.nombre, "Reservado"):
            with self.subTest(name=name):
                response = self.check_name(name, excluir=self.public.pk)
                self.assertEqual(response.data, {"nombre": name, "disponible": False})
                self.assertEqual(self.api.put(f"/api/portafolios/{self.public.pk}/", {"version": 1, "nombre": name}, format="json").status_code, 400)

    def test_admin_edit_uses_actual_owner_including_private_portfolios(self):
        self.api.force_authenticate(self.admin)
        self.assertTrue(self.check_name(self.private.nombre).data["disponible"])
        self.assertTrue(self.check_name(self.private.nombre, excluir=self.private.pk).data["disponible"])
        self.assertFalse(self.check_name(self.public.nombre, excluir=self.private.pk).data["disponible"])

    def test_private_and_unknown_exclusions_return_same_not_found(self):
        self.api.force_authenticate(self.other)
        private = self.check_name("Latam", excluir=self.private.pk)
        missing = self.check_name("Latam", excluir=999999)
        self.assertEqual((private.status_code, missing.status_code), (404, 404))
        self.assertEqual(private.data, missing.data)
        self.assertNotIn(self.private.nombre, str(private.data))

    def test_free_owner_parameters_are_rejected(self):
        self.api.force_authenticate(self.other)
        for field in ("usuario", "usuario_id", "propietario"):
            with self.subTest(field=field):
                response = self.check_name(self.private.nombre, **{field: self.owner.pk})
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data["error"]["detalles"])

    def test_invalid_names_match_write_validation(self):
        for data in ({}, {"nombre": ""}, {"nombre": "  "}, {"nombre": " ab "}, {"nombre": "x" * 101}):
            with self.subTest(data=data):
                checked = self.api.get(self.url, data)
                created = self.api.post("/api/portafolios/", data, format="json")
                self.assertEqual((checked.status_code, created.status_code), (400, 400))
                self.assertEqual(checked.data["nombre"], created.data["nombre"])
                self.assertEqual(checked.data["error"]["codigo"], "validacion")

    def test_valid_length_boundaries_after_trimming(self):
        for name in ("abc", "x" * 100):
            with self.subTest(length=len(name)):
                response = self.check_name(f"  {name}  ")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, {"nombre": name, "disponible": True})

    def test_invalid_exclusions_are_rejected(self):
        for value in ("", "0", "-1", "abc", "true", "1.5", "null"):
            with self.subTest(value=value):
                response = self.check_name("Latam", excluir=value)
                self.assertEqual(response.status_code, 400)
                self.assertIn("excluir", response.data["error"]["detalles"])

    def test_authentication_and_writer_permissions(self):
        self.api.force_authenticate(None)
        self.assertEqual(self.check_name("Latam").status_code, 401)
        self.api.force_authenticate(self.viewer)
        own = Portafolio.objects.create(usuario=self.viewer, nombre="Del lector")
        for params in ({}, {"excluir": own.pk}, {"excluir": self.public.pk}):
            with self.subTest(params=params):
                self.assertEqual(self.check_name("Latam", **params).status_code, 403)
        self.assertEqual(self.check_name("Latam", excluir=self.private.pk).status_code, 404)

    def test_inactive_actor_cannot_check_availability(self):
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        self.assertEqual(self.check_name("Latam").status_code, 403)
        self.assertEqual(self.check_name("Latam", excluir=self.public.pk).status_code, 404)

    def test_availability_does_not_reserve_name_for_later_create_or_edit(self):
        self.assertTrue(self.check_name("Latam").data["disponible"])
        self.assertTrue(self.check_name("Latam", excluir=self.public.pk).data["disponible"])
        Portafolio.objects.create(usuario=self.owner, nombre="Latam")
        self.assertEqual(self.api.post("/api/portafolios/", {"nombre": "Latam"}, format="json").status_code, 400)
        self.assertEqual(self.api.put(f"/api/portafolios/{self.public.pk}/", {"version": 1, "nombre": "Latam"}, format="json").status_code, 400)
        self.public.refresh_from_db()
        self.assertEqual((self.public.nombre, self.public.version), ("Compartido", 1))
