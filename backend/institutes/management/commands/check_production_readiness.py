import uuid

from django.conf import settings
from django.core.cache import cache
from django.core.mail import get_connection, send_mail
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Check production database, shared cache, SMTP, HTTPS, hosts and cookie configuration."

    def add_arguments(self, parser):
        parser.add_argument(
            "--send-test-email",
            metavar="EMAIL",
            help="Send a real test email to this address (explicit opt-in).",
        )

    def handle(self, *args, **options):
        failures = []

        def passed(message):
            self.stdout.write(self.style.SUCCESS("OK: " + message))

        def failed(message):
            failures.append(message)
            self.stderr.write(self.style.ERROR("FAIL: " + message))

        if settings.DEBUG:
            failed("DJANGO_DEBUG must be false in production.")
        else:
            passed("DEBUG is disabled.")

        if connection.vendor != "postgresql":
            failed("Production database must be PostgreSQL; current vendor is %s." % connection.vendor)
        else:
            passed("PostgreSQL database is configured.")

        cache_backend = settings.CACHES["default"]["BACKEND"]
        if "django_redis" not in cache_backend.lower():
            failed("Production throttling requires the Redis cache backend with atomic INCR support.")
        else:
            try:
                key = "production-readiness:" + uuid.uuid4().hex
                if not cache.add(key, 1, timeout=30):
                    raise RuntimeError("cache.add did not create a fresh key")
                if cache.incr(key) != 2:
                    raise RuntimeError("cache.incr did not increment atomically")
                cache.delete(key)
                passed("Shared cache add/increment/delete probe succeeded (%s)." % cache_backend)
            except Exception as error:
                failed("Shared cache probe failed: %s" % error)

        if not settings.ALLOWED_HOSTS or "*" in settings.ALLOWED_HOSTS:
            failed("Set explicit DJANGO_ALLOWED_HOSTS values; wildcard is not accepted.")
        else:
            passed("Allowed hosts are explicitly configured.")
        if not settings.CSRF_TRUSTED_ORIGINS or any(
            not origin.startswith("https://") for origin in settings.CSRF_TRUSTED_ORIGINS
        ):
            failed("Set HTTPS-only DJANGO_CSRF_TRUSTED_ORIGINS values.")
        else:
            passed("CSRF trusted origins are HTTPS-only.")

        secure_settings = {
            "SECURE_SSL_REDIRECT": getattr(settings, "SECURE_SSL_REDIRECT", False),
            "SESSION_COOKIE_SECURE": getattr(settings, "SESSION_COOKIE_SECURE", False),
            "CSRF_COOKIE_SECURE": getattr(settings, "CSRF_COOKIE_SECURE", False),
        }
        insecure = [name for name, enabled in secure_settings.items() if not enabled]
        if insecure:
            failed("These HTTPS/cookie protections are disabled: %s." % ", ".join(insecure))
        else:
            passed("HTTPS redirect and secure session/CSRF cookies are enabled.")
        if getattr(settings, "SECURE_HSTS_SECONDS", 0) < 31536000:
            failed("HSTS must be configured for at least one year after HTTPS is confirmed.")
        else:
            passed("HSTS is configured for at least one year.")

        if settings.EMAIL_BACKEND.endswith("console.EmailBackend"):
            failed("Console email backend is development-only.")
        elif not all([settings.EMAIL_HOST, settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD, settings.DEFAULT_FROM_EMAIL]):
            failed("SMTP host, username, password and default sender must all be configured.")
        else:
            try:
                email_connection = get_connection(fail_silently=False)
                email_connection.open()
                email_connection.close()
                passed("SMTP connection and authentication succeeded.")
            except Exception as error:
                failed("SMTP connection failed: %s" % error)

        recipient = options.get("send_test_email")
        if recipient:
            try:
                send_mail(
                    "TypingSkillZone production email test",
                    "This is an explicitly requested SMTP delivery test for the Django application.",
                    settings.DEFAULT_FROM_EMAIL,
                    [recipient],
                    fail_silently=False,
                )
                passed("Test email handed to SMTP server for %s." % recipient)
            except Exception as error:
                failed("Test email could not be sent: %s" % error)

        if failures:
            raise CommandError("Production readiness failed with %s issue(s)." % len(failures))
        self.stdout.write(self.style.SUCCESS("Production readiness checks passed."))
