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
