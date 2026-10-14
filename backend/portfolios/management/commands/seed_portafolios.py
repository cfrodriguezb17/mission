from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from countries.models import Pais
from portfolios.models import Portafolio
from portfolios.services import agregar_posicion, crear_portafolio


class Command(BaseCommand):
    help = "Crea dos portafolios de demostración para un usuario existente, sin modificar registros existentes."

    def add_arguments(self, parser):
        parser.add_argument("--usuario", required=True, help="Email de un ADMIN o ANALISTA existente y activo.")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            user = get_user_model().objects.select_for_update().get(email=options["usuario"].strip().lower(), is_active=True)
        except get_user_model().DoesNotExist:
            raise CommandError("Seleccione un usuario existente y activo; el comando no crea ni modifica usuarios.")
        if user.rol not in ("ADMIN", "ANALISTA"):
            raise CommandError("El usuario debe tener rol ADMIN o ANALISTA.")
        examples = [
            ("Demo Latam compartido", True, [("CO", "RENTA_FIJA", "100000"), ("BR", "RENTA_VARIABLE", "150000")]),
            ("Demo Andino privado", False, [("PE", "COMMODITIES", "75000"), ("CL", "RENTA_FIJA", "125000")]),
        ]
        count = 0
        try:
            for name, public, positions in examples:
                if Portafolio.objects.filter(usuario=user, nombre=name).exists():
                    continue
                codes = {code for code, _, _ in positions}
                countries = {country.pk: country for country in Pais.objects.filter(pk__in=codes, activo=True)}
                if set(countries) != codes:
                    raise CommandError("Faltan países activos para el seed. Ejecute seed_countries primero.")
                portfolio = crear_portafolio(user, {"nombre": name, "descripcion": "Portafolio simulado para demostración.", "es_publico": public})
                for code, kind, amount in positions:
                    _, portfolio = agregar_posicion(user, portfolio.pk, portfolio.version, {
                        "pais": countries[code], "tipo_activo": kind, "monto_inversion_usd": Decimal(amount),
                        "fecha_entrada": timezone.localdate() - timedelta(days=7), "notas": "Posición simulada de demostración.",
                    })
                count += 1
        except APIException as exc:
            raise CommandError(str(exc.detail)) from exc
        self.stdout.write(self.style.SUCCESS(f"Portafolios creados: {count}. Registros existentes conservados."))
