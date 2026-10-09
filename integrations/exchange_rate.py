from datetime import datetime, timezone

from .http import JsonClient, ProviderError, decimal_value


class ExchangeRateClient:
    def __init__(self, http=None):
        self.http = http or JsonClient()

    def cotizaciones(self):
        payload = self.http.get("https://open.er-api.com/v6/latest/USD")
        if not isinstance(payload, dict) or payload.get("result") != "success" or payload.get("base_code") != "USD":
            raise ProviderError("Respuesta ExchangeRate inválida o con mensaje de error.")
        if not isinstance(payload.get("rates"), dict):
            raise ProviderError("ExchangeRate no devolvió un catálogo de tasas.")
        try:
            timestamp = int(payload["time_last_update_unix"])
            date = datetime.fromtimestamp(timestamp, timezone.utc).date()
            if timestamp <= 0 or date > datetime.now(timezone.utc).date():
                raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError, OSError) as exc:
            raise ProviderError("Fecha de actualización ExchangeRate inválida.") from exc
        return date, payload["rates"]

    @staticmethod
    def invertir(value):
        value = decimal_value(value)
        if value <= 0:
            raise ProviderError("La cotización debe ser positiva.")
        return 1 / value
