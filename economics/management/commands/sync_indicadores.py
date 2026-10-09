import json

from django.core.management.base import BaseCommand, CommandError

from economics.catalog import COUNTRY_CODES
from backend.workflows import sincronizar_y_recalcular as sincronizar_indicadores


class Command(BaseCommand):
    help = "Sincroniza World Bank para los países del alcance; conserva datos manuales y registra fallos parciales."

    def add_arguments(self, parser):
        parser.add_argument("--paises", nargs="+", choices=COUNTRY_CODES)
        parser.add_argument("--anio-inicio", type=int)
        parser.add_argument("--anio-fin", type=int)
        parser.add_argument("--presupuesto", type=int, default=180, help="Límite total de segundos (1–600).")

    def handle(self, *args, **options):
        if not 1 <= options["presupuesto"] <= 600:
            raise CommandError("El presupuesto debe estar entre 1 y 600 segundos.")
        try:
            result = sincronizar_indicadores(paises=options["paises"], anio_inicio=options["anio_inicio"],
                                            anio_fin=options["anio_fin"], presupuesto=options["presupuesto"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False))
        if result["errores"] or result.get("riesgos", {}).get("errores"):
            raise CommandError("Sincronización parcial: consulte los errores y reintente los países pendientes.")
