from django.test import RequestFactory, SimpleTestCase, override_settings

from accounts import security


class ClientIpTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(RATE_LIMIT_CLIENT_IP_HEADER="")
    def test_without_configured_header_uses_remote_addr(self):
        request = self.factory.get("/", REMOTE_ADDR="192.0.2.10")
        self.assertEqual(security.client_ip(request), "192.0.2.10")

    @override_settings(RATE_LIMIT_CLIENT_IP_HEADER="X-Forwarded-For", RATE_LIMIT_TRUSTED_PROXY_HOPS=1)
    def test_forwarded_for_uses_rightmost_entry_so_clients_cannot_choose_identity(self):
        request = self.factory.get(
            "/", REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_FOR="9.9.9.9, 203.0.113.5"
        )
        self.assertEqual(security.client_ip(request), "203.0.113.5")

    @override_settings(RATE_LIMIT_CLIENT_IP_HEADER="X-Forwarded-For", RATE_LIMIT_TRUSTED_PROXY_HOPS=1)
    def test_missing_forwarded_for_fails_closed_instead_of_using_proxy_address(self):
        request = self.factory.get("/", REMOTE_ADDR="10.0.0.5")
        self.assertEqual(security.client_ip(request), security.UNTRUSTED_CLIENT_BUCKET)

    @override_settings(RATE_LIMIT_CLIENT_IP_HEADER="X-Forwarded-For", RATE_LIMIT_TRUSTED_PROXY_HOPS=1)
    def test_malformed_forwarded_for_fails_closed(self):
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="not-an-address")
        self.assertEqual(security.client_ip(request), security.UNTRUSTED_CLIENT_BUCKET)

    @override_settings(RATE_LIMIT_CLIENT_IP_HEADER="CF-Connecting-IP")
    def test_cloudflare_header_is_read_as_single_address(self):
        request = self.factory.get("/", HTTP_CF_CONNECTING_IP="198.51.100.20")
        self.assertEqual(security.client_ip(request), "198.51.100.20")

    @override_settings(RATE_LIMIT_CLIENT_IP_HEADER="CF-Connecting-IP")
    def test_raw_address_never_appears_in_cache_key(self):
        request = self.factory.get("/", HTTP_CF_CONNECTING_IP="198.51.100.20")
        self.assertNotIn("198.51.100.20", security.rate_limit_key("student-login", request))
