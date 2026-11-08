"""Isolated Cloudflare Python Worker adapter for the existing Django app.

This preview adapter deliberately does not connect to a database yet.
A separate Neon test branch and a dedicated Hyperdrive binding must be
created before database access is enabled.
"""

import os
import sys
from pathlib import Path

from workers import Response, WorkerEntrypoint, wsgi

BACKEND_DIR = str(Path(__file__).resolve().parent)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

_django_application = None


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


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        global _django_application

        if request.url.endswith("/_worker-healthz"):
            return Response(
                "TypingSkillZone Cloudflare preview runtime is alive. "
                "This endpoint does not check database connectivity.",
                status=200,
                headers={"content-type": "text/plain; charset=utf-8"},
            )

        try:
            if _django_application is None:
                _configure_django(self.env)
                from django.core.wsgi import get_wsgi_application

                _django_application = get_wsgi_application()

            return await wsgi.fetch(_django_application, request, self.env)
        except Exception:
            # Never expose exception details, secrets, or connection metadata.
            return Response(
                "TypingSkillZone preview is not configured. "
                "Check Worker secrets and the dedicated test bindings.",
                status=503,
                headers={"content-type": "text/plain; charset=utf-8"},
            )
