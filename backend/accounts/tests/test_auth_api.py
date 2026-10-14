from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class AuthenticationAPITests(APITestCase):
    password = "ClaveSegura!739x"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="ana@example.com", nombre_completo="Ana Pérez", password=cls.password,
        )
        cls.other = User.objects.create_user(
            email="otra@example.com", nombre_completo="Otra Persona", password=cls.password,
        )
        cls.superuser = User.objects.create_superuser(
            email="admin@example.com", password=cls.password,
        )

    def url(self, name):
        return reverse(f"accounts:{name}")

    def payload(self, **overrides):
        return {
            "email": "nueva@example.com", "nombre_completo": "Nueva Persona",
            "password": self.password, **overrides,
        }

    def login(self, email=None, password=None):
        return self.client.post(self.url("login"), {
            "email": email or self.user.email,
            "password": password or self.password,
        }, format="json")

    def authenticate(self):
        response = self.login()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return response.data

    def test_register_persists_viewer_and_never_returns_password(self):
        response = self.client.post(self.url("register"), self.payload(
            email="  NUEVA@Example.COM  ", rol="ADMIN", activo=False,
            is_active=False, is_staff=True, is_superuser=True, username="intruso",
        ), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="nueva@example.com")
        self.assertEqual(user.get_username(), user.email)
        self.assertEqual(user.rol, User.Rol.VIEWER)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password(self.password))
        self.assertNotEqual(user.password, self.password)
        self.assertEqual(response.data["rol"], "VIEWER")
        self.assertTrue(response.data["activo"])
        self.assertNotIn("password", response.data)
        self.assertNotIn("username", response.data)

    def test_register_requires_email_name_and_password(self):
        for field in ("email", "nombre_completo", "password"):
            for value in ("missing", "", None):
                with self.subTest(field=field, value=value):
                    data = self.payload()
                    if value == "missing":
                        data.pop(field)
                    else:
                        data[field] = value
                    response = self.client.post(self.url("register"), data, format="json")
                    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                    self.assertIn(field, response.data)
        self.assertFalse(User.objects.filter(email="nueva@example.com").exists())

    def test_register_rejects_duplicate_normalized_email(self):
        response = self.client.post(self.url("register"), self.payload(
            email="  ANA@EXAMPLE.COM  ",
        ), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)
        self.assertEqual(User.objects.filter(email=self.user.email).count(), 1)

    def test_register_rejects_invalid_email(self):
        response = self.client.post(self.url("register"), self.payload(
            email="sin-email",
        ), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_register_applies_django_password_policy(self):
        for password in ("abc", "123456789", "password", "nueva@example.com"):
            with self.subTest(password=password):
                response = self.client.post(self.url("register"), self.payload(
                    password=password,
                ), format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("password", response.data)

    def test_login_by_normalized_email_returns_token_pair(self):
        response = self.login(email="  ANA@EXAMPLE.COM  ")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {"access", "refresh"})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        profile = self.client.get(self.url("me"))
        self.assertEqual(profile.status_code, status.HTTP_200_OK)
        self.assertEqual(profile.data["email"], self.user.email)
        self.assertNotIn("password", profile.data)

    def test_superuser_can_login_with_email_and_password(self):
        response = self.login(email=self.superuser.email)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(self.superuser.is_staff)
        self.assertTrue(self.superuser.is_superuser)
        self.assertTrue(self.superuser.check_password(self.password))

    def test_login_rejects_wrong_password_and_unknown_email(self):
        for data in ({"email": self.user.email, "password": "Incorrecta!734"},
                     {"email": "ausente@example.com", "password": self.password}):
            with self.subTest(email=data["email"]):
                response = self.client.post(self.url("login"), data, format="json")
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
                self.assertNotIn("access", response.data)

    def test_register_and_login_preserve_password_whitespace(self):
        password = "  EspaciosClave!734  "
        created = self.client.post(self.url("register"), self.payload(
            password=password,
        ), format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        response = self.login(email="nueva@example.com", password=password)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.login(email="nueva@example.com", password=password.strip())
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_requires_access_token_for_read_and_update(self):
        for method in ("get", "put"):
            response = getattr(self.client, method)(self.url("me"))
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_rejects_invalid_expired_or_refresh_token(self):
        refresh = RefreshToken.for_user(self.user)
        expired = refresh.access_token
        expired.set_exp(lifetime=timedelta(seconds=-1))
        for token in ("token-invalido", str(expired), str(refresh)):
            with self.subTest(token=token[:15]):
                self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = self.client.get(self.url("me"))
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_profile_updates_email_without_password(self):
        self.authenticate()
        response = self.client.put(self.url("me"), {
            "email": "  NUEVO@EXAMPLE.COM ", "nombre_completo": "Nombre Actualizado",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "nuevo@example.com")
        self.assertEqual(self.user.get_username(), self.user.email)
        self.assertEqual(self.user.nombre_completo, "Nombre Actualizado")
        self.assertTrue(self.user.check_password(self.password))
        self.assertNotIn("password", response.data)
        self.client.credentials()
        self.assertEqual(self.login(email="nuevo@example.com").status_code, 200)
        self.assertEqual(self.login(email="ana@example.com").status_code, 401)

    def test_profile_requires_email_and_name_on_put(self):
        self.authenticate()
        response = self.client.put(self.url("me"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)
        self.assertIn("nombre_completo", response.data)
        self.assertNotIn("password", response.data)

    def test_profile_cannot_change_role_activation_privileges_or_another_user(self):
        self.authenticate()
        response = self.client.put(self.url("me"), {
            "email": self.user.email, "nombre_completo": "Mi Perfil",
            "rol": "ADMIN", "activo": False, "is_active": False,
            "is_staff": True, "is_superuser": True, "id": self.other.pk,
            "username": self.other.email,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.user.rol, User.Rol.VIEWER)
        self.assertTrue(self.user.is_active)
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertEqual(self.user.get_username(), self.user.email)
        self.assertEqual(self.other.nombre_completo, "Otra Persona")
        self.assertEqual(response.data["id"], self.user.pk)

    def test_profile_rejects_duplicate_email(self):
        self.authenticate()
        response = self.client.put(self.url("me"), {
            "email": self.other.email.upper(), "nombre_completo": "Mi Perfil",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "ana@example.com")

    def test_password_change_hashes_password_and_revokes_existing_tokens(self):
        tokens = self.authenticate()
        new_password = "OtraClave!842z"
        response = self.client.put(self.url("me"), {
            "email": self.user.email, "nombre_completo": self.user.nombre_completo,
            "password": new_password,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("password", response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertNotEqual(self.user.password, new_password)
        self.assertFalse(self.user.check_password(self.password))
        self.assertEqual(self.client.get(self.url("me")).status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post(self.url("refresh"), {
            "refresh": tokens["refresh"],
        }, format="json").status_code, 401)
        self.assertEqual(self.login().status_code, 401)
        self.assertEqual(self.login(password=new_password).status_code, 200)

    def test_profile_rejects_weak_password_without_changing_user(self):
        self.authenticate()
        response = self.client.put(self.url("me"), {
            "email": self.user.email, "nombre_completo": self.user.nombre_completo,
            "password": "123456",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))

    def test_refresh_renews_access_and_token_authenticates(self):
        tokens = self.login().data
        response = self.client.post(self.url("refresh"), {
            "refresh": tokens["refresh"],
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        self.assertEqual(self.client.get(self.url("me")).status_code, 200)

    def test_refresh_rejects_missing_invalid_access_or_expired_token(self):
        tokens = self.login().data
        expired = RefreshToken(tokens["refresh"])
        expired.set_exp(lifetime=timedelta(seconds=-1))
        for token in ("invalido", tokens["access"], str(expired)):
            with self.subTest(token=token[:15]):
                response = self.client.post(self.url("refresh"), {
                    "refresh": token,
                }, format="json")
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.post(self.url("refresh"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_user_cannot_login_refresh_or_use_existing_access(self):
        tokens = self.authenticate()
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(self.url("me")).status_code, 401)
        self.client.credentials()
        self.assertEqual(self.login().status_code, 401)
        self.assertEqual(self.client.post(self.url("refresh"), {
            "refresh": tokens["refresh"],
        }, format="json").status_code, 401)

    def test_deleted_user_cannot_refresh(self):
        tokens = self.login().data
        self.user.delete()
        response = self.client.post(self.url("refresh"), {
            "refresh": tokens["refresh"],
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_profile_disallows_patch_and_delete(self):
        self.authenticate()
        for method in ("patch", "delete"):
            response = getattr(self.client, method)(self.url("me"))
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
