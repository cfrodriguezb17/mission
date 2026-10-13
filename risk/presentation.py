from decimal import Decimal


def nivel_riesgo(value):
    if value >= Decimal('75'):
        return 'BAJO'
    if value >= Decimal('50'):
        return 'MODERADO'
    if value >= Decimal('25'):
        return 'ALTO'
    return 'CRITICO'


def color_riesgo(value):
    return {'BAJO': '#22c55e', 'MODERADO': '#eab308', 'ALTO': '#f97316', 'CRITICO': '#ef4444'}[nivel_riesgo(value)]
