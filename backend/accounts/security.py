"""Cache-backed, atomic throttling for public authentication endpoints."""
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
    """Atomically count attempts; fail closed if the shared cache is unavailable."""
    key = rate_limit_key(scope, request, identity)
    try:
        if cache.add(key, 1, timeout=window):
            return False
        try:
            count = cache.incr(key)
        except ValueError:
            # The key expired between add() and incr(). Recreate it safely.
            if cache.add(key, 1, timeout=window):
                return False
            count = cache.incr(key)
        return count > limit
    except Exception:
        # Fail closed for authentication abuse controls if cache is unavailable.
        return True
