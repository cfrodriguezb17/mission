"""Clientes externos sin ORM: límites, errores y decimales exactos."""
import json
import time
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ProviderError(Exception):
    pass


def decimal_value(value):
    if value is None or isinstance(value, bool):
        raise ProviderError("Valor numérico ausente o inválido.")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ProviderError("Valor numérico inválido.") from exc
    if not result.is_finite():
        raise ProviderError("El proveedor devolvió un número no finito.")
    return result


class JsonClient:
    def __init__(self, *, deadline=None, timeout=5, retries=1):
        self.deadline = deadline
        self.timeout = timeout
        self.retries = retries

    def remaining(self):
        if self.deadline is None:
            return self.timeout
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderError("Se agotó el tiempo de sincronización; reintente los países pendientes.")
        return min(self.timeout, remaining)

    def get(self, url, *, headers=None):
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "DataPulse/1.0", **(headers or {})})
        for attempt in range(self.retries + 1):
            try:
                # Lecturas acotadas también limitan respuestas lentas o excesivamente grandes.
                with urlopen(request, timeout=self.remaining()) as response:
                    body = response.read(5_000_001)
                self.remaining()
                if len(body) > 5_000_000:
                    raise ProviderError("La respuesta del proveedor excede el tamaño permitido.")
                return json.loads(body, parse_float=Decimal)
            except HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == self.retries:
                    raise ProviderError(f"El proveedor respondió HTTP {exc.code}.") from exc
            except (URLError, TimeoutError, OSError) as exc:
                if attempt == self.retries:
                    raise ProviderError("No se pudo contactar al proveedor dentro del tiempo permitido.") from exc
            except (ValueError, UnicodeError) as exc:
                raise ProviderError("El proveedor devolvió JSON inválido.") from exc
            delay = min(0.25 * (attempt + 1), self.remaining())
            time.sleep(delay)
        raise ProviderError("No se pudo obtener la respuesta del proveedor.")
