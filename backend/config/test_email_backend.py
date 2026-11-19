import io
import json
import os
import urllib.error
from unittest import mock

from django.core.mail import EmailMultiAlternatives
from django.test import SimpleTestCase, override_settings

from config.email_backends import RESEND_ENDPOINT, ResendEmailBackend


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ResendBackendTests(SimpleTestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"RESEND_API_KEY": "re_test_key_not_real"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _message(self):
        message = EmailMultiAlternatives(
            "Verify your account", "Plain body", "TypingSkillZone <support@typingskillzone.in>",
            ["student@example.com"], reply_to=["support@typingskillzone.in"],
        )
        message.attach_alternative("<p>HTML body</p>", "text/html")
        return message

    @mock.patch("config.email_backends.urllib.request.urlopen", return_value=FakeResponse(b"{}"))
    def test_sends_expected_request(self, urlopen):
        sent = ResendEmailBackend().send_messages([self._message()])
        self.assertEqual(sent, 1)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, RESEND_ENDPOINT)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer re_test_key_not_real")
        self.assertTrue(request.get_header("User-agent").startswith("TypingSkillZone"))
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["to"], ["student@example.com"])
        self.assertEqual(body["subject"], "Verify your account")
        self.assertEqual(body["text"], "Plain body")
        self.assertEqual(body["html"], "<p>HTML body</p>")
        self.assertEqual(body["reply_to"], ["support@typingskillzone.in"])

    @mock.patch("config.email_backends.urllib.request.urlopen")
    def test_provider_error_never_contains_api_key(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError(
            RESEND_ENDPOINT, 403, "Forbidden", {}, io.BytesIO(b'{"message":"domain not verified"}')
        )
        with self.assertRaises(RuntimeError) as raised:
            ResendEmailBackend().send_messages([self._message()])
        self.assertIn("403", str(raised.exception))
        self.assertNotIn("re_test_key_not_real", str(raised.exception))

    def test_attachments_are_rejected_not_dropped(self):
        message = self._message()
        message.attach("notes.txt", "data", "text/plain")
        with self.assertRaises(ValueError):
            ResendEmailBackend().send_messages([message])

    def test_missing_key_fails_loudly_unless_fail_silently(self):
        with mock.patch.dict(os.environ, {"RESEND_API_KEY": ""}):
            with self.assertRaises(RuntimeError):
                ResendEmailBackend().send_messages([self._message()])
            self.assertEqual(ResendEmailBackend(fail_silently=True).send_messages([self._message()]), 0)
