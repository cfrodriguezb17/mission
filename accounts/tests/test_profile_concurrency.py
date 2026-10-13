from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.serializers import ProfileSerializer
from audit.models import LogActividad

User = get_user_model()


class ProfileSecurityUpdateTests(APITestCase):
    password = "OriginalClave!739x"

    def setUp(self):
        self.user = User.objects.create_user(
            email="profile-race@example.com", nombre_completo="Nombre original",
            password=self.password, rol="ANALISTA", is_staff=True, is_superuser=True,
        )
        self.refresh = str(RefreshToken.for_user(self.user))
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {RefreshToken(self.refresh).access_token}",
        )

    def edit_after_change(self, changes, **payload):
        update = ProfileSerializer.update

        def interleave(serializer, instance, validated_data):
            # Cambiar la fila después de autenticar y validar, antes de guardarla.
            User.objects.filter(pk=instance.pk).update(**changes)
            return update(serializer, instance, validated_data)

        with patch.object(ProfileSerializer, "update", interleave):
            return self.client.put("/api/auth/me/", {
                "email": self.user.email, "nombre_completo": "Nombre editado", **payload,
            }, format="json")

    def test_profile_preserves_concurrent_role_and_privilege_revocation(self):
        response = self.edit_after_change({
            "rol": "VIEWER", "is_staff": False, "is_superuser": False,
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.rol, "VIEWER")
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertTrue(self.user.check_password(self.password))
        self.assertEqual(self.user.nombre_completo, "Nombre editado")
        self.assertEqual(response.data["rol"], "VIEWER")
        event = LogActividad.objects.get(accion="EDITAR", usuario=self.user)
        self.assertFalse(event.detalle["credenciales_actualizadas"])

    def assert_password_reset_survives(self, **payload):
        new_password = "ResetAdministrativo!842z"
        response = self.edit_after_change({"password": make_password(new_password)}, **payload)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["error"]["codigo"], "autenticacion")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertFalse(self.user.check_password(self.password))
        self.assertEqual(self.user.nombre_completo, "Nombre original")
        self.assertFalse(LogActividad.objects.filter(accion="EDITAR").exists())
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post("/api/auth/refresh/", {
            "refresh": self.refresh,
        }, format="json").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login/", {
            "email": self.user.email, "password": new_password,
        }, format="json").status_code, 200)

    def test_profile_rejects_credentials_changed_after_authentication(self):
        self.assert_password_reset_survives()

    def test_password_change_cannot_overwrite_concurrent_password_reset(self):
        self.assert_password_reset_survives(password="ClaveDePeticion!927x")

    def assert_deactivation_survives(self, **payload):
        response = self.edit_after_change({"is_active": False}, **payload)
        self.assertEqual(response.status_code, 401)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertTrue(self.user.check_password(self.password))
        self.assertEqual(self.user.nombre_completo, "Nombre original")
        self.assertFalse(LogActividad.objects.filter(accion="EDITAR").exists())

    def test_profile_rejects_deactivation_after_authentication(self):
        self.assert_deactivation_survives()

    def test_password_change_rejects_deactivation_after_authentication(self):
        self.assert_deactivation_survives(password="ClaveDePeticion!927x")

    def test_concurrent_duplicate_email_returns_validation_error(self):
        update = ProfileSerializer.update

        def interleave(serializer, instance, validated_data):
            User.objects.create_user(email="taken@example.com", nombre_completo="Otro usuario")
            return update(serializer, instance, validated_data)

        with patch.object(ProfileSerializer, "update", interleave):
            response = self.client.put("/api/auth/me/", {
                "email": "taken@example.com", "nombre_completo": "Nombre editado",
            }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["codigo"], "validacion")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "profile-race@example.com")
        self.assertFalse(LogActividad.objects.filter(accion="EDITAR").exists())


class ConcurrentPasswordChangeTests(TransactionTestCase):
    def test_two_authenticated_password_changes_only_one_succeeds(self):
        user = User.objects.create_user(
            email="password-race@example.com", nombre_completo="Usuario concurrente",
            password="OriginalClave!739x",
        )
        token = str(RefreshToken.for_user(user).access_token)
        barrier = Barrier(2)
        update = ProfileSerializer.update
        passwords = ["NuevaClaveUno!927x", "NuevaClaveDos!842z"]

        def synchronized_update(serializer, instance, validated_data):
            # Ambos requests ya autenticaron con el mismo hash antes de competir.
            barrier.wait(timeout=10)
            return update(serializer, instance, validated_data)

        def change(index):
            try:
                api = APIClient()
                api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = api.put("/api/auth/me/", {
                    "email": user.email, "nombre_completo": user.nombre_completo,
                    "password": passwords[index],
                }, format="json")
                return response.status_code, index
            finally:
                connections.close_all()

        with patch.object(ProfileSerializer, "update", synchronized_update):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(change, index) for index in range(2)]
                results = [future.result(timeout=20) for future in futures]
        self.assertEqual(sorted(code for code, _ in results), [200, 401])
        winner = next(index for code, index in results if code == 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password(passwords[winner]))
        self.assertEqual(LogActividad.objects.filter(accion="EDITAR", usuario=user).count(), 1)
