import unittest

from django.core.cache import caches
from django.conf import settings
from django.test.runner import DiscoverRunner


class CacheIsolatedRunner(DiscoverRunner):
    """Aislar throttling entre pruebas que reutilizan PK; mantenerlo activo dentro de cada una."""

    def build_suite(self, test_labels=None, **kwargs):
        # Funciona también al invocar backend/manage.py desde la raíz del proyecto.
        return super().build_suite(test_labels or [str(settings.BASE_DIR)], **kwargs)

    def get_resultclass(self):
        base = super().get_resultclass() or unittest.TextTestResult

        class Result(base):
            def startTest(self, test):
                for cache in caches.all():
                    cache.clear()
                super().startTest(test)

        return Result
