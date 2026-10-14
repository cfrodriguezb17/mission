import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from common.logging import JsonFormatter
from integrations.exchange_rate import ExchangeRateClient
from integrations.http import JsonClient, ProviderError, decimal_value
from integrations.rest_countries import RestCountriesClient
from integrations.world_bank import WorldBankClient


class IntegrationContractTests(TestCase):
    def test_world_bank_reads_all_pages_and_keeps_missing_values(self):
        def row(value):
            return {"country": {"id": "CO"}, "indicator": {"id": "FP.CPI.TOTL.ZG"}, "date": "2025", "value": value}
        http = Mock()
        http.get.side_effect = [[{"page": 1, "pages": 2}, [row(Decimal("9.2"))]],
                                [{"page": 2, "pages": 2}, [row(None)]]]
        observations = WorldBankClient(http).indicadores("CO", ["FP.CPI.TOTL.ZG"], 2025, 2025)
        self.assertEqual(observations[0]["valor"], Decimal("9.2"))
        self.assertIsNone(observations[1]["valor"])
        self.assertIn("page=2", http.get.call_args.args[0])

    def test_world_bank_rejects_errors_wrong_country_and_invalid_values(self):
        for payload in ([{"message": "error"}], [{"page": 1, "pages": 21}, []],
                        [{"page": 1, "pages": 1}, [{"country": {"id": "BR"}, "indicator": {"id": "X"}, "date": "2025", "value": 1}]],
                        [{"page": 1, "pages": 1}, [{}]]):
            with self.subTest(payload=payload), self.assertRaises(ProviderError):
                WorldBankClient(Mock(get=Mock(return_value=payload))).indicadores("CO", ["X"], 2025, 2025)

    def test_exchange_uses_provider_update_day_and_rejects_bad_responses(self):
        timestamp = int(datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp())
        valid = {"result": "success", "base_code": "USD", "time_last_update_unix": timestamp, "rates": {"COP": 4000}}
        date_value, rates = ExchangeRateClient(Mock(get=Mock(return_value=valid))).cotizaciones()
        self.assertEqual(date_value, date(2026, 1, 2))
        self.assertEqual(ExchangeRateClient.invertir(rates["COP"]), Decimal("0.00025"))
        for invalid in ({"result": "error"}, valid | {"base_code": "EUR"}, valid | {"rates": []}, valid | {"time_last_update_unix": -1}):
            with self.subTest(invalid=invalid), self.assertRaises(ProviderError):
                ExchangeRateClient(Mock(get=Mock(return_value=invalid))).cotizaciones()

    def test_non_finite_boolean_and_malformed_numbers_rejected(self):
        for invalid in (None, True, "NaN", "Infinity", "abc"):
            with self.subTest(invalid=invalid), self.assertRaises(ProviderError):
                decimal_value(invalid)
        for invalid in (0, -1):
            with self.assertRaises(ProviderError):
                ExchangeRateClient.invertir(invalid)

    def test_rest_countries_requires_key_and_validates_v5_shape(self):
        with self.assertRaises(ProviderError):
            RestCountriesClient("", Mock()).pais("CO")
        row = {"codes": {"alpha_2": "CO"}, "names": {"official": "Colombia"}, "population": 52_000_000,
               "coordinates": {"lat": Decimal("4.57"), "lng": Decimal("-74.29")},
               "currencies": [{"code": "COP", "name": "Peso colombiano"}], "flag": {"url_png": "https://example.org/co.png"}}
        http = Mock(get=Mock(return_value={"data": {"objects": [row]}}))
        result = RestCountriesClient("test-key", http).pais("CO")
        self.assertEqual(result["monedas"], {"COP": "Peso colombiano"})
        self.assertEqual(http.get.call_args.kwargs["headers"]["Authorization"], "Bearer test-key")
        row["population"] = Decimal("1.2")
        with self.assertRaises(ProviderError):
            RestCountriesClient("test-key", http).pais("CO")
        http.get.return_value = {"data": {"objects": []}}
        with self.assertRaises(ProviderError):
            RestCountriesClient("test-key", http).pais("CO")

    @patch("integrations.http.time.sleep")
    @patch("integrations.http.urlopen")
    def test_json_client_retries_network_errors_and_preserves_decimal_precision(self, opener, sleep):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"value": 123.123456789012345678}'
        opener.side_effect = [URLError("timeout"), response]
        payload = JsonClient().get("https://example.org")
        self.assertEqual(payload["value"], Decimal("123.123456789012345678"))
        self.assertEqual(opener.call_count, 2)

    @patch("integrations.http.urlopen")
    def test_json_client_does_not_retry_permanent_http_errors_or_bad_json(self, opener):
        opener.side_effect = HTTPError("https://example.org", 401, "Denied", {}, None)
        with self.assertRaises(ProviderError):
            JsonClient().get("https://example.org")
        self.assertEqual(opener.call_count, 1)
        opener.side_effect = None
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'<html>unavailable</html>'
        opener.return_value = response
        with self.assertRaises(ProviderError):
            JsonClient().get("https://example.org")

    @patch("integrations.http.urlopen")
    def test_expired_deadline_never_contacts_provider(self, opener):
        with self.assertRaises(ProviderError):
            JsonClient(deadline=0).get("https://example.org")
        opener.assert_not_called()

    @patch("integrations.http.time.sleep")
    @patch("integrations.http.urlopen")
    def test_transient_http_errors_have_a_bounded_retry_count(self, opener, sleep):
        for status in (429, 500, 502, 503, 504):
            with self.subTest(status=status):
                opener.reset_mock()
                opener.side_effect = HTTPError("https://example.org", status, "Unavailable", {}, None)
                with self.assertRaisesRegex(ProviderError, f"HTTP {status}"):
                    JsonClient(retries=1).get("https://example.org")
                self.assertEqual(opener.call_count, 2)

    @patch("integrations.http.urlopen")
    def test_oversized_provider_response_is_rejected_without_retry(self, opener):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b"x" * 5_000_001
        opener.return_value = response
        with self.assertRaisesRegex(ProviderError, "tamaño"):
            JsonClient().get("https://example.org")
        self.assertEqual(opener.call_count, 1)

    def test_world_bank_handles_empty_data_and_rejects_wrong_year_or_non_finite_value(self):
        http = Mock(get=Mock(return_value=[{"page": 1, "pages": 0}, None]))
        self.assertEqual(WorldBankClient(http).indicadores("CO", ["X"], 2025, 2025), [])
        base = {"country": {"id": "CO"}, "indicator": {"id": "X"}, "date": "2025", "value": 1}
        for row in (base | {"date": "2024"}, base | {"value": "NaN"}, base | {"value": True}):
            with self.subTest(row=row), self.assertRaises(ProviderError):
                http.get.return_value = [{"page": 1, "pages": 1}, [row]]
                WorldBankClient(http).indicadores("CO", ["X"], 2025, 2025)

    def test_structured_logs_keep_operation_context_and_spanish_text(self):
        record = logging.LogRecord("economics.services", logging.ERROR, __file__, 1, "Sincronización fallida", (), None)
        record.pais = "CO"
        record.sincronizacion = {"errores": [{"mensaje": "Sin conexión"}]}
        payload = json.loads(JsonFormatter().format(record))
        self.assertEqual(payload["nivel"], "ERROR")
        self.assertEqual(payload["pais"], "CO")
        self.assertEqual(payload["sincronizacion"]["errores"][0]["mensaje"], "Sin conexión")
