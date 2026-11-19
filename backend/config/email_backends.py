"""Django email backend that sends through Resend's HTTPS API.

Used when outbound SMTP is blocked by the hosting platform. Requires RESEND_API_KEY.
Only plain-text and HTML bodies are supported; attachments are rejected rather than dropped.
"""
import json
import logging
import os
import urllib.error
import urllib.request

from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"
REQUEST_TIMEOUT_SECONDS = 10


class ResendEmailBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = os.environ.get("RESEND_API_KEY", "")

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not self.api_key:
            if self.fail_silently:
                return 0
            raise RuntimeError("RESEND_API_KEY is not set.")

        sent = 0
        for message in email_messages:
            try:
                self._send(message)
                sent += 1
            except Exception:
                logger.exception("Resend delivery failed for one message.")
                if not self.fail_silently:
                    raise
        return sent

    def _send(self, message):
        if message.attachments:
            raise ValueError("ResendEmailBackend does not send attachments.")

        payload = {
            "from": message.from_email,
            "to": list(message.to),
            "subject": message.subject,
            "text": message.body,
        }
        if message.cc:
            payload["cc"] = list(message.cc)
        if message.bcc:
            payload["bcc"] = list(message.bcc)
        if message.reply_to:
            payload["reply_to"] = list(message.reply_to)
        for content, mimetype in getattr(message, "alternatives", []):
            if mimetype == "text/html":
                payload["html"] = content

        request = urllib.request.Request(
            RESEND_ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                # Without a browser-like User-Agent, Cloudflare in front of Resend can reject the request.
                "User-Agent": "TypingSkillZone/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                response.read()
        except urllib.error.HTTPError as error:
            # Log the status and the provider's error text, never the API key.
            detail = error.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"Resend returned HTTP {error.code}: {detail}") from None
