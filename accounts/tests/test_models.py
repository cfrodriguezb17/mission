from django.contrib.auth import get_user_model
from django.test import TestCase


class UserCreationTests(TestCase):
    def test_create_user_persists_and_hashes_password(self):
        User = get_user_model()
        password = "ClaveSegura!739x"
        user = User.objects.create_user(
            email="  ANA@Example.COM  ",
            nombre_completo="Ana Pérez",
            password=password,
        )

        saved_user = User.objects.get(pk=user.pk)
        self.assertEqual(saved_user.email, "ana@example.com")
        self.assertEqual(saved_user.nombre_completo, "Ana Pérez")
        self.assertEqual(saved_user.username, saved_user.email)
        self.assertEqual(User.USERNAME_FIELD, "email")
        self.assertEqual(saved_user.rol, User.Rol.VIEWER)
        self.assertTrue(saved_user.is_active)
        self.assertIsNotNone(saved_user.fecha_creacion)
        self.assertNotEqual(saved_user.password, password)
        self.assertTrue(saved_user.check_password(password))
        self.assertFalse(saved_user.check_password("OtraClave!123"))
        self.assertEqual(str(saved_user), saved_user.email)

    def test_standard_createsuperuser_command_uses_email_without_username(self):
        import os
        from unittest.mock import patch

        from django.contrib.auth import authenticate
        from django.core.management import call_command

        User = get_user_model()
        password = "SuperClave!872z"
        with patch.dict(os.environ, {"DJANGO_SUPERUSER_PASSWORD": password}):
            call_command(
                "createsuperuser", email="ADMIN@Example.COM", interactive=False,
                verbosity=0,
            )
        user = User.objects.get(email="admin@example.com")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertEqual(user.username, user.email)
        self.assertTrue(user.check_password(password))
        self.assertEqual(user.nombre_completo, user.email)
        self.assertEqual(user.rol, User.Rol.VIEWER)
        self.assertEqual(authenticate(email="ADMIN@Example.COM", password=password), user)

    def test_superuser_rejects_invalid_required_flags(self):
        User = get_user_model()
        for flag in ("is_staff", "is_superuser", "is_active"):
            with self.subTest(flag=flag):
                with self.assertRaises(ValueError):
                    User.objects.create_superuser(
                        email="admin@example.com", password="SuperClave!872z",
                        **{flag: False},
                    )
        self.assertFalse(User.objects.filter(email="admin@example.com").exists())
