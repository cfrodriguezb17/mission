from django.conf import settings
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient


class ThrottlingProxyTests(SimpleTestCase):
    def test_default_limit_ignores_spoofed_forwarded_headers(self):
        api = APIClient()
        for index in range(20):
            response = api.post("/api/auth/login/", {}, format="json",
                                REMOTE_ADDR="192.0.2.10",
                                HTTP_X_FORWARDED_FOR=f"198.51.100.{index + 1}")
            self.assertEqual(response.status_code, 400)
        for headers in ({}, {"HTTP_X_FORWARDED_FOR": "203.0.113.99"},
                        {"HTTP_X_FORWARDED_FOR": "inventado, 198.51.100.20"}):
            response = api.post("/api/auth/login/", {}, format="json",
                                REMOTE_ADDR="192.0.2.10", **headers)
            self.assertEqual(response.status_code, 429)
            self.assertIn("Retry-After", response)
        # Otra conexión real conserva su contador, aunque declare el mismo XFF.
        response = api.post("/api/auth/login/", {}, format="json",
                            REMOTE_ADDR="192.0.2.11", HTTP_X_FORWARDED_FOR="203.0.113.99")
        self.assertEqual(response.status_code, 400)

    @override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "NUM_PROXIES": 1})
    def test_trusted_proxy_uses_client_address_without_untrusted_prefix(self):
        api = APIClient()
        for index in range(20):
            response = api.get("/api/", REMOTE_ADDR="192.0.2.100",
                               HTTP_X_FORWARDED_FOR=f"198.51.100.{index + 1}, 203.0.113.10")
            self.assertEqual(response.status_code, 200)
        response = api.get("/api/", REMOTE_ADDR="192.0.2.100",
                           HTTP_X_FORWARDED_FOR="otro-valor, 203.0.113.10")
        self.assertEqual(response.status_code, 429)
        response = api.get("/api/", REMOTE_ADDR="192.0.2.100",
                           HTTP_X_FORWARDED_FOR="otro-valor, 203.0.113.11")
        self.assertEqual(response.status_code, 200)
