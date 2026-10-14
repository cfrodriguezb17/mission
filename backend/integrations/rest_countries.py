from urllib.parse import urlencode

from .http import JsonClient, ProviderError, decimal_value


class RestCountriesClient:
    def __init__(self, api_key, http=None):
        self.api_key = api_key
        self.http = http or JsonClient()

    def pais(self, code):
        if not self.api_key:
            raise ProviderError("Configure REST_COUNTRIES_API_KEY para sincronizar países con la API v5.")
        fields = "names.official,codes.alpha_2,currencies,population,coordinates,flag.url_png"
        payload = self.http.get(
            f"https://api.restcountries.com/countries/v5/codes.alpha_2/{code}?" + urlencode({"response_fields": fields}),
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        try:
            objects = payload["data"]["objects"]
            if not isinstance(objects, list) or len(objects) != 1:
                raise ProviderError("REST Countries no devolvió exactamente un país.")
            row = objects[0]
            if row["codes"]["alpha_2"] != code:
                raise ProviderError("REST Countries devolvió un país distinto al solicitado.")
            population = decimal_value(row["population"])
            if population < 0 or population != population.to_integral_value():
                raise ProviderError("La población debe ser un entero no negativo.")
            currencies = {c["code"]: c["name"] for c in row["currencies"]}
            return {"nombre": row["names"]["official"], "poblacion": int(population),
                    "latitud": decimal_value(row["coordinates"]["lat"]),
                    "longitud": decimal_value(row["coordinates"]["lng"]),
                    "bandera_url": row["flag"]["url_png"], "monedas": currencies}
        except (KeyError, TypeError, AttributeError) as exc:
            raise ProviderError("Respuesta REST Countries inválida o incompleta.") from exc
