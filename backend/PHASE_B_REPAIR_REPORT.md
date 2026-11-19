# Phase B — Free Cloudflare Authentication Rate Limiter

## Status

**Implementation prepared on isolated branch `phase-b-free-rate-limiter`; not deployed and not yet runtime-verified.** This branch is based on `phase-a-launch-blockers`. The existing Phase A branch and `main` remain unchanged.

## Scope

Replace the production Redis dependency used solely by authentication throttling with a Cloudflare Python Worker and SQLite-backed Durable Object. Preserve the current Neon PostgreSQL provider and all existing account, authentication, email, institute, exam, typing, payment, and subscription behaviour.

## Changes prepared

- Added `cloudflare_rate_limits.py` to map the existing endpoint scopes, limits, windows, response codes, and suppression-only resend caps.
- Added `cloudflare_worker.py` with an SQLite-backed Durable Object counter shard keyed by a SHA-256 hash of Cloudflare's edge-provided client IP. Counter keys hash scope, IP, and normalized identity. Raw IP/email values are not stored in Durable Object SQLite.
- The Durable Object uses an atomic SQLite UPSERT to increment or reset fixed-window counters. Expired rows are opportunistically cleaned every 128 calls.
- The Worker removes externally supplied internal marker headers, checks rate limits before forwarding to Django, and adds a verified marker only after a successful Durable Object call.
- Django fails closed in Cloudflare production mode if the Worker marker is missing.
- Student and owner resend endpoints retain their existing email-specific blocking and IP-based email-suppression behaviour.
- Password-reset throttling is applied only when Django's email validator accepts the submitted email, and both existing counters are incremented.
- Removed `django-redis` and `redis` from production requirements. Local development uses Django LocMemCache only; production requires the Cloudflare Worker limiter.
- Added pure-Python route/key tests and Django marker/fail-closed tests.
- Added an example Wrangler Durable Object binding. It is intentionally not a complete deployment configuration.

## Existing limits preserved

- Student registration: 5/hour.
- Student resend: 3/email/hour; IP cap 10/hour suppresses delivery.
- Student verification: 10/15 minutes.
- Institute registration: 5/hour.
- Owner login and student/staff login: 8/15 minutes.
- Owner verification: 10/15 minutes.
- Owner resend: 3/email/hour; IP cap 10/hour suppresses delivery.
- Password reset: 3/email/hour and 10/IP/hour.

## Files changed

- `backend/cloudflare_rate_limits.py` — new route plan and key builder.
- `backend/cloudflare_worker.py` — new Worker entrypoint and Durable Object.
- `backend/test_cloudflare_rate_limits.py` — new route/key regression tests.
- `backend/accounts/security.py` — Cloudflare marker validation and local fallback.
- `backend/accounts/views.py` — preserve student resend IP suppression.
- `backend/institutes/owner_verification.py` — preserve owner resend IP suppression.
- `backend/accounts/test_security_throttling.py` — marker and fail-closed tests.
- `backend/config/settings.py` — LocMemCache for local tests; production requires Cloudflare rate-limit mode.
- `backend/requirements.txt` — remove Redis packages.
- `backend/PRODUCTION_SECURITY.md` — document no-Redis design and free-tier limits.
- `backend/wrangler.rate-limiter.example.toml` — example DO binding/migration only.

## Validation status

Not yet executed in this environment:
- Django test suite and PostgreSQL concurrency suite.
- Wrangler/Python Workers build.
- Durable Object SQL runtime tests and concurrent request tests.
- End-to-end request-body/header forwarding tests through `workers.wsgi.fetch`.
- Full Python dependency compatibility and Hyperdrive/Neon runtime validation.

The new route-plan tests are ordinary pytest tests and can run outside Cloudflare. Durable Object integration must be tested with Wrangler/Miniflare before this branch is considered production-ready.

## Free-tier constraints

Cloudflare currently documents Workers Free Durable Objects limits including 100,000 requests/day, 5 million SQLite row reads/day, 100,000 SQLite row writes/day, and 5 GB total SQLite storage. Exceeding a Free limit causes further operations of that type to fail. A zero-cost target is therefore conditional on staying within quotas; it is not an unlimited free hosting guarantee.

## Preservation checks

- No changes to `main`.
- No Neon credentials, roles, schema, migrations, or data changed.
- No database provider change.
- No production migration, DNS change, Cloudflare account resource creation, or deployment performed.
- No authentication architecture, payment gateway, subscription logic, or user records changed.

## Remaining risks

1. Worker request header mutability and WSGI header propagation must be verified under the current Python Workers runtime.
2. Cloudflare's Python Workers runtime/dependency build configuration and Hyperdrive binding are not yet finalized.
3. The sample Wrangler file is not a complete deployable configuration.
4. Free-tier quotas can be exhausted; monitoring and fail-closed handling must be tested.
5. The Phase A Gunicorn/WhiteNoise setup remains provisional for Cloudflare and is outside this Phase B change.
