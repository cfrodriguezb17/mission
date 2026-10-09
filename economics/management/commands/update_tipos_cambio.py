import json

from django.core.management.base import BaseCommand, CommandError

from backend.workflows import actualizar_y_recalcular as actualizar_tipos_cambio


class Command(BaseCommand):
    help = "Obtiene la cotización diaria ExchangeRate y guarda moneda local → USD."

    def handle(self, *args, **options):
        result = actualizar_tipos_cambio()
        self.stdout.write(json.dumps(result, ensure_ascii=False))
        if result["errores"] or result.get("riesgos", {}).get("errores") or result.get("alertas", {}).get("errores") or result.get("auditoria_pendiente"):
            raise CommandError("Actualización parcial: consulte los errores.")
