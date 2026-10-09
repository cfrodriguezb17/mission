import json

from django.core.management.base import BaseCommand, CommandError

from alerts.services import generar_alertas
from countries.models import Pais
from risk.selectors import ultimos_indices


class Command(BaseCommand):
    help = "Genera o reintenta alertas para el último IRPC de países activos sin duplicarlas."

    def add_arguments(self, parser):
        parser.add_argument("--paises", nargs="+")

    def handle(self, *args, **options):
        queryset = ultimos_indices()
        if options["paises"]:
            codes = {code.upper() for code in options["paises"]}
            existing = set(Pais.objects.filter(activo=True, pk__in=codes).values_list("pk", flat=True))
            if codes - existing:
                raise CommandError("Seleccione únicamente países existentes y activos.")
            queryset = queryset.filter(pais_id__in=codes)
        result = generar_alertas([{"id": index.pk, "pais": index.pais_id} for index in queryset])
        self.stdout.write(json.dumps(result, ensure_ascii=False))
        if result["errores"]:
            raise CommandError("Generación parcial: consulte los errores.")
