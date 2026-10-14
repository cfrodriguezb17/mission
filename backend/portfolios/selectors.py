from decimal import Decimal, ROUND_HALF_UP
from collections.abc import Mapping

from django.db.models import Q

from risk.selectors import ultimos_indices
from risk.presentation import nivel_riesgo

from .models import Portafolio


def nombre_disponible(usuario_id, nombre, *, excluir=None):
    # Los nombres de portafolios eliminados también permanecen reservados.
    return not Portafolio.objects.filter(usuario_id=usuario_id, nombre=nombre).exclude(pk=excluir).exists()


def portafolios_visibles(usuario):
    queryset = Portafolio.objects.filter(activo=True)
    if not usuario.is_active:
        return queryset.none()
    if usuario.rol != "ADMIN":
        queryset = queryset.filter(Q(usuario=usuario) | Q(es_publico=True))
    return queryset


def resumen_portafolio(portafolio, *, posiciones=None, indices=None):
    rows = (portafolio.posiciones.filter(fecha_salida__isnull=True).values(
                'pais_id', 'tipo_activo', 'monto_inversion_usd', 'fecha_salida')
            if posiciones is None else posiciones)
    positions = []
    for row in rows:
        if not isinstance(row, Mapping) and row.fecha_salida is not None:
            continue
        value = row if isinstance(row, Mapping) else {
            'pais_id': row.pais_id, 'tipo_activo': row.tipo_activo,
            'monto_inversion_usd': row.monto_inversion_usd, 'fecha_salida': row.fecha_salida}
        if value['fecha_salida'] is None:
            positions.append(value)
    if indices is None:
        scores = dict(ultimos_indices().filter(pais_id__in={p['pais_id'] for p in positions}).values_list(
            "pais_id", "indice_compuesto"))
    else:
        scores = {code: index.indice_compuesto for code, index in indices.items()}
    total = sum((p['monto_inversion_usd'] for p in positions), Decimal("0"))
    known = sum((p['monto_inversion_usd'] for p in positions if p['pais_id'] in scores), Decimal("0"))
    weighted = sum((p['monto_inversion_usd'] * scores[p['pais_id']]
                    for p in positions if p['pais_id'] in scores), Decimal("0"))

    def amount(value):
        return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def distribution(key):
        grouped = {}
        for position in positions:
            code = key(position)
            grouped[code] = grouped.get(code, Decimal("0")) + position['monto_inversion_usd']
        return [{"codigo": code, "monto_usd": amount(value),
                 "porcentaje": amount(value / total * 100) if total else "0.00"}
                for code, value in sorted(grouped.items())]

    return {
        "portafolio": portafolio.pk, "version": portafolio.version,
        "total_invertido_usd": amount(total), "posiciones_activas": len(positions),
        "riesgo_promedio_ponderado": amount(weighted / known) if known else None,
        "monto_con_riesgo_usd": amount(known), "monto_sin_riesgo_usd": amount(total - known),
        "riesgo_incompleto": known != total,
        "paises_sin_riesgo": sorted({p['pais_id'] for p in positions if p['pais_id'] not in scores}),
        "distribucion_por_pais": distribution(lambda p: p['pais_id']),
        "distribucion_por_tipo_activo": distribution(lambda p: p['tipo_activo']),
        "distribucion_por_riesgo": distribution(lambda p: nivel_riesgo(scores[p['pais_id']]) if p['pais_id'] in scores else "SIN_DATOS"),
    }
