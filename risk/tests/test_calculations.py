from datetime import date, timedelta
from decimal import Decimal as D

from django.test import SimpleTestCase

from risk.calculations import calculate_irpc, currency_score, economic_score, penalty, stability_score


class CalculationTests(SimpleTestCase):
    def test_all_economic_boundaries_use_strict_comparisons_and_only_one_bracket(self):
        cases = {
            "PIB_PERCAPITA": [(2999, 30), (3000, 15), (5999, 15), (6000, 5), (11999, 5), (12000, 0)],
            "INFLACION": [(5, 0), (D("5.01"), 10), (10, 10), (D("10.01"), 25), (50, 25), (51, 40)],
            "DESEMPLEO": [(7, 0), (8, 5), (10, 5), (11, 15), (15, 15), (16, 25)],
            "DEUDA_PIB": [(50, 0), (51, 10), (80, 10), (81, 20)],
        }
        for code, rows in cases.items():
            for value, expected in rows:
                with self.subTest(code=code, value=value):
                    score, penalties = economic_score({code: D(value)})
                    self.assertEqual(penalties[code], expected)
                    self.assertEqual(score, 100 - expected)

    def test_scores_are_clamped_and_missing_indicators_are_not_zero(self):
        result = calculate_irpc({"PIB_PERCAPITA": D(1000), "INFLACION": D(60),
                                 "DESEMPLEO": D(20), "DEUDA_PIB": D(90)}, None, {}, date(2026, 1, 31))
        self.assertEqual(result["score_economico"], 0)
        missing = calculate_irpc({}, None, {}, date(2026, 1, 31))
        self.assertEqual(missing["score_economico"], 100)
        self.assertTrue(missing["detalle_calculo"]["datos_parciales"])
        self.assertIn("PIB_PERCAPITA", missing["detalle_calculo"]["missing_indicators"])

    def test_stability_boundaries_and_count_distinct_penalized_indicators(self):
        for trade, expected in ((-11, 25), (-10, 15), (-6, 15), (-5, 5), (-1, 5), (0, 0)):
            score, penalties, growth, negative = stability_score({"BALANZA_COMERCIAL": D(trade)}, None, {})
            self.assertEqual(penalties["BALANZA_COMERCIAL"], expected)
            self.assertEqual(len(negative), bool(expected))
        for current, expected in ((97, 30), (98, 20), (99, 20), (100, 10), (101, 0)):
            _, penalties, growth, negative = stability_score({"PIB": D(current)}, D(100), {"INFLACION": 10})
            self.assertEqual(penalties["CRECIMIENTO_PIB"], expected)
            self.assertEqual(penalties["INDICADORES_NEGATIVOS"], 5 * (1 + bool(expected)))
        self.assertIsNone(stability_score({"PIB": D(100)}, D(0), {})[2])
        self.assertIsNone(stability_score({"PIB": D(100)}, D(-1), {})[2])

    def test_currency_penalty_boundaries(self):
        for value, expected in ((D("0.5"), 0), (D("0.5001"), 10), (D("1.5"), 10),
                                (D("1.5001"), 25), (D(3), 25), (D("3.0001"), 40)):
            self.assertEqual(penalty(value, "gt", ((3, 40), (1.5, 25), (0.5, 10))), expected)
        for value, expected in ((2, 0), (3, 5), (5, 5), (6, 15), (10, 15), (11, 30)):
            self.assertEqual(penalty(D(value), "gt", ((10, 30), (5, 15), (2, 5))), expected)

    def test_population_standard_deviation_and_depreciation_direction(self):
        end = date(2026, 1, 31)
        rates = {end - timedelta(days=2): D(100), end - timedelta(days=1): D(102), end: D("99.96")}
        score, detail = currency_score(rates, end)
        self.assertEqual(D(detail["volatilidad"]), 2)  # +2 %, -2 %; desviación poblacional.
        self.assertEqual(score, 75)
        self.assertIsNone(detail["depreciacion"])
        rates[end - timedelta(days=30)] = D(120)
        score, detail = currency_score(rates, end)
        self.assertEqual(D(detail["depreciacion"]), D("16.700"))
        self.assertEqual(score, 45)
        rates[end] = D(130)
        self.assertEqual(D(currency_score(rates, end)[1]["depreciacion"]), 0)

    def test_gaps_are_not_bridged_and_usd_is_identity(self):
        end = date(2026, 1, 31)
        rates = {end: D(2), end - timedelta(days=2): D(1)}
        _, detail = currency_score(rates, end)
        self.assertEqual(detail["variaciones"], [])
        self.assertIn("VOLATILIDAD", detail["faltantes"])
        score, detail = currency_score({}, end, identity=True)
        self.assertEqual(score, 100)
        self.assertTrue(detail["no_aplica"])
        self.assertEqual(detail["faltantes"], [])

    def test_compound_example_is_69(self):
        # Ejemplo reproducible: económico 60, cambiario 70, estabilidad 80.
        # No pretende reconstruir entradas que no figuran en la transcripción.
        end = date(2026, 1, 31)
        values = {"PIB_PERCAPITA": D(6800), "INFLACION": D(12), "DESEMPLEO": D(6),
                  "DEUDA_PIB": D(60), "BALANZA_COMERCIAL": D(-1), "PIB": D(103)}
        rates = {end - timedelta(days=i): D(100) - D(30 - i) * D("0.4") for i in range(31)}
        result = calculate_irpc(values, D(100), rates, end)
        # La balanza también cuenta como indicador en riesgo: 4 indicadores → estabilidad 75.
        self.assertEqual(result["score_economico"], 60)
        self.assertEqual(result["score_cambiario"], 70)
        self.assertEqual(result["score_estabilidad"], 75)
        self.assertEqual(result["indice_compuesto"], D("67.50"))
        # Dos indicadores económicos penalizados + balanza → estabilidad 80.
        values["PIB_PERCAPITA"] = D(12000)
        values["INFLACION"] = D(11)
        values["DEUDA_PIB"] = D(40)
        values["DESEMPLEO"] = D(11)
        result = calculate_irpc(values, D(100), rates, end)
        self.assertEqual(result["score_economico"], 60)
        self.assertEqual(result["score_estabilidad"], 80)
        self.assertEqual(result["indice_compuesto"], D("69.00"))

    def test_extreme_valid_quote_precision_does_not_crash(self):
        end = date(2026, 1, 31)
        rates = {end - timedelta(days=2): D("0.000000000001"),
                 end - timedelta(days=1): D("999999999999.999999999999"), end: D("0.000000000001")}
        score, detail = currency_score(rates, end)
        self.assertEqual(score, 60)
        self.assertTrue(D(detail["volatilidad"]).is_finite())
