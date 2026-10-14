from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.contrib.auth.models import AnonymousUser
from django.core.cache import caches
from redis.exceptions import ConnectionError
from rest_framework.test import APIClient, APIRequestFactory

from common.throttling import AnonRateThrottle, ThrottlingUnavailable


class SharedThrottlingTests(SimpleTestCase):
    def test_both_cache_stores_unavailable_fails_closed(self):
        with patch.object(AnonRateThrottle.cache, 'get', side_effect=ConnectionError('private-secret')):
            with patch.object(caches['throttle_fallback'], 'get', side_effect=OSError('private-secret')):
                response = APIClient().get('/api/')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data['error']['codigo'], 'servicio_no_disponible')
        self.assertNotIn('private-secret', str(response.data))

    def test_cache_failure_preserves_cause_for_internal_diagnostics(self):
        request = APIRequestFactory().get('/api/')
        request.user = AnonymousUser()
        with patch.object(AnonRateThrottle.cache, 'get', side_effect=OSError('unavailable')):
            with patch.object(caches['throttle_fallback'], 'get', side_effect=OSError('unavailable')):
                with self.assertRaises(ThrottlingUnavailable):
                    AnonRateThrottle().allow_request(request, None)

    @override_settings(THROTTLE_REDIS=True)
    def test_redis_outage_keeps_http_available_and_last_known_rate_budget(self):
        api = APIClient()
        with patch('common.throttling._retry_at', 0):
            for _ in range(19):
                self.assertEqual(api.get('/api/').status_code, 200)
            with patch.object(AnonRateThrottle.cache, 'get', side_effect=ConnectionError('down')):
                self.assertEqual(api.get('/api/').status_code, 200)
                self.assertEqual(api.get('/api/').status_code, 429)
