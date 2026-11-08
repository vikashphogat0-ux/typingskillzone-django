"""Isolated Cloudflare Python Worker adapter for the existing Django app.

The Wrangler configuration binds a dedicated preview Hyperdrive resource.
The runtime-only health endpoint does not exercise that connection; normal
Django routes may access the configured preview database when invoked.
Never bind the production Hyperdrive resource or run migrations from a Worker.
"""

import asyncio
import hmac
import json
import os
import sys
import uuid
from urllib.parse import urlsplit
from pathlib import Path

from workers import Response, WorkerEntrypoint, wsgi

BACKEND_DIR = str(Path(__file__).resolve().parent)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

_django_application = None
# Hyperdrive requires synchronous database operations to be serialized.
# WSGI does not expose a narrower async boundary around Django ORM calls, so
# this preview adapter conservatively serializes each request per Worker isolate.
_request_lock = asyncio.Lock()


def _binding_value(binding, name):
    try:
        value = getattr(binding, name)
    except Exception:
        return ""
    return str(value) if value is not None else ""


def _configure_django(worker_env):
    """Load explicitly supplied Worker secrets and a test DB binding."""
    secret_names = (
        "DJANGO_SECRET_KEY",
        "DJANGO_ALLOWED_HOSTS",
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "DJANGO_CACHE_URL",
        "DJANGO_EMAIL_BACKEND",
        "PREVIEW_DIAGNOSTIC_TOKEN",
        "EMAIL_HOST",
        "EMAIL_PORT",
        "EMAIL_HOST_USER",
        "EMAIL_HOST_PASSWORD",
        "EMAIL_USE_TLS",
        "DEFAULT_FROM_EMAIL",
    )
    for name in secret_names:
        value = _binding_value(worker_env, name)
        if value:
            os.environ[name] = value

    # Do not silently fall back to SQLite, local-memory cache, or console email.
    os.environ.setdefault(
        "DJANGO_EMAIL_BACKEND",
        "django.core.mail.backends.smtp.EmailBackend",
    )
    os.environ["DJANGO_DEBUG"] = "false"
    os.environ["DJANGO_DB_ENGINE"] = "django.db.backends.postgresql"
    os.environ["DJANGO_DB_CONN_MAX_AGE"] = "0"

    try:
        hyperdrive = worker_env.HYPERDRIVE
    except Exception:
        hyperdrive = None

    if hyperdrive is None:
        raise RuntimeError("A dedicated test HYPERDRIVE binding is required.")

    database_values = {
        "DJANGO_DB_NAME": _binding_value(hyperdrive, "database"),
        "DJANGO_DB_USER": _binding_value(hyperdrive, "user"),
        "DJANGO_DB_PASSWORD": _binding_value(hyperdrive, "password"),
        "DJANGO_DB_HOST": _binding_value(hyperdrive, "host"),
        "DJANGO_DB_PORT": _binding_value(hyperdrive, "port") or "5432",
    }
    if not all(database_values.values()):
        raise RuntimeError("The test HYPERDRIVE binding is incomplete.")

    os.environ.update(database_values)

    required = (
        "DJANGO_SECRET_KEY",
        "DJANGO_ALLOWED_HOSTS",
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "DJANGO_CACHE_URL",
        "EMAIL_HOST",
        "EMAIL_HOST_USER",
        "EMAIL_HOST_PASSWORD",
        "DEFAULT_FROM_EMAIL",
    )
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Worker configuration is incomplete: " + ", ".join(missing)
        )


def _runtime_diagnostics(request, worker_env):
    """Run non-destructive preview checks; never send email or expose secrets."""
    expected_token = _binding_value(worker_env, "PREVIEW_DIAGNOSTIC_TOKEN")
    supplied = request.headers.get("authorization", "")
    prefix = "Bearer "
    if not expected_token or not supplied.startswith(prefix):
        return Response("Unauthorized", status=401)
    if not hmac.compare_digest(supplied[len(prefix):], expected_token):
        return Response("Unauthorized", status=401)

    from django.apps import apps
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.core.cache import cache
    from django.db import connection

    checks = {"database": False, "redis_cache": False, "django_auth": False, "smtp_configuration": False}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            checks["database"] = cursor.fetchone()[0] == 1
    except Exception:
        pass

    cache_key = "tsz:preview:diagnostic:" + uuid.uuid4().hex
    cache_value = uuid.uuid4().hex
    try:
        cache.set(cache_key, cache_value, timeout=30)
        checks["redis_cache"] = cache.get(cache_key) == cache_value
    except Exception:
        pass
    finally:
        try:
            cache.delete(cache_key)
        except Exception:
            pass

    try:
        checks["django_auth"] = apps.ready and get_user_model() is not None
    except Exception:
        pass

    checks["smtp_configuration"] = bool(
        settings.EMAIL_HOST and settings.EMAIL_PORT and settings.EMAIL_HOST_USER
        and settings.EMAIL_HOST_PASSWORD and settings.DEFAULT_FROM_EMAIL
        and settings.EMAIL_BACKEND.endswith("smtp.EmailBackend")
    )
    all_passed = all(checks.values())
    payload = {"status": "ok" if all_passed else "degraded", "checks": checks,
               "email_delivery_tested": False, "database_writes": False, "migrations_run": False}
    return Response(json.dumps(payload), status=200 if all_passed else 503,
                    headers={"content-type": "application/json; charset=utf-8"})

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        global _django_application

        request_path = urlsplit(request.url).path
        if request_path == "/_worker-healthz":
            return Response(
                "TypingSkillZone Cloudflare preview runtime is alive. "
                "This endpoint does not check database connectivity.",
                status=200,
                headers={"content-type": "text/plain; charset=utf-8"},
            )

        try:
            async with _request_lock:
                if _django_application is None:
                    _configure_django(self.env)
                    from django.core.wsgi import get_wsgi_application

                    _django_application = get_wsgi_application()

                if request_path == "/_preview-runtime-check":
                    if request.method != "POST":
                        return Response("Method not allowed", status=405)
                    return _runtime_diagnostics(request, self.env)

                return await wsgi.fetch(_django_application, request, self.env)
        except Exception:
            # Never expose exception details, secrets, or connection metadata.
            return Response(
                "TypingSkillZone preview is not configured. "
                "Check Worker secrets and the dedicated test bindings.",
                status=503,
                headers={"content-type": "text/plain; charset=utf-8"},
            )
