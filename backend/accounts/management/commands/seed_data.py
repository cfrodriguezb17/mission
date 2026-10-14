"""Dataset de entrega repetible, sin alterar identidades ni datos existentes."""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from economics.catalog import COUNTRY_CODES
from risk.selectors import ultimos_indices

USUARIOS = [
    ("admin@datapulse.com", "Administrador de demostración", "ADMIN"),
    ("analista@datapulse.com", "Analista de demostración", "ANALISTA"),
    ("viewer@datapulse.com", "Lector de demostración", "VIEWER"),
]


class Command(BaseCommand):
    help = "Crea usuarios de prueba, países, indicadores, cotizaciones y portafolios; recalcula riesgos solo si cambió el dataset."

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        # Validar primero todos los emails; un conflicto cancela el seed completo.
        existing = {u.email: u for u in User.objects.select_for_update().filter(email__in=[row[0] for row in USUARIOS])}
        for email, _, role in USUARIOS:
            user = existing.get(email)
            if user and (not user.is_active or user.rol != role or not user.check_password("DataPulse2026!")):
                raise CommandError(f"El usuario de prueba {email} ya existe con otros datos. "
                                   "No se modificó: resuelva el conflicto explícitamente antes de repetir.")
        created = 0
        for email, name, role in USUARIOS:
            if email not in existing:
                existing[email] = User.objects.create_user(email=email, nombre_completo=name, rol=role)
                # Credencial fija exigida por el enunciado, similar al dominio:
                # excepción acotada a estas tres cuentas DEMO; no relajar el registro.
                existing[email].set_password("DataPulse2026!")
                existing[email].save(update_fields=["password"])
                created += 1
        from economics.models import IndicadorEconomico, TipoCambio
        before = (IndicadorEconomico.objects.count(), TipoCambio.objects.count())
        call_command("seed_economics", stdout=self.stdout)
        call_command("seed_portafolios", usuario="analista@datapulse.com", stdout=self.stdout)
        after = (IndicadorEconomico.objects.count(), TipoCambio.objects.count())
        complete = set(ultimos_indices().values_list("pais_id", flat=True)) >= set(COUNTRY_CODES)
        if before != after or not complete:
            call_command("calcular_riesgos", stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS(
            f"Dataset preparado. Usuarios creados: {created}; usuarios y datos previos conservados. "
            "Históricos de demostración identificados como simulados."
        ))
