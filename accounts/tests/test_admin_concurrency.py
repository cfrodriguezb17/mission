from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic
from unittest.mock import patch

from django.contrib.admin.options import ModelAdmin
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AdminPasswordChangeForm
from django.contrib.auth.hashers import make_password
from django.db import connection, connections
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.admin import AccountsUserAdmin
from accounts.serializers import ProfileSerializer
from audit.models import LogActividad

User = get_user_model()


class AdminConcurrencyTests(TransactionTestCase):
    password = "OriginalClave!739x"
    new_password = "NuevaClave!927x"

    def setUp(self):
        self.admin = User.objects.create_superuser(email="admin-race@example.com", password="AdminClave!842z")
        self.user = User.objects.create_user(email="user-race@example.com", nombre_completo="Usuario",
                                             password=self.password, rol="ANALISTA", is_staff=True)
        self.client.force_login(self.admin)
        self.change_url = reverse("admin:accounts_user_change", args=[self.user.pk])
        self.password_url = reverse("admin:auth_user_password_change", args=[self.user.pk])

    def admin_post(self, password=False):
        if password:
            return self.client.post(self.password_url, {
                "password1": self.new_password, "password2": self.new_password,
                "usable_password": "true", "set-password": "Guardar",
            })
        return self.client.post(self.change_url, {
            "email": self.user.email, "nombre_completo": self.user.nombre_completo,
            "rol": "VIEWER", "is_active": "on", "_save": "Guardar",
        })

    def update_in_other_connection(self, **changes):
        def update():
            try:
                return User.objects.filter(pk=self.user.pk).update(**changes)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=1) as pool:
            self.assertEqual(pool.submit(update).result(timeout=10), 1)

    def interleave_before_lock(self, *, reset_password=False, **changes):
        get_object = ModelAdmin.get_object
        changed = False

        def interleave(model_admin, request, object_id, from_field=None):
            nonlocal changed
            instance = get_object(model_admin, request, object_id, from_field)
            if instance is not None and instance.pk == self.user.pk and not changed:
                changed = True
                self.update_in_other_connection(**changes)
            return instance

        with patch.object(ModelAdmin, "get_object", interleave):
            response = self.admin_post(password=reset_password)
        self.assertTrue(changed)
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()

    def test_role_edit_preserves_password_committed_before_lock(self):
        self.interleave_before_lock(password=make_password(self.new_password))
        self.assertEqual(self.user.rol, "VIEWER")
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertFalse(self.user.check_password(self.password))

    def test_password_reset_preserves_profile_and_privileges_committed_before_lock(self):
        self.interleave_before_lock(reset_password=True, nombre_completo="Nombre actualizado", rol="VIEWER",
                                    is_active=False, is_staff=False)
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertEqual(self.user.nombre_completo, "Nombre actualizado")
        self.assertEqual(self.user.rol, "VIEWER")
        self.assertFalse(self.user.is_active)
        self.assertFalse(self.user.is_staff)

    def concurrent_profile(self, *, password_reset):
        token = str(RefreshToken.for_user(self.user).access_token)
        ready = Event()
        profile_update = ProfileSerializer.update
        worker_pid = []
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_backend_pid()")
            admin_pid = cursor.fetchone()[0]

        def announce(serializer, instance, data):
            # El JWT ya se autenticó con la contraseña anterior al reset.
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                worker_pid.append(cursor.fetchone()[0])
            ready.set()
            return profile_update(serializer, instance, data)

        def edit_profile():
            try:
                api = APIClient()
                api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                return api.put("/api/auth/me/", {
                    "email": self.user.email, "nombre_completo": "Nombre desde perfil",
                    "password": "ClaveDesdePerfil!842z",
                }, format="json")
            finally:
                connections.close_all()

        futures = []
        blocked = False
        with ThreadPoolExecutor(max_workers=1) as pool:
            def before_admin_save(save, *args, **kwargs):
                nonlocal blocked
                futures.append(pool.submit(edit_profile))
                self.assertTrue(ready.wait(timeout=10))
                deadline = monotonic() + 10
                while monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT %s = ANY(pg_blocking_pids(%s))", [admin_pid, worker_pid[0]])
                        blocked = cursor.fetchone()[0]
                    if blocked or futures[0].done():
                        break
                    Event().wait(0.01)
                return save(*args, **kwargs)

            save_model = AccountsUserAdmin.save_model
            save_password = AdminPasswordChangeForm.save

            def save_user(model_admin, *args, **kwargs):
                return before_admin_save(save_model, model_admin, *args, **kwargs)

            def reset_password(form, *args, **kwargs):
                return before_admin_save(save_password, form, *args, **kwargs)

            target = AdminPasswordChangeForm if password_reset else AccountsUserAdmin
            method = "save" if password_reset else "save_model"
            replacement = reset_password if password_reset else save_user
            with patch.object(ProfileSerializer, "update", announce), patch.object(target, method, replacement):
                admin_response = self.admin_post(password=password_reset)
                profile_response = futures[0].result(timeout=10)
        self.assertTrue(blocked, "El perfil debe esperar al bloqueo de fila del administrador.")
        self.assertEqual(admin_response.status_code, 302)
        self.user.refresh_from_db()
        return profile_response

    def test_role_edit_serializes_with_profile_password_change(self):
        response = self.concurrent_profile(password_reset=False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rol"], "VIEWER")
        self.assertEqual(self.user.rol, "VIEWER")
        self.assertTrue(self.user.check_password("ClaveDesdePerfil!842z"))
        self.assertEqual(self.user.nombre_completo, "Nombre desde perfil")
        self.assertEqual(LogActividad.objects.filter(usuario=self.user, accion="EDITAR").count(), 1)

    def test_admin_password_reset_rejects_profile_authenticated_before_reset(self):
        response = self.concurrent_profile(password_reset=True)
        self.assertEqual(response.status_code, 401)
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertEqual(self.user.nombre_completo, "Usuario")
        self.assertFalse(LogActividad.objects.filter(usuario=self.user, accion="EDITAR").exists())
        self.assertTrue(LogActividad.objects.filter(usuario=self.admin, entidad_id=str(self.user.pk),
                                                   detalle__credenciales_actualizadas=True).exists())
