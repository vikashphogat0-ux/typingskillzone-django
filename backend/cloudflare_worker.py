"""Cloudflare Python Worker entrypoint and SQLite Durable Object rate limiter.

This Worker must be the only public entrypoint to the Django WSGI application.
Cloudflare supplies CF-Connecting-IP at the edge; client-supplied internal
rate-limit marker headers are removed before Django receives the request.
"""
import os
import time
import hashlib
from urllib.parse import parse_qs, urlparse

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.core.wsgi import get_wsgi_application
from workers import DurableObject, Response, WorkerEntrypoint, wsgi

from cloudflare_rate_limits import build_rate_limit_plan

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()


class AuthRateLimiter(DurableObject):
    """One SQLite-backed counter shard per trusted client IP."""

    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.ctx = ctx
        self.env = env
        self._calls = 0
        self.ctx.storage.sql.exec(
            """
            CREATE TABLE IF NOT EXISTS auth_rate_limit_counters (
                counter_key TEXT PRIMARY KEY,
                count INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            )
            """
        )

    async def consume_many(self, checks, stop_on_limit=True):
        now = int(time.time())
        blocked = False
        suppressed_scopes = []

        for check in checks:
            result = self.ctx.storage.sql.exec(
                """
                INSERT INTO auth_rate_limit_counters (counter_key, count, expires_at)
                VALUES (?, 1, ?)
                ON CONFLICT(counter_key) DO UPDATE SET
                    count = CASE
                        WHEN auth_rate_limit_counters.expires_at <= ? THEN 1
                        ELSE auth_rate_limit_counters.count + 1
                    END,
                    expires_at = CASE
                        WHEN auth_rate_limit_counters.expires_at <= ?
                            THEN excluded.expires_at
                        ELSE auth_rate_limit_counters.expires_at
                    END
                RETURNING count
                """,
                check["key"],
                now + int(check["window"]),
                now,
                now,
            ).one()

            if int(result.count) > int(check["limit"]):
                if check.get("suppress_only"):
                    suppressed_scopes.append(check["scope"])
                else:
                    blocked = True
                    if stop_on_limit:
                        break

        self._calls += 1
        if self._calls % 128 == 0:
            self.ctx.storage.sql.exec(
                "DELETE FROM auth_rate_limit_counters WHERE expires_at <= ?",
                now,
            )

        return {"blocked": blocked, "suppressed_scopes": suppressed_scopes}


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        # Never accept these internal headers from an external caller.
        request.headers.delete("X-Tsz-Rate-Limit-Checked")
        request.headers.delete("X-Tsz-Rate-Limit-Suppress")

        parsed_url = urlparse(request.url)
        path = parsed_url.path
        plan = None

        if request.method.upper() == "POST":
            try:
                body = await request.clone().text()
                form_values = parse_qs(body, keep_blank_values=True)
                form = {key: values[0] for key, values in form_values.items() if values}
            except Exception:
                # A protected endpoint with an unreadable body must not bypass
                # its authentication throttle.
                if path in {
                    "/accounts/student/register/",
                    "/accounts/student/verify/resend/",
                    "/institutes/register/",
                    "/institutes/owner/login/",
                    "/institutes/student/login/",
                    "/institutes/staff/login/",
                    "/institutes/owner/verify/resend/",
                    "/accounts/password-reset/",
                } or path.startswith("/accounts/student/verify/") or path.startswith("/institutes/owner/verify/"):
                    return Response("Authentication protection temporarily unavailable.", status=503)
                form = {}
            client_ip = request.headers.get("CF-Connecting-IP")
            if client_ip:
                valid_reset_email = False
                if path == "/accounts/password-reset/":
                    try:
                        validate_email((form.get("email") or "").strip())
                        valid_reset_email = True
                    except ValidationError:
                        pass

                plan = build_rate_limit_plan(
                    path,
                    request.method,
                    form,
                    client_ip,
                    valid_password_reset_email=valid_reset_email,
                )
            elif path in {
                "/accounts/student/register/",
                "/accounts/student/verify/resend/",
                "/institutes/register/",
                "/institutes/owner/login/",
                "/institutes/student/login/",
                "/institutes/staff/login/",
                "/institutes/owner/verify/resend/",
                "/accounts/password-reset/",
            } or path.startswith("/accounts/student/verify/") or path.startswith("/institutes/owner/verify/"):
                return Response("Authentication protection temporarily unavailable.", status=503)

        if plan:
            try:
                ip_shard = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()
                object_id = self.env.AUTH_RATE_LIMITER.idFromName(ip_shard)
                limiter = self.env.AUTH_RATE_LIMITER.get(object_id)
                outcome = await limiter.consume_many(
                    plan["checks"],
                    plan["stop_on_limit"],
                )
            except Exception:
                # Fail closed if the shared, durable limiter cannot be reached.
                return Response("Authentication protection temporarily unavailable.", status=503)

            if outcome["blocked"]:
                return Response(
                    plan["blocked_message"],
                    status=plan["blocked_status"],
                    headers={"Content-Type": "text/plain; charset=utf-8"},
                )

            request.headers.set("X-Tsz-Rate-Limit-Checked", "1")
            if outcome["suppressed_scopes"]:
                request.headers.set(
                    "X-Tsz-Rate-Limit-Suppress",
                    ",".join(outcome["suppressed_scopes"]),
                )

        return await wsgi.fetch(application, request, self.env)
