"""A database-free URL used only by the local Cloudflare WSGI smoke test."""

from django.http import JsonResponse
from django.urls import path


def runtime_check(request):
    return JsonResponse(
        {
            "status": "ok",
            "component": "django-wsgi",
            "mode": "local-only-smoke-test",
        }
    )


urlpatterns = [
    path("_django-runtime-check", runtime_check, name="cloudflare-runtime-check"),
]
