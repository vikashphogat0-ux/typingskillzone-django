"""Pure routing and key-building rules for Cloudflare-backed auth throttling.

The counter key intentionally matches accounts.security.rate_limit_key(): scope,
trusted client IP, and normalized identity are SHA-256 hashed before storage.
"""
import hashlib


def counter_key(scope, client_ip, identity=""):
    raw = f"{scope}:{client_ip}:{identity.strip().lower()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"auth-throttle:{scope}:{digest}"


def _check(scope, client_ip, identity, limit, window, *, suppress_only=False):
    return {
        "scope": scope,
        "identity": identity.strip().lower(),
        "key": counter_key(scope, client_ip, identity),
        "limit": limit,
        "window": window,
        "suppress_only": suppress_only,
    }


def build_rate_limit_plan(path, method, form, client_ip, *, valid_password_reset_email=False):
    """Return the exact legacy throttle checks for one incoming request."""
    if method.upper() != "POST":
        return None

    value = lambda name: (form.get(name) or "").strip()
    email = value("email").lower()
    username = value("username").lower()

    if path == "/accounts/student/register/":
        return {"checks": [_check("student-register", client_ip, "", 5, 3600)], "blocked_status": 429, "blocked_message": "Too many registration attempts. Please try again later.", "stop_on_limit": True}
    if path == "/accounts/student/verify/resend/":
        return {"checks": [_check("student-resend", client_ip, email, 3, 3600), _check("student-resend-ip", client_ip, "", 10, 3600, suppress_only=True)], "blocked_status": 429, "blocked_message": "Too many requests. Please try again later.", "stop_on_limit": True}
    if path.startswith("/accounts/student/verify/") and path != "/accounts/student/verify/resend/":
        return {"checks": [_check("student-verify", client_ip, "", 10, 900)], "blocked_status": 429, "blocked_message": "Too many verification attempts. Please try again later.", "stop_on_limit": True}
    if path == "/institutes/register/":
        return {"checks": [_check("institute-register", client_ip, "", 5, 3600)], "blocked_status": 403, "blocked_message": "Too many registration attempts. Please try again later.", "stop_on_limit": True}
    if path == "/institutes/owner/login/":
        return {"checks": [_check("owner-login", client_ip, username, 8, 900)], "blocked_status": 403, "blocked_message": "Too many login attempts. Please try again later.", "stop_on_limit": True}
    if path == "/institutes/student/login/":
        return {"checks": [_check("student-login", client_ip, username, 8, 900)], "blocked_status": 403, "blocked_message": "Too many login attempts. Please try again later.", "stop_on_limit": True}
    if path == "/institutes/staff/login/":
        return {"checks": [_check("staff-login", client_ip, username, 8, 900)], "blocked_status": 403, "blocked_message": "Too many login attempts. Please try again later.", "stop_on_limit": True}
    if path.startswith("/institutes/owner/verify/") and path != "/institutes/owner/verify/resend/":
        return {"checks": [_check("owner-verify", client_ip, "", 10, 900)], "blocked_status": 403, "blocked_message": "Too many verification attempts. Please try again later.", "stop_on_limit": True}
    if path == "/institutes/owner/verify/resend/":
        return {"checks": [_check("owner-resend", client_ip, email, 3, 3600), _check("owner-resend-ip", client_ip, "", 10, 3600, suppress_only=True)], "blocked_status": 403, "blocked_message": "Too many requests. Please try again later.", "stop_on_limit": True}
    if path == "/accounts/password-reset/" and valid_password_reset_email:
        return {"checks": [_check("password-reset-email", client_ip, email, 3, 3600), _check("password-reset-ip", client_ip, "", 10, 3600)], "blocked_status": 429, "blocked_message": "Too many password reset requests. Please try again later.", "stop_on_limit": False}
    return None
