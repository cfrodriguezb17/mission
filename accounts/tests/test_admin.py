from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class EmailOnlyAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            email="admin@example.com", password="SuperClave!872z",
        )

    def test_admin_login_accepts_email(self):
        response = self.client.post(reverse("admin:login"), {
            "username": "ADMIN@Example.COM", "password": "SuperClave!872z",
            "next": reverse("admin:index"),
        })
        # AuthenticationForm mantiene el nombre HTML username aunque use email.
        self.assertRedirects(response, reverse("admin:index"))

    def test_admin_add_and_change_user_without_username_field(self):
        self.client.force_login(self.admin)
        add_url = reverse("admin:accounts_user_add")
        response = self.client.get(add_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("username", response.context["adminform"].form.fields)
        response = self.client.post(add_url, {
            "email": "  NUEVA@Example.COM  ", "nombre_completo": "Nueva Persona",
            "rol": "ANALISTA", "is_active": "on",
            "password1": "OtraClave!842z", "password2": "OtraClave!842z",
            "usable_password": "true", "_save": "Guardar",
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="nueva@example.com")
        self.assertTrue(user.check_password("OtraClave!842z"))
        change_url = reverse("admin:accounts_user_change", args=[user.pk])
        response = self.client.get(change_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("username", response.context["adminform"].form.fields)
        response = self.client.post(change_url, {
            "email": "EDITADA@Example.COM", "nombre_completo": "Persona Editada",
            "rol": "ANALISTA", "is_active": "on", "_save": "Guardar",
        })
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.email, "editada@example.com")
        self.assertTrue(user.check_password("OtraClave!842z"))
