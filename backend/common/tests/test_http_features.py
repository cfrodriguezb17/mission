import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from common.exceptions import exception_handler


class HTTPFeaturesTests(TestCase):
    def setUp(self):
        cache.clear()
        self.api = APIClient()
        self.user = get_user_model().objects.create_user(email="http-features@example.com", nombre_completo="Usuario")

    def test_unauthorized_validation_not_found_and_method_errors_share_envelope(self):
        response = self.api.get("/api/dashboard/resumen/")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["error"]["codigo"], "autenticacion")
        self.api.force_authenticate(self.user)
        cases = [(self.api.get("/api/dashboard/mapa/", {"ordering": "password"}), 400),
                 (self.api.get("/api/portafolios/999999/"), 404),
                 (self.api.post("/api/dashboard/mapa/", {}, format="json"), 405)]
        for response, status in cases:
            self.assertEqual(response.status_code, status)
            self.assertEqual(set(response.data["error"]), {"codigo", "mensaje", "detalles"})

    def test_unknown_errors_do_not_expose_secrets(self):
        response = exception_handler(RuntimeError("password=secret"), {})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret", json.dumps(response.data))

    @override_settings(DEBUG=True)
    def test_unknown_api_route_uses_json_even_in_debug(self):
        response = self.api.get("/api/no-existe/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"]["codigo"], "no_encontrado")

    def test_anon_limit_is_twenty_and_returns_retry_after(self):
        for _ in range(20):
            self.assertEqual(self.api.get("/api/").status_code, 200)
        response = self.api.get("/api/")
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)

    def test_authenticated_limit_is_one_hundred_and_independent_per_user(self):
        self.api.force_authenticate(self.user)
        for _ in range(100):
            self.assertEqual(self.api.get("/api/dashboard/mapa/").status_code, 200)
        self.assertEqual(self.api.get("/api/dashboard/mapa/").status_code, 429)
        other = get_user_model().objects.create_user(email="independent-limit@example.com", nombre_completo="Otro")
        self.api.force_authenticate(other)
        self.assertEqual(self.api.get("/api/dashboard/mapa/").status_code, 200)

    @override_settings(CORS_ALLOWED_ORIGINS=["https://frontend.example.com"])
    def test_cors_preflight_and_errors_only_allow_configured_origin(self):
        response = self.api.options("/api/dashboard/resumen/", HTTP_ORIGIN="https://frontend.example.com",
                                    HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
                                    HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization")
        self.assertEqual(response["Access-Control-Allow-Origin"], "https://frontend.example.com")
        response = self.api.get("/api/dashboard/resumen/", HTTP_ORIGIN="https://frontend.example.com")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["Access-Control-Allow-Origin"], "https://frontend.example.com")
        response = self.api.get("/api/dashboard/resumen/", HTTP_ORIGIN="https://malicious.example.com")
        self.assertNotIn("Access-Control-Allow-Origin", response)

    def test_request_logs_method_path_authenticated_user_duration_without_payloads(self):
        self.api.force_authenticate(self.user)
        with self.assertLogs("api.requests", level="INFO") as logs:
            self.api.get("/api/dashboard/resumen/", {"secret": "do-not-log"}, HTTP_AUTHORIZATION="Bearer do-not-log")
        record = logs.records[0]
        self.assertEqual(record.usuario, self.user.pk)
        self.assertEqual(record.ruta, "/api/dashboard/resumen/")
        self.assertGreaterEqual(record.duracion_ms, 0)
        self.assertNotIn("do-not-log", logs.output[0])

    def test_health_checks_database_and_handles_unavailability(self):
        self.assertEqual(self.api.get("/health/").json(), {"estado": "ok"})
        with patch("common.views.connection.cursor", side_effect=RuntimeError("secret")):
            response = self.api.get("/health/")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret", str(response.content))
