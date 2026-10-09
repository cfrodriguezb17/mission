import json

from django.core.management.base import BaseCommand, CommandError

from risk.services import recalcular_riesgos


class Command(BaseCommand):
    help = "Calcula IRPC histórico para los países activos con datos persistidos."

    def add_arguments(self, parser):
        parser.add_argument("--paises", nargs="+")

    def handle(self, *args, **options):
        codes = [code.upper() for code in options["paises"]] if options["paises"] else None
        result = recalcular_riesgos(codes)
        self.stdout.write(json.dumps(result, ensure_ascii=False))
        if result["errores"]:
            raise CommandError("Recálculo parcial: consulte los países con errores.")
