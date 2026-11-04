from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings

from accounts.security import is_rate_limited


@override_settings(CACHES={"default": {
    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    "LOCATION": "security-throttle-tests",
}})
class AtomicRateLimitTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.request = RequestFactory().post("/login/", REMOTE_ADDR="192.0.2.10")

    def test_allows_limit_then_blocks_next_attempt(self):
        for _ in range(5):
            self.assertFalse(is_rate_limited("test-login", self.request, limit=5, window=60))
        self.assertTrue(is_rate_limited("test-login", self.request, limit=5, window=60))

    def test_scopes_counters_by_identity(self):
        self.assertFalse(is_rate_limited("test-login", self.request, identity="one@example.test", limit=1, window=60))
        self.assertFalse(is_rate_limited("test-login", self.request, identity="two@example.test", limit=1, window=60))
        self.assertTrue(is_rate_limited("test-login", self.request, identity="one@example.test", limit=1, window=60))
