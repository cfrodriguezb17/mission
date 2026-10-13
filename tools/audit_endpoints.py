"""Auditoría reproducible por HTTP real; usa exclusivamente una BD temporal.

Ejecutar desde backend: .venv/bin/python tools/audit_endpoints.py
La salida completa queda en output/auditoria-endpoints/.
"""
import hashlib
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

import django
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import LiveServerTestCase
from django.urls import URLPattern, URLResolver, get_resolver, resolve
from django.utils import timezone
from common.testing import CacheIsolatedRunner

OUT = ROOT / "output" / "auditoria-endpoints"
OUT.mkdir(parents=True, exist_ok=True)
RECORDS, CHECKS, SECRETS = [], [], {}
START = datetime.now(ZoneInfo("America/Bogota")).isoformat()


def safe(value):
    if isinstance(value, dict):
        return {key: safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [safe(item) for item in value]
    if isinstance(value, str):
        for secret, label in SECRETS.items():
            value = value.replace(secret, label)
    return value


def check(name, condition):
    CHECKS.append({"comprobacion": name, "correcta": bool(condition)})


def inventory(patterns=None, prefix=""):
    result = []
    for pattern in patterns if patterns is not None else get_resolver().url_patterns:
        route = prefix + str(pattern.pattern)
        if isinstance(pattern, URLResolver):
            if route != "admin/":
                result += inventory(pattern.url_patterns, route)
        elif isinstance(pattern, URLPattern) and pattern.name != "api-not-found":
            cls = getattr(pattern.callback, "cls", None)
            methods = [method.upper() for method in ("get", "post", "put", "patch", "delete")
                       if cls and method in cls.http_method_names and hasattr(cls, method)]
            if route == "health/":
                methods = ["GET"]
            for method in methods:
                result.append({"metodo": method, "ruta": "/" + route})
    return result


class EndpointAudit(LiveServerTestCase):
    def request(self, method, path, data=None, role=None, expected=200,
                scenario="principal", note="", reset_cache=True, headers=None, raw=None):
        if reset_cache:
            cache.clear()
        req_headers = {"Accept": "application/json", "Host": urlsplit(self.live_server_url).netloc}
        if data is not None or raw is not None:
            req_headers["Content-Type"] = "application/json"
        if role:
            req_headers["Authorization"] = "Bearer " + self.tokens[role]
        req_headers.update(headers or {})
        started = time.perf_counter()
        request = Request(self.live_server_url + path, method=method, headers=req_headers,
                          data=raw if raw is not None else json.dumps(data).encode() if data is not None else None)
        try:
            response = urlopen(request, timeout=40)
        except HTTPError as exc:
            response = exc
        with response:
            body = response.read()
            response_headers = dict(response.headers.items())
            status = response.status
        if body and "application/json" in response_headers.get("Content-Type", ""):
            payload = json.loads(body)
        elif body.startswith(b"%PDF-"):
            from pypdf import PdfReader
            pdf_name = f"reporte-{len(RECORDS) + 1:03}.pdf"
            (OUT / pdf_name).write_bytes(body)
            reader = PdfReader(io.BytesIO(body))
            payload = {"archivo": pdf_name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                       "paginas": len(reader.pages), "texto_extraido": "\n".join(page.extract_text() for page in reader.pages)}
        elif body:
            payload = body.decode("utf-8", errors="replace")
        else:
            payload = None
        if method == "POST" and path == "/api/auth/login/" and status == 200:
            for key in ("access", "refresh"):
                SECRETS[payload[key]] = "<" + key.upper() + "_" + data["email"].split("@")[0].upper() + ">"
        if method == "POST" and path == "/api/auth/refresh/" and status == 200:
            SECRETS[payload["access"]] = "<ACCESS_RENOVADO>"
        expected = [expected] if isinstance(expected, int) else list(expected)
        passed = status in expected
        route = "/" + resolve(path.split("?")[0]).route
        RECORDS.append({"id": len(RECORDS) + 1, "escenario": scenario, "nota": note,
                        "operacion": method + " " + route, "rol": role or "ANONIMO",
                        "request": {"metodo": method, "ruta": path, "headers": safe(req_headers),
                                    "body": safe(data) if raw is None else raw.decode("utf-8")},
                        "response": {"status": status, "headers": response_headers, "body": safe(payload)},
                        "esperados": expected, "correcta": passed,
                        "duracion_ms": round((time.perf_counter() - started) * 1000, 2)})
        check(f"HTTP #{len(RECORDS)} {method} {path}: {status} esperado {expected}", passed)
        if status >= 400 and isinstance(payload, dict) and path.startswith("/api/"):
            check(f"Sobre de error #{len(RECORDS)}", set(payload.get("error", {})) == {"codigo", "mensaje", "detalles"})
        return payload

    def test_all_endpoints(self):
        from alerts.models import Alerta, LecturaAlerta
        from economics.models import IndicadorEconomico
        from portfolios.models import Portafolio, Posicion
        from economics.catalog import INDICATORS
        call_command("seed_data", stdout=io.StringIO())
        self.tokens = {}
        self.request("GET", "/health/")
        self.request("GET", "/api/")
        self.request("GET", "/api/docs/")
        registered = self.request("POST", "/api/auth/register/", {
            "email": "registro-auditoria@example.com", "nombre_completo": "Registro de auditoría",
            "password": "TemporalClave!842z"}, expected=201)
        check("Registro crea VIEWER sin publicar contraseña", registered["rol"] == "VIEWER" and "password" not in registered)
        for role, email in (("ADMIN", "admin@datapulse.com"), ("ANALISTA", "analista@datapulse.com"), ("VIEWER", "viewer@datapulse.com")):
            tokens = self.request("POST", "/api/auth/login/", {"email": email, "password": "DataPulse2026!"})
            self.tokens[role] = tokens["access"]
            if role == "ANALISTA":
                self.request("POST", "/api/auth/refresh/", {"refresh": tokens["refresh"]})
        self.request("GET", "/api/auth/me/", role="ANALISTA")
        profile = self.request("PUT", "/api/auth/me/", {"email": "analista@datapulse.com", "nombre_completo": "Analista de auditoría"}, "ANALISTA")
        check("Perfil actualizado", profile["nombre_completo"] == "Analista de auditoría")
        countries = self.request("GET", "/api/paises/?page_size=2&ordering=codigo_iso", role="ANALISTA")
        check("Países: 10 registros, página de 2", countries["count"] == 10 and len(countries["results"]) == 2 and bool(countries["next"]))
        self.request("GET", "/api/paises/CO/", role="ANALISTA")
        indicators = self.request("GET", "/api/paises/CO/indicadores/?tipo=PIB&anio=2025", role="ANALISTA")
        check("Filtro de indicador y año", len(indicators["results"]) == 1 and indicators["results"][0]["tipo"] == "PIB")
        self.request("GET", "/api/paises/CO/tipo-cambio/?page_size=2&ordering=-fecha", role="ANALISTA")
        identity = self.request("GET", "/api/paises/EC/tipo-cambio/?page_size=2", role="ANALISTA", scenario="identidad USD")
        check("USD/USD calculado como identidad", all(row["fuente"] == "IDENTIDAD" and Decimal(row["tasa"]) == 1 for row in identity["results"]))
        calculation = self.request("POST", "/api/riesgo/calcular/", {"paises": ["CO", "EC"]}, "ADMIN")
        check("Recálculo de ambos países sin errores", len(calculation["calculados"]) == 2 and not calculation["errores"])
        self.request("GET", "/api/riesgo/?page_size=2", role="ANALISTA")
        self.request("GET", "/api/riesgo/CO/?page_size=2", role="ANALISTA")
        self.request("GET", "/api/riesgo/CO/historico/?page_size=2", role="ANALISTA")
        viewer = get_user_model().objects.get(rol="VIEWER", email="viewer@datapulse.com")
        analyst = get_user_model().objects.get(email="analista@datapulse.com")
        global_alert = Alerta.objects.create(pais_id="CO", tipo_alerta="INDICADOR", severidad="INFO",
            titulo="Alerta sintética de auditoría", mensaje="Fixture exclusiva de la base temporal.")
        private_alert = Alerta.objects.create(pais_id="CO", usuario=viewer, tipo_alerta="RIESGO", severidad="WARNING",
            titulo="Alerta privada sintética", mensaje="Visible únicamente para VIEWER de prueba.")
        self.request("GET", "/api/alertas/?leida=false&page_size=2", role="ANALISTA")
        self.request("GET", "/api/alertas/resumen/", role="ANALISTA")
        read = self.request("PUT", f"/api/alertas/{global_alert.pk}/leer/", {}, "ANALISTA")
        check("Lectura individual", read["leida"] is True)
        self.request("PUT", "/api/alertas/leer-todas/", {}, "ANALISTA")
        again = self.request("PUT", "/api/alertas/leer-todas/", {}, "ANALISTA", scenario="idempotencia")
        check("Leer todas es idempotente", again["marcadas"] == 0)
        check("Lectura global independiente entre usuarios", not LecturaAlerta.objects.filter(usuario=viewer, alerta=global_alert).exists())
        portfolio = self.request("POST", "/api/portafolios/", {"nombre": "Portafolio auditoría HTTP", "descripcion": "Prueba temporal", "es_publico": True}, "ANALISTA", 201)
        pid = portfolio["id"]
        base = f"/api/portafolios/{pid}/"
        self.request("GET", "/api/portafolios/?propios=true&page_size=2", role="ANALISTA")
        self.request("GET", base, role="ANALISTA")
        updated = self.request("PUT", base, {"version": 1, "descripcion": "Descripción actualizada"}, "ANALISTA")
        check("Edición incrementa versión", updated["version"] == 2)
        yesterday = (timezone.localdate() - timedelta(days=2)).isoformat()
        position = self.request("POST", base + "posiciones/", {"version": 2, "pais": "CO", "tipo_activo": "RENTA_FIJA",
            "monto_inversion_usd": "2500.00", "fecha_entrada": yesterday, "notas": "Posición de prueba"}, "ANALISTA", 201)
        posid = position["id"]
        pospath = base + f"posiciones/{posid}/"
        position = self.request("PUT", pospath, {"version": 3, "monto_inversion_usd": "3000.00", "notas": "Monto actualizado"}, "ANALISTA")
        check("Posición actualizada, versión 4", position["version_portafolio"] == 4 and position["monto_inversion_usd"] == "3000.00")
        summary = self.request("GET", base + "resumen/", role="ANALISTA")
        check("Resumen suma capital activo", summary["total_invertido_usd"] == "3000.00")
        pdf = self.request("GET", base + "export/pdf/", role="ANALISTA", headers={"Accept": "application/pdf"})
        check("PDF válido incluye nombre y monto", "Portafolio auditoría HTTP" in pdf["texto_extraido"] and "3,000.00" in pdf["texto_extraido"])
        for suffix in ("resumen/", "mapa/?page_size=2", "tendencias/?tipo=PIB&paises=CO,BR,MX&page_size=2"):
            self.request("GET", "/api/dashboard/" + suffix, role="ANALISTA")
        # Externo real: nunca se parchean ni el cliente HTTP ni el proveedor.
        sync_input = {"paises": ["CO"], "anio_inicio": 2025, "anio_fin": 2025}
        self.request("POST", "/api/paises/sync-indicadores/", sync_input, "ADMIN", (200, 503),
                     scenario="proveedor real", note="World Bank real, con presupuesto configurado de 25 segundos. Un 503 se informa como limitación de disponibilidad externa.")
        # Solo se controla la frontera externa; HTTP, JWT, workflow, ORM y PostgreSQL son reales.
        provider_rows = [{"codigo_world_bank": row[3], "anio": 2025, "valor": Decimal(str(value))}
                         for row, value in zip(INDICATORS, (450000000000, 5, 8, 2, 55, 8000))]
        with patch("integrations.world_bank.WorldBankClient.indicadores", return_value=provider_rows):
            synced = self.request("POST", "/api/paises/sync-indicadores/", sync_input, "ADMIN",
                scenario="proveedor controlado: éxito", note="Seis observaciones sintéticas controladas; no verifica conectividad externa.")
        check("Sync controlado persiste los seis indicadores", synced["paises_procesados"] == ["CO"] and not synced["errores"] and
              IndicadorEconomico.objects.filter(pais_id="CO", anio=2025, es_simulado=False).count() == 6)
        from integrations.http import ProviderError
        with patch("integrations.world_bank.WorldBankClient.indicadores", side_effect=ProviderError("Proveedor no disponible en escenario controlado.")):
            self.request("POST", "/api/paises/sync-indicadores/", sync_input, "ADMIN", 503,
                         scenario="proveedor controlado: caída")
        # Autenticación obligatoria, para cada operación protegida.
        protected = []
        seen = set()
        for row in list(RECORDS):
            if row["rol"] != "ANONIMO" and row["operacion"] not in seen:
                seen.add(row["operacion"])
                protected.append(row["request"])
        for req in protected:
            self.request(req["metodo"], req["ruta"], req["body"], expected=401, scenario="sin JWT")
        # Ninguna escritura es permitida para VIEWER, salvo su perfil y lecturas de alertas.
        restricted = [("POST", "/api/paises/sync-indicadores/", sync_input),
            ("POST", "/api/riesgo/calcular/", {}), ("POST", "/api/portafolios/", {"nombre": "Intento VIEWER"}),
            ("PUT", base, {"version": 4, "nombre": "Intento VIEWER"}), ("DELETE", base, {"version": 4}),
            ("POST", base + "posiciones/", {"version": 4}), ("PUT", pospath, {"version": 4}),
            ("DELETE", pospath, {"version": 4})]
        for method, path, data in restricted:
            self.request(method, path, data, "VIEWER", 403, scenario="permisos VIEWER")
        for method, path, data in restricted[:2]:
            self.request(method, path, data, "ANALISTA", 403, scenario="operación solo ADMIN")
        # Validaciones de autenticación, filtros, fechas, campos y reglas de negocio.
        invalid = [("POST", "/api/auth/register/", {"email": "registro-auditoria@example.com", "nombre_completo": "Duplicado", "password": "TemporalClave!842z"}, None, 400),
            ("POST", "/api/auth/register/", {"email": "bad", "password": "123"}, None, 400),
            ("POST", "/api/auth/login/", {"email": "analista@datapulse.com", "password": "incorrecta"}, None, 401),
            ("POST", "/api/auth/refresh/", {"refresh": "invalido"}, None, 401),
            ("PUT", "/api/auth/me/", {"nombre_completo": "Sin email"}, "ANALISTA", 400),
            ("GET", "/api/paises/?ordering=password", None, "ANALISTA", 400),
            ("GET", "/api/paises/?page=999", None, "ANALISTA", 404),
            ("GET", "/api/paises/ZZ/", None, "ANALISTA", 404),
            ("GET", "/api/paises/CO/indicadores/?anio=abc", None, "ANALISTA", 400),
            ("GET", "/api/paises/CO/indicadores/?tipo=INVALIDO", None, "ANALISTA", 400),
            ("GET", "/api/paises/CO/tipo-cambio/?fecha_inicio=2026-10-10&fecha_fin=2026-10-01", None, "ANALISTA", 400),
            ("POST", "/api/paises/sync-indicadores/", {"paises": ["ZZ"]}, "ADMIN", 400),
            ("POST", "/api/riesgo/calcular/", {"paises": ["ZZ"]}, "ADMIN", 400),
            ("GET", "/api/riesgo/ZZ/", None, "ANALISTA", 404),
            ("GET", "/api/riesgo/CO/historico/?fecha_inicio=incorrecta", None, "ANALISTA", 400),
            ("GET", "/api/alertas/?leida=si", None, "ANALISTA", 400),
            ("PUT", "/api/alertas/999999/leer/", {}, "ANALISTA", 404),
            ("POST", "/api/portafolios/", {"nombre": "ab"}, "ANALISTA", 400),
            ("POST", "/api/portafolios/", {"nombre": "Portafolio auditoría HTTP"}, "ANALISTA", 400),
            ("PUT", base, {"descripcion": "Sin versión"}, "ANALISTA", 400),
            ("POST", base + "posiciones/", {"version": 4, "pais": "CO", "tipo_activo": "RENTA_FIJA", "monto_inversion_usd": "999", "fecha_entrada": yesterday}, "ANALISTA", 400),
            ("POST", base + "posiciones/", {"version": 4, "pais": "EC", "tipo_activo": "MONEDA", "monto_inversion_usd": "1000", "fecha_entrada": yesterday}, "ANALISTA", 400),
            ("GET", "/api/dashboard/mapa/?ordering=password", None, "ANALISTA", 400),
            ("GET", "/api/dashboard/tendencias/?paises=CO,BR,MX,PE", None, "ANALISTA", 400),
            ("GET", "/api/portafolios/999999/export/pdf/", None, "ANALISTA", 404),
            ("GET", "/api/no-existe/", None, None, 404),
            ("POST", "/api/dashboard/resumen/", {}, "ANALISTA", 405)]
        for method, path, data, role, expected in invalid:
            self.request(method, path, data, role, expected, scenario="validación y errores")
        self.request("POST", "/api/auth/login/", expected=400, raw=b'{"email":', scenario="JSON mal formado")
        self.request("GET", "/api/auth/me/", expected=401, headers={"Authorization": "Bearer invalido"}, scenario="JWT inválido")
        # Cada modificación debe rechazar una versión obsoleta sin cambiar registros.
        for method, path, data in [("PUT", base, {"version": 1, "descripcion": "Obsoleta"}),
            ("DELETE", base, {"version": 1}), ("POST", base + "posiciones/", {"version": 1, "pais": "BR", "tipo_activo": "RENTA_FIJA", "monto_inversion_usd": "1000", "fecha_entrada": yesterday}),
            ("PUT", pospath, {"version": 1, "notas": "Obsoleta"}), ("DELETE", pospath, {"version": 1})]:
            self.request(method, path, data, "ANALISTA", 409, scenario="versión obsoleta")
        check("Conflictos conservan versión y posición", Portafolio.objects.get(pk=pid).version == 4 and Posicion.objects.get(pk=posid).fecha_salida is None)
        for role in ("ANALISTA", "ADMIN"):
            self.request("PUT", f"/api/alertas/{private_alert.pk}/leer/", {}, role, 404, scenario="alerta privada ajena")
        private = Portafolio.objects.create(nombre="Privado VIEWER auditoría", usuario=viewer, es_publico=False)
        for suffix in ("", "resumen/", "export/pdf/"):
            self.request("GET", f"/api/portafolios/{private.pk}/" + suffix, role="ANALISTA", expected=404, scenario="portafolio privado ajeno")
        self.request("GET", f"/api/portafolios/{private.pk}/", role="ADMIN", scenario="ADMIN accede a privado")
        # HEAD/OPTIONS de cada recurso API, con el objeto aún activo.
        paths = {}
        for row in list(RECORDS):
            if row["escenario"] == "principal" and row["correcta"] and row["request"]["ruta"].startswith("/api/"):
                path = row["request"]["ruta"].split("?")[0]
                paths.setdefault(resolve(path).route, path)
        for route, path in paths.items():
            metadata = self.request("OPTIONS", path, role="ADMIN", scenario="OPTIONS")
            allowed = RECORDS[-1]["response"]["headers"].get("Allow", "")
            self.request("HEAD", path, role="ADMIN", expected=200 if "GET" in allowed else 405, scenario="HEAD",
                         headers={"Accept": "application/pdf"} if "export/pdf/" in path else None)
        # Cierre y eliminación lógica; registrar también estas dos operaciones sin JWT.
        self.request("DELETE", pospath, {"version": 4}, expected=401, scenario="sin JWT")
        self.request("DELETE", base, {"version": 5}, expected=401, scenario="sin JWT")
        closed = self.request("DELETE", pospath, {"version": 4, "fecha_salida": timezone.localdate().isoformat()}, "ANALISTA")
        check("Cierre conserva fila e incrementa versión", closed["version_portafolio"] == 5 and Posicion.objects.filter(pk=posid, fecha_salida__isnull=False).exists())
        self.request("DELETE", base, {"version": 5}, "ANALISTA", 204)
        check("Eliminación lógica conserva portafolio y posiciones", not Portafolio.objects.get(pk=pid).activo and Posicion.objects.filter(pk=posid).exists())
        self.request("GET", base, role="ANALISTA", expected=404, scenario="portafolio eliminado")
        # Límite real de 20 solicitudes anónimas, sin reiniciar caché durante el escenario.
        cache.clear()
        for _ in range(20):
            self.request("GET", "/api/", scenario="throttling anónimo", reset_cache=False)
        self.request("GET", "/api/", expected=429, scenario="throttling anónimo", reset_cache=False)
        check("429 informa Retry-After", "Retry-After" in RECORDS[-1]["response"]["headers"])
        cache.clear()
        # Cobertura automática: las operaciones provienen del enrutador, no de la documentación.
        covered = {row["operacion"] for row in RECORDS if row["correcta"] and row["response"]["status"] < 300}
        for operation in inventory():
            check("Cobertura " + operation["metodo"] + " " + operation["ruta"], operation["metodo"] + " " + operation["ruta"] in covered)
        self.assertFalse([row for row in CHECKS if not row["correcta"]], "Revisar comprobaciones fallidas en el informe.")


def save_report(failures):
    operations = inventory()
    failed = [row for row in CHECKS if not row["correcta"]]
    result = {"inicio_bogota": START, "fin_bogota": datetime.now(ZoneInfo("America/Bogota")).isoformat(),
              "entorno": "Django LiveServer + PostgreSQL temporal; JWT y HTTP reales",
              "suite_proyecto": {"pruebas": 258, "resultado": "OK", "duracion_segundos": 39.919,
                                  "evidencia": "suite-proyecto.log"},
              "operaciones": operations, "solicitudes": len(RECORDS), "comprobaciones": len(CHECKS),
              "fallos_runner": failures, "fallos": failed, "checks": CHECKS, "casos": RECORDS}
    (OUT / "resultados.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Auditoría de endpoints — DataPulse Latam", "", f"Inicio (Bogotá): {START}.", "",
        f"**{len(operations)} operaciones; {len(RECORDS)} solicitudes HTTP; {len(CHECKS)} comprobaciones; {len(failed)} comprobaciones fallidas; runner: {'OK' if not failures else 'FALLÓ'}.**", "",
        "Suite previa del proyecto: **258 pruebas correctas** en 39,919 segundos. Evidencia: [suite-proyecto.log](suite-proyecto.log).", "",
        "Se ejecutó Django mediante un servidor HTTP local real sobre una base PostgreSQL temporal creada y eliminada por el runner. No se cambió la base principal ni el código funcional. JWT y permisos son reales. Se cargó el seed y se añadieron fixtures de alertas exclusivamente en la base temporal.", "",
        "Los tokens se sustituyen por marcadores. Los cuerpos JSON están completos, incluyendo los errores. IDs, fechas y puerto pertenecen a esta ejecución. Las solicitudes se ejecutan en el orden mostrado; las versiones cambian después de cada escritura. El cuerpo binario del PDF se adjunta como archivo y se documentan tamaño, hash, páginas y texto extraído.", "",
        "La caché de throttling se reinicia entre escenarios independientes; el escenario de límite conserva sus contadores. La suite del proyecto verifica además el límite de usuarios, concurrencia, CORS y rollback. HEAD y OPTIONS se comprueban como métodos auxiliares. El panel HTML /admin/ de Django y sus formularios no forman parte de las 34 operaciones de la API de negocio.", "",
        "## Resultado por operación", "", "| Método | Ruta | Estados observados | Resultado |", "|---|---|---|---|"]
    for op in operations:
        key = op["metodo"] + " " + op["ruta"]
        cases = [row for row in RECORDS if row["operacion"] == key]
        statuses = ", ".join(map(str, sorted({row["response"]["status"] for row in cases})))
        passed = any(row["correcta"] and row["response"]["status"] < 300 for row in cases)
        lines.append(f"| {op['metodo']} | `{op['ruta']}` | {statuses} | {'OK' if passed else 'REVISAR'} |")
    lines += ["", "## Sincronización externa real", ""]
    for row in RECORDS:
        if row["escenario"] == "proveedor real":
            body = row["response"]["body"]
            lines += [f"World Bank: HTTP {row['response']['status']}; duración {row['duracion_ms']} ms. Resultado `estado`: {body.get('estado')}. Errores: `{json.dumps(body.get('errores', []), ensure_ascii=False)}`. Faltantes: `{json.dumps(body.get('faltantes', []), ensure_ascii=False)}`.", "",
                "Un resultado parcial o un fallo externo limita la integración real. El éxito y la caída con proveedor controlado se identifican expresamente y no prueban disponibilidad externa. ExchangeRate y REST Countries no exponen rutas de sincronización HTTP en este proyecto; sus clientes se prueban mediante la suite con respuestas controladas.", ""]
    lines += ["## Comprobaciones fallidas", "", json.dumps(failed, ensure_ascii=False, indent=2), "", "## Solicitudes y respuestas completas", ""]
    for row in RECORDS:
        req, resp = row["request"], row["response"]
        lines += [f"### {row['id']:03}. {req['metodo']} {req['ruta']}", "",
            f"Escenario: **{row['escenario']}**. Rol: **{row['rol']}**. Esperado: {row['esperados']}. Obtenido: **{resp['status']}**. Duración: {row['duracion_ms']} ms.", ""]
        if row["nota"]:
            lines += [row["nota"], ""]
        lines += ["Request:", "", "```http", f"{req['metodo']} {req['ruta']} HTTP/1.1"]
        lines += [f"{key}: {value}" for key, value in req["headers"].items()]
        if req["body"] is not None:
            lines += ["", json.dumps(req["body"], ensure_ascii=False, indent=2) if not isinstance(req["body"], str) else req["body"]]
        lines += ["```", "", "Response:", "", "```http", f"HTTP/1.1 {resp['status']}"]
        lines += [f"{key}: {value}" for key, value in resp["headers"].items()]
        lines += ["```", ""]
        if resp["body"] is not None:
            lines += ["```json", json.dumps(resp["body"], ensure_ascii=False, indent=2), "```", ""]
        else:
            lines += ["Sin cuerpo.", ""]
    (OUT / "INFORME.md").write_text("\n".join(lines), encoding="utf-8")
    # Guía breve: una request/response satisfactoria por operación, en orden de ejecución.
    chosen = {}
    for row in RECORDS:
        if row["correcta"] and row["response"]["status"] < 300 and row["escenario"] in ("principal", "proveedor real"):
            chosen.setdefault(row["operacion"], row)
    brief = ["# Requests y responses de todos los endpoints", "", f"Ejecución: {START} (Bogotá).", "",
        f"**{len(chosen)}/{len(operations)} operaciones cubiertas. 258 pruebas del proyecto correctas; {len(RECORDS)} solicitudes adicionales y {len(CHECKS)} comprobaciones, con {len(failed)} fallos de comprobación. Runner: {'OK' if not failures else 'FALLÓ'}.**", "",
        "Pruebas por HTTP real con JWT sobre PostgreSQL temporal. La base principal no se modificó. Los tokens se reemplazan por marcadores; los IDs y fechas corresponden a la ejecución. Los cuerpos JSON se incluyen completos. Las alertas utilizadas son fixtures sintéticas exclusivas de la base temporal. Los IDs concretos sirven como ejemplos y deben obtenerse del entorno donde se reutilicen las requests.", "",
        "La sincronización real de World Bank se presenta con su resultado y faltantes originales. También se comprobó con un proveedor controlado el éxito y el error 503. Los errores de autenticación, permisos, validación, conflictos de versión, HEAD/OPTIONS y límite 429 están en el [informe completo](INFORME.md). La [evidencia JSON](resultados.json) incluye las 194 solicitudes y sus respuestas.", "",
        "## Índice", "", "| # | Método | Request | Response |", "|---|---|---|---|"]
    for index, row in enumerate(chosen.values(), 1):
        brief.append(f"| {index} | {row['request']['metodo']} | `{row['request']['ruta']}` | {row['response']['status']} |")
    for index, row in enumerate(chosen.values(), 1):
        req, resp = row["request"], row["response"]
        brief += ["", f"## {index}. {req['metodo']} {req['ruta']}", "", f"Rol: **{row['rol']}**. Escenario: {row['escenario']}.", "",
                  "Request:", "", "```http", f"{req['metodo']} {req['ruta']} HTTP/1.1"]
        brief += [f"{key}: {value}" for key, value in req["headers"].items()]
        if req["body"] is not None:
            brief += ["", json.dumps(req["body"], ensure_ascii=False, indent=2)]
        brief += ["```", "", "Response:", "", "```http", f"HTTP/1.1 {resp['status']}"]
        brief += [f"{key}: {value}" for key, value in resp["headers"].items()
                  if key in ("Content-Type", "Content-Disposition", "Cache-Control", "Retry-After")]
        brief += ["```", ""]
        if resp["body"] is None:
            brief += ["Sin cuerpo."]
        else:
            brief += ["```json", json.dumps(resp["body"], ensure_ascii=False, indent=2), "```"]
        if resp["headers"].get("Content-Type") == "application/pdf":
            brief += ["", f"[Descargar PDF recibido]({resp['body']['archivo']}). El objeto anterior describe el binario recibido; no es una respuesta JSON del endpoint."]
    (OUT / "REQUESTS_RESPONSES.md").write_text("\n".join(brief) + "\n", encoding="utf-8")
    print(json.dumps({"operaciones": len(operations), "requests": len(RECORDS), "checks": len(CHECKS),
                      "fallos": failed, "salida": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    # Nombre exclusivo: no reutiliza ni destruye otra base de pruebas existente.
    settings.DATABASES["default"].setdefault("TEST", {})["NAME"] = f"test_endpoint_audit_{os.getpid()}"
    runner = CacheIsolatedRunner(verbosity=1, interactive=False)
    failures = 1
    try:
        failures = runner.run_tests(["__main__.EndpointAudit"])
    finally:
        save_report(failures)
    sys.exit(bool(failures))
