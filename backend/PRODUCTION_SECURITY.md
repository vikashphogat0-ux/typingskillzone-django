# Production security configuration

This Django application is separate from the existing Next.js production service. Do not point it at, migrate, or modify the Next.js application's database.


## WSGI application server and static assets

Install production dependencies from the backend directory with `pip install -r requirements.txt`. The WSGI entry point remains `config.wsgi:application`; the production process command is:

```sh
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

WhiteNoise is enabled immediately after Django's SecurityMiddleware and uses compressed, manifest-backed static storage. Run this during the hosting provider's build/release step, before starting Gunicorn:

```sh
python manage.py collectstatic --noinput
```

For local development and tests, install `requirements-dev.txt` instead; it includes the production requirements plus pytest and Playwright tooling. Do not install test tooling in the production image.

## Database and concurrent seat enforcement

Production must use PostgreSQL. SQLite remains the local-development default only. Set these environment variables in the Django hosting environment:

- DJANGO_DEBUG=false
- DJANGO_SECRET_KEY=<strong random secret>
- DJANGO_DB_ENGINE=django.db.backends.postgresql
- DJANGO_DB_NAME=<Django database name>
- DJANGO_DB_USER=<Django database user>
- DJANGO_DB_PASSWORD=<Django database password>
- DJANGO_DB_HOST=<PostgreSQL host>
- DJANGO_DB_PORT=5432
- DJANGO_DB_CONN_MAX_AGE=60

Install the PostgreSQL driver in the Django environment using the Cloudflare-compatible package set validated for the Python Workers runtime. Do not install or configure Redis for this project. The current psycopg-binary wheel and the complete dependency set still require a Cloudflare Python Workers build/runtime compatibility check before deployment.

Run normal Django migrations against the dedicated Django database. Do not run createcachetable or migrations against the Next.js/Neon database.

The membership write path locks the parent Institute row with select_for_update() before checking the current active seat count and inserting the membership. This serializes concurrent seat additions on PostgreSQL. The PostgreSQL-only concurrency regression test is institutes.test_concurrent_seats.ConcurrentSeatLimitTests; it is skipped on SQLite because SQLite cannot prove row-level locking.

## Authentication throttling without Redis

Production authentication throttling runs in `cloudflare_worker.py` before the Django WSGI application. The Worker uses Cloudflare's edge-provided `CF-Connecting-IP`, routes each IP to a deterministic SQLite-backed Durable Object shard, and stores only SHA-256 counter keys (not raw IP addresses or email addresses). The Durable Object performs atomic SQLite upserts with fixed-window expiry. Email resend IP caps suppress delivery while retaining the existing generic success response; email-specific caps retain their existing block responses.

Set `DJANGO_CLOUDFLARE_AUTH_RATE_LIMITING=true` in the Worker environment. Django fails closed if this mode is enabled but the Worker verification marker is absent. The Worker strips client-supplied internal marker headers before checking limits. Do not expose the Django WSGI application through another public origin or bypass the Worker.

Local development continues to use Django's process-local cache fallback. That fallback is not a production multi-instance rate limiter. Redis and django-redis have been removed from production requirements.

The Free plan has finite Durable Object allowances: 100,000 requests/day, 5 million SQLite row reads/day, 100,000 SQLite row writes/day, and 5 GB total SQLite storage. Exceeding a free allowance causes further operations of that type to fail. Configure usage alerts/spending controls where available and monitor usage; this architecture is not guaranteed to remain free above those limits.

## HTTPS, hosts, and cookies

Set DJANGO_ALLOWED_HOSTS to comma-separated exact hostnames and DJANGO_CSRF_TRUSTED_ORIGINS to comma-separated full HTTPS origins, including scheme. Production defaults enable SSL redirect, secure session and CSRF cookies, one-year HSTS, content-type sniffing protection, frame denial, and same-origin referrer policy. HSTS should only be enabled after HTTPS is working for every included hostname.

If TLS terminates at a trusted reverse proxy, set `DJANGO_TRUST_X_FORWARDED_PROTO=true` in that hosting provider's environment only after verifying that the proxy overwrites `X-Forwarded-Proto` and does not pass through client-supplied values. The application already maps this flag to Django's `SECURE_PROXY_SSL_HEADER`. Keep it unset/false for direct connections or proxies that do not guarantee this behavior. The hosting provider has not yet been selected, so no provider-specific environment value is committed here.

## SMTP email delivery

Set DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend, EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, EMAIL_USE_TLS=true for STARTTLS on port 587, and DEFAULT_FROM_EMAIL to a verified sender address. Do not commit credentials.

After deployment, run python manage.py check --deploy and python manage.py check_production_readiness. To send an end-to-end test message, run python manage.py check_production_readiness --send-test-email your-address@example.com and confirm it arrives. SMTP connectivity alone does not prove inbox delivery.

## Required deployment verification

1. Confirm the public hostname routes only through the configured Cloudflare Worker.
2. Confirm the Durable Object binding and SQLite migration are active, and run concurrent counter/expiry tests.
3. Confirm client-supplied internal marker headers cannot bypass throttling and that missing Durable Object connectivity fails closed.
4. Confirm HTTPS redirect, secure cookies, trusted hosts/origins, and HSTS using the deployed hostname.
5. Send and receive the test email.
6. Run the full test suite against PostgreSQL so the concurrency test executes rather than skips.
