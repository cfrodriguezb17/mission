from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Avg, Count, OuterRef, Q, Subquery

from alerts.selectors import alertas_visibles
from countries.models import Pais
from portfolios.selectors import portafolios_visibles
from risk.models import IndiceRiesgo
from risk.selectors import ultimos_indices


def resumen_dashboard(usuario):
    metrics = ultimos_indices().aggregate(
        promedio=Avg("indice_compuesto"),
        total=Count("pk"),
        parciales=Count("pk", filter=Q(detalle_calculo__datos_parciales=True)),
    )
    average = metrics["promedio"]
    return {
        "total_paises": Pais.objects.filter(activo=True).count(),
        "alertas_activas": alertas_visibles(usuario).filter(leida=False).count(),
        "portafolios_usuario": portafolios_visibles(usuario).filter(usuario=usuario).count(),
        "promedio_irpc": str(average.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if average is not None else None,
        "paises_con_riesgo": metrics["total"],
        "paises_con_datos_parciales": metrics["parciales"],
    }


def paises_con_riesgo():
    latest = IndiceRiesgo.objects.filter(pais_id=OuterRef("pk")).order_by("-fecha_calculo", "-pk")
    return Pais.objects.filter(activo=True).select_related("moneda").annotate(
        irpc=Subquery(latest.values("indice_compuesto")[:1]),
        fecha_riesgo=Subquery(latest.values("fecha_calculo")[:1]),
        datos_parciales=Subquery(latest.values("detalle_calculo__datos_parciales")[:1]),
        contiene_simulaciones=Subquery(latest.values("detalle_calculo__contiene_simulaciones")[:1]),
    )
