"""Small cache-backed throttling helpers for public authentication endpoints.

Production deployments with multiple workers should configure a shared Django cache.
The default local-memory cache is suitable for development and single-process deployments only.
"""
import hashlib

from django.core.cache import cache


def client_ip(request):
    # Do not trust X-Forwarded-For unless a trusted proxy has been configured.
    return request.META.get("REMOTE_ADDR", "unknown")


def rate_limit_key(scope, request, identity=""):
    raw = f"{scope}:{client_ip(request)}:{identity.strip().lower()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"auth-throttle:{scope}:{digest}"


def is_rate_limited(scope, request, *, identity="", limit=5, window=900):
    key = rate_limit_key(scope, request, identity)
    try:
        count = cache.get(key)
        if count is None:
            cache.add(key, 1, timeout=window)
            return False
        if count >= limit:
            return True
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, count + 1, timeout=window)
        return False
    except Exception:
        # Fail closed for authentication abuse controls if cache is unavailable.
        return True
