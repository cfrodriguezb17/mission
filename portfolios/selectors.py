from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q

from risk.selectors import ultimos_indices

from .models import Portafolio


def portafolios_visibles(usuario):
    queryset = Portafolio.objects.filter(activo=True)
    if not usuario.is_active:
        return queryset.none()
    if usuario.rol != "ADMIN":
        queryset = queryset.filter(Q(usuario=usuario) | Q(es_publico=True))
    return queryset


def resumen_portafolio(portafolio, *, posiciones=None, indices=None):
    positions = (list(portafolio.posiciones.filter(fecha_salida__isnull=True).select_related("pais"))
                 if posiciones is None else [p for p in posiciones if p.fecha_salida is None])
    if indices is None:
        indices = {index.pais_id: index for index in ultimos_indices().filter(pais_id__in={p.pais_id for p in positions})}
    total = sum((p.monto_inversion_usd for p in positions), Decimal("0"))
    known = sum((p.monto_inversion_usd for p in positions if p.pais_id in indices), Decimal("0"))
    weighted = sum((p.monto_inversion_usd * indices[p.pais_id].indice_compuesto
                    for p in positions if p.pais_id in indices), Decimal("0"))

    def amount(value):
        return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def distribution(key):
        grouped = {}
        for position in positions:
            code = key(position)
            grouped[code] = grouped.get(code, Decimal("0")) + position.monto_inversion_usd
        return [{"codigo": code, "monto_usd": amount(value),
                 "porcentaje": amount(value / total * 100) if total else "0.00"}
                for code, value in sorted(grouped.items())]

    return {
        "portafolio": portafolio.pk, "version": portafolio.version,
        "total_invertido_usd": amount(total), "posiciones_activas": len(positions),
        "riesgo_promedio_ponderado": amount(weighted / known) if known else None,
        "monto_con_riesgo_usd": amount(known), "monto_sin_riesgo_usd": amount(total - known),
        "riesgo_incompleto": known != total,
        "paises_sin_riesgo": sorted({p.pais_id for p in positions if p.pais_id not in indices}),
        "distribucion_por_pais": distribution(lambda p: p.pais_id),
        "distribucion_por_tipo_activo": distribution(lambda p: p.tipo_activo),
        "distribucion_por_riesgo": distribution(lambda p: indices[p.pais_id].nivel_riesgo if p.pais_id in indices else "SIN_DATOS"),
    }
