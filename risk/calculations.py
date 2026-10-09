"""IRPC v1: funciones puras, Decimal y evidencia; sin HTTP ni ORM."""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP, localcontext

VERSION_FORMULA = "irpc-v1"
D = Decimal
ECONOMIC_RULES = {
    "PIB_PERCAPITA": ("lt", ((3000, 30), (6000, 15), (12000, 5))),
    "INFLACION": ("gt", ((50, 40), (10, 25), (5, 10))),
    "DESEMPLEO": ("gt", ((15, 25), (10, 15), (7, 5))),
    "DEUDA_PIB": ("gt", ((80, 20), (50, 10))),
}


def penalty(value, direction, brackets):
    if value is None:
        return 0
    for threshold, amount in brackets:
        if (direction == "lt" and value < D(threshold)) or (direction == "gt" and value > D(str(threshold))):
            return amount
    return 0


def economic_score(values):
    penalties = {code: penalty(values.get(code), *rule) for code, rule in ECONOMIC_RULES.items()}
    return D(max(0, 100 - sum(penalties.values()))), penalties


def stability_score(values, previous_gdp, economic_penalties):
    with localcontext() as ctx:
        ctx.prec = 64
        current = values.get("PIB")
        growth = ((current - previous_gdp) / previous_gdp * 100
                  if current is not None and previous_gdp is not None and previous_gdp > 0 else None)
        trade_penalty = penalty(values.get("BALANZA_COMERCIAL"), "lt", ((-10, 25), (-5, 15), (0, 5)))
        growth_penalty = penalty(growth, "lt", ((-2, 30), (0, 20), (1, 10)))
        negative = [code for code, amount in economic_penalties.items() if amount]
        if trade_penalty:
            negative.append("BALANZA_COMERCIAL")
        if growth_penalty:
            negative.append("PIB")
        penalties = {"BALANZA_COMERCIAL": trade_penalty, "CRECIMIENTO_PIB": growth_penalty,
                     "INDICADORES_NEGATIVOS": 5 * len(negative)}
        return D(max(0, 100 - sum(penalties.values()))), penalties, growth, negative


def currency_score(rates, end, identity=False):
    start = end - timedelta(days=30)
    if identity:
        return D(100), {"no_aplica": True, "volatilidad": "0", "depreciacion": "0",
                        "variaciones": [], "fechas_faltantes": [], "faltantes": [],
                        "penalizaciones": {"VOLATILIDAD": 0, "DEPRECIACION": 0}}
    with localcontext() as ctx:
        ctx.prec = 64
        variations = []
        missing_dates = []
        for offset in range(31):
            day = start + timedelta(days=offset)
            if day not in rates:
                missing_dates.append(day.isoformat())
            if offset and day in rates and day - timedelta(days=1) in rates:
                value = (rates[day] / rates[day - timedelta(days=1)] - 1) * 100
                variations.append({"fecha": day.isoformat(), "valor": str(value)})
        values = [D(item["valor"]) for item in variations]
        volatility = None
        if len(values) >= 2:
            mean = sum(values) / len(values)
            volatility = (sum((value - mean) ** 2 for value in values) / len(values)).sqrt()
        depreciation = None
        if start in rates and end in rates:
            # USD por moneda local: una caída de la tasa es depreciación.
            depreciation = max(D(0), (1 - rates[end] / rates[start]) * 100)
        penalties = {"VOLATILIDAD": penalty(volatility, "gt", ((3, 40), (1.5, 25), (0.5, 10))),
                     "DEPRECIACION": penalty(depreciation, "gt", ((10, 30), (5, 15), (2, 5)))}
        missing = []
        if volatility is None:
            missing.append("VOLATILIDAD")
        if depreciation is None:
            missing.append("DEPRECIACION")
        if missing_dates:
            missing.append("HISTORICO_CAMBIARIO_30_DIAS")
        detail = {"no_aplica": False, "volatilidad": str(volatility) if volatility is not None else None,
                  "depreciacion": str(depreciation) if depreciation is not None else None,
                  "variaciones": variations, "fechas_faltantes": missing_dates, "faltantes": missing,
                  "penalizaciones": penalties}
        return D(max(0, 100 - sum(penalties.values()))), detail


def calculate_irpc(values, previous_gdp, rates, end, identity=False):
    with localcontext() as ctx:
        ctx.prec = 64
        economic, economic_penalties = economic_score(values)
        stability, stability_penalties, growth, negative = stability_score(values, previous_gdp, economic_penalties)
        currency, currency_detail = currency_score(rates, end, identity)
        missing = [code for code in (*ECONOMIC_RULES, "PIB", "BALANZA_COMERCIAL") if values.get(code) is None]
        if growth is None:
            missing.append("CRECIMIENTO_PIB")
        missing.extend(currency_detail["faltantes"])
        composite = (economic * D("0.40") + currency * D("0.30") + stability * D("0.30")).quantize(
            D("0.01"), rounding=ROUND_HALF_UP)
        return {"score_economico": economic, "score_cambiario": currency, "score_estabilidad": stability,
                "indice_compuesto": composite, "version_formula": VERSION_FORMULA,
                "detalle_calculo": {"missing_indicators": missing, "datos_parciales": bool(missing),
                    "penalizaciones_economicas": economic_penalties, "penalizaciones_estabilidad": stability_penalties,
                    "crecimiento_pib": str(growth) if growth is not None else None,
                    "indicadores_negativos": negative, "cambiario": currency_detail,
                    "pesos": {"economico": "0.40", "cambiario": "0.30", "estabilidad": "0.30"}}}
