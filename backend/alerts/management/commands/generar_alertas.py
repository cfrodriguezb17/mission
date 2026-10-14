import json

from django.core.management.base import BaseCommand, CommandError

from alerts.services import generar_alertas
from countries.models import Pais


class Command(BaseCommand):
    help = "Recupera índices históricos y lotes INFO pendientes sin duplicar alertas."

    def add_arguments(self, parser):
        parser.add_argument("--paises", nargs="+")
        parser.add_argument("--limite", type=int, default=100,
                            help="Máximo conjunto de índices y lotes por ejecución (1–1000).")

    def handle(self, *args, **options):
        codes = None
        if not 1 <= options["limite"] <= 1000:
            raise CommandError("El límite de trabajos debe estar entre 1 y 1000.")
        if options["paises"]:
            codes = {code.upper() for code in options["paises"]}
            existing = set(Pais.objects.filter(pk__in=codes).values_list("pk", flat=True))
            if codes - existing:
                raise CommandError("Seleccione únicamente países existentes.")
        result = generar_alertas(paises=codes, limite=options["limite"])
        self.stdout.write(json.dumps(result, ensure_ascii=False))
        if result["errores"] or result["pendientes"]:
            raise CommandError("Generación parcial: revise los errores o trabajos pendientes y repita el comando.")
