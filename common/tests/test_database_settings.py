import os
from pathlib import Path
import runpy
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase


class DatabaseSettingsTests(SimpleTestCase):
    def read_database(self, value=None, **overrides):
        # No leer secretos locales ni modificar el módulo de settings en uso.
        environment = {"DJANGO_DEBUG": "true"}
        if value is not None:
            environment["DJANGO_DB_CONN_MAX_AGE"] = value
        environment.update(overrides)
        with patch.dict(os.environ, environment, clear=True), patch("dotenv.load_dotenv"):
            config = runpy.run_path(str(Path(settings.BASE_DIR) / "backend" / "settings.py"))
        return config["DATABASES"]["default"]

    def test_default_uses_pool_and_prepared_statements_without_persistent_connections(self):
        config = self.read_database()
        self.assertEqual(config["CONN_MAX_AGE"], 0)
        self.assertTrue(config["CONN_HEALTH_CHECKS"])
        self.assertEqual(config['OPTIONS']['pool']['max_size'], 4)
        self.assertTrue(config['OPTIONS']['server_side_binding'])
        self.assertEqual(config['OPTIONS']['prepare_threshold'], 5)

    def test_zero_disables_persistence_and_positive_age_is_configurable(self):
        for value in ("0", "120"):
            with self.subTest(value=value):
                self.assertEqual(self.read_database(value, DJANGO_DB_POOL='false')["CONN_MAX_AGE"], int(value))

    def test_pool_rejects_persistence_and_invalid_sizes(self):
        for options in ({'DJANGO_DB_CONN_MAX_AGE': '60'}, {'DJANGO_DB_POOL_MIN_SIZE': '5'},
                        {'DJANGO_DB_POOL_MAX_SIZE': '0'}, {'DJANGO_DB_POOL_MIN_SIZE': '-1'},
                        {'DJANGO_DB_POOL': 'yes'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.read_database(**options)

    def test_preparation_can_be_disabled_and_invalid_threshold_rejected(self):
        config = self.read_database(DJANGO_DB_PREPARE_THRESHOLD='')
        self.assertNotIn('prepare_threshold', config['OPTIONS'])
        self.assertNotIn('server_side_binding', config['OPTIONS'])
        for value in ('-1', 'invalid', '1.5'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.read_database(DJANGO_DB_PREPARE_THRESHOLD=value)

    def test_invalid_age_stops_startup(self):
        for value in ("-1", "", "invalid", "1.5"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "DJANGO_DB_CONN_MAX_AGE"):
                self.read_database(value)
