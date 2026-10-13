import os
from pathlib import Path
import runpy
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase


class DatabaseSettingsTests(SimpleTestCase):
    def read_database(self, value=None):
        # No leer secretos locales ni modificar el módulo de settings en uso.
        environment = {"DJANGO_DEBUG": "true"}
        if value is not None:
            environment["DJANGO_DB_CONN_MAX_AGE"] = value
        with patch.dict(os.environ, environment, clear=True), patch("dotenv.load_dotenv"):
            config = runpy.run_path(str(Path(settings.BASE_DIR) / "backend" / "settings.py"))
        return config["DATABASES"]["default"]

    def test_default_reuses_connections_and_checks_health(self):
        config = self.read_database()
        self.assertEqual(config["CONN_MAX_AGE"], 60)
        self.assertTrue(config["CONN_HEALTH_CHECKS"])

    def test_zero_disables_persistence_and_positive_age_is_configurable(self):
        for value in ("0", "120"):
            with self.subTest(value=value):
                self.assertEqual(self.read_database(value)["CONN_MAX_AGE"], int(value))

    def test_invalid_age_stops_startup(self):
        for value in ("-1", "", "invalid", "1.5"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "DJANGO_DB_CONN_MAX_AGE"):
                self.read_database(value)
