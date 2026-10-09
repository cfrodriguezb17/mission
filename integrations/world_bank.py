from urllib.parse import urlencode

from .http import JsonClient, ProviderError, decimal_value


class WorldBankClient:
    def __init__(self, http=None):
        self.http = http or JsonClient()

    def indicadores(self, pais, codigos, anio_inicio, anio_fin):
        url = f"https://api.worldbank.org/v2/country/{pais}/indicator/{';'.join(codigos)}"
        observations = []
        page = 1
        while True:
            payload = self.http.get(url + "?" + urlencode({
                "source": 2, "format": "json", "date": f"{anio_inicio}:{anio_fin}",
                "per_page": 1000, "page": page,
            }))
            if not isinstance(payload, list) or len(payload) != 2 or not isinstance(payload[0], dict):
                raise ProviderError("Respuesta World Bank inválida o con mensaje de error.")
            meta, rows = payload
            try:
                pages = int(meta["pages"])
                response_page = int(meta["page"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderError("Paginación World Bank inválida.") from exc
            if not 0 <= pages <= 20 or response_page != page or (rows is not None and not isinstance(rows, list)):
                raise ProviderError("Paginación o datos World Bank inválidos.")
            for row in rows or []:
                try:
                    code = row["indicator"]["id"]
                    year = int(row["date"])
                    country = row["country"]["id"].upper()
                    value = row["value"]
                    if code not in codigos or country != pais or not anio_inicio <= year <= anio_fin:
                        raise ProviderError("World Bank devolvió un indicador, país o año no solicitado.")
                    if value is None:
                        observations.append({"codigo_world_bank": code, "anio": year, "valor": None})
                    else:
                        observations.append({"codigo_world_bank": code, "anio": year, "valor": decimal_value(value)})
                except (KeyError, TypeError, ValueError, AttributeError) as exc:
                    raise ProviderError("Observación World Bank inválida.") from exc
            if page >= pages:
                break
            page += 1
        return observations
