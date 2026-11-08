"""Local-only Django settings for the Cloudflare WSGI smoke test.

This module must never be used by a deployed Worker. It deliberately avoids
external services and application data so the WSGI adapter can be tested
without Neon, Redis, SMTP, or migrations.
"""

from .settings import *  # noqa: F403

ROOT_URLCONF = "config.cloudflare_test_urls"
MIDDLEWARE = []
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "typingskillzone-cloudflare-local-smoke-test",
    }
}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
