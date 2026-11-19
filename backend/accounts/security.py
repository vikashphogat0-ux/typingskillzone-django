"""Shared authentication throttling with local and Cloudflare implementations."""
import hashlib

from django.conf import settings
from django.core.cache import cache


def client_ip(request):
    # Local-development fallback only. Production Cloudflare requests are
    # throttled before Django using Cloudflare's edge-provided CF-Connecting-IP.
    return request.META.get("REMOTE_ADDR", "unknown")


def rate_limit_key(scope, request, identity=""):
    raw = f"{scope}:{client_ip(request)}:{identity.strip().lower()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"auth-throttle:{scope}:{digest}"


def is_rate_limited(scope, request, *, identity="", limit=5, window=900):
    """Use the Worker-verified Durable Object result, or local cache in DEBUG.

    In Cloudflare production mode, a missing trusted marker fails closed. The
    Worker strips any client-supplied marker before applying the Durable Object.
    """
    if getattr(settings, "CLOUDFLARE_AUTH_RATE_LIMITING", False):
        return request.META.get("HTTP_X_TSZ_RATE_LIMIT_CHECKED") != "1"

    key = rate_limit_key(scope, request, identity)
    try:
        if cache.add(key, 1, timeout=window):
            return False
        try:
            count = cache.incr(key)
        except ValueError:
            if cache.add(key, 1, timeout=window):
                return False
            count = cache.incr(key)
        return count > limit
    except Exception:
        return True


def is_rate_limit_suppressed(request, scope):
    """True when the Worker has reached an IP resend cap and suppressed email."""
    if not getattr(settings, "CLOUDFLARE_AUTH_RATE_LIMITING", False):
        return False
    if request.META.get("HTTP_X_TSZ_RATE_LIMIT_CHECKED") != "1":
        return False
    scopes = {
        item.strip()
        for item in request.META.get("HTTP_X_TSZ_RATE_LIMIT_SUPPRESS", "").split(",")
        if item.strip()
    }
    return scope in scopes
