from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP, localcontext

from django.db.models import ExpressionWrapper, OuterRef, Subquery, Value

from .models import TipoCambio


def cotizaciones_con_anterior(moneda_origen, moneda_destino="USD"):
    anterior = TipoCambio.objects.filter(
        moneda_origen_id=OuterRef("moneda_origen_id"),
        moneda_destino_id=OuterRef("moneda_destino_id"),
        fecha=ExpressionWrapper(OuterRef("fecha") - Value(timedelta(days=1)),
                                output_field=TipoCambio._meta.get_field("fecha")),
    )
    return TipoCambio.objects.filter(
        moneda_origen_id=moneda_origen, moneda_destino_id=moneda_destino,
    ).annotate(tasa_anterior=Subquery(anterior.values("tasa")[:1]))


def variacion_porcentual(tasa, tasa_anterior):
    if tasa_anterior is None:
        return None
    # Cubrir el cociente entre ambos extremos válidos de DecimalField(24, 12).
    with localcontext() as context:
        context.prec = 60
        return ((tasa / tasa_anterior - 1) * 100).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
