"""Cache-backed, atomic throttling for public authentication endpoints."""
import hashlib
import ipaddress
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

UNTRUSTED_CLIENT_BUCKET = "untrusted-client"


def _meta_key(header_name):
    return "HTTP_" + header_name.strip().upper().replace("-", "_")


def client_ip(request):
    """Return the client address used for throttling.

    REMOTE_ADDR is used only when no client-IP header is configured (local development).
    When a header is configured it is read only from that named header. For X-Forwarded-For,
    the address is taken DJANGO_RATE_LIMIT_TRUSTED_PROXY_HOPS entries from the right, so
    client-supplied leading entries cannot choose the identity. Missing or malformed values
    map to one shared bucket (fail closed) instead of falling back to the proxy address.
    """
    header = getattr(settings, "RATE_LIMIT_CLIENT_IP_HEADER", "")
    if not header:
        return request.META.get("REMOTE_ADDR") or "unknown"

    raw = request.META.get(_meta_key(header), "")
    if header.strip().lower() == "x-forwarded-for":
        entries = [part.strip() for part in raw.split(",") if part.strip()]
        hops = max(1, int(getattr(settings, "RATE_LIMIT_TRUSTED_PROXY_HOPS", 1)))
        candidate = entries[-hops] if len(entries) >= hops else ""
    else:
        candidate = raw.strip()

    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        logger.warning("Client-IP header %s missing or malformed; using shared bucket.", header)
        return UNTRUSTED_CLIENT_BUCKET


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
