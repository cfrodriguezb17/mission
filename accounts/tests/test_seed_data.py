from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from economics.models import TipoCambio
from portfolios.models import Portafolio
from risk.models import IndiceRiesgo


class SeedDataTests(TestCase):
    def test_complete_seed_is_repeatable_and_does_not_change_existing_users_or_quotes(self):
        User = get_user_model()
        owner = User.objects.create_user(email="existing@example.com", nombre_completo="Existente", rol="ANALISTA")
        original = owner.password
        call_command("seed_data", stdout=StringIO())
        counts = (User.objects.count(), Portafolio.objects.count(), TipoCambio.objects.count(), IndiceRiesgo.objects.count())
        self.assertEqual(counts, (4, 2, 279, 10))
        self.assertFalse(IndiceRiesgo.objects.filter(detalle_calculo__datos_parciales=True).exists())
        for email, role in [("admin@datapulse.com", "ADMIN"), ("analista@datapulse.com", "ANALISTA"), ("viewer@datapulse.com", "VIEWER")]:
            user = User.objects.get(email=email)
            self.assertEqual(user.rol, role)
            self.assertTrue(user.check_password("DataPulse2026!"))
        call_command("seed_data", stdout=StringIO())
        self.assertEqual(counts, (User.objects.count(), Portafolio.objects.count(), TipoCambio.objects.count(), IndiceRiesgo.objects.count()))
        owner.refresh_from_db()
        self.assertEqual(owner.password, original)

    def test_conflicting_demo_identity_aborts_without_resetting_password_or_creating_other_users(self):
        User = get_user_model()
        existing = User.objects.create_user(email="viewer@datapulse.com", nombre_completo="Original", rol="ADMIN")
        with self.assertRaises(CommandError):
            call_command("seed_data", stdout=StringIO())
        self.assertEqual(User.objects.count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.rol, "ADMIN")
        self.assertEqual(TipoCambio.objects.count(), 0)
