import json

from django.core.management.base import BaseCommand, CommandError

from countries.services import sincronizar_paises


class Command(BaseCommand):
    help = "Actualiza datos generales desde REST Countries v5; requiere REST_COUNTRIES_API_KEY."

    def handle(self, *args, **options):
        result = sincronizar_paises()
        self.stdout.write(json.dumps(result, ensure_ascii=False))
        if result["errores"]:
            raise CommandError("Sincronización de países parcial: consulte los errores.")
