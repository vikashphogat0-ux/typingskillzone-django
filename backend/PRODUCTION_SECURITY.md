# Production security configuration

This Django application is separate from the existing Next.js production service. Do not point it at, migrate, or modify the Next.js application's database.

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

Install the PostgreSQL driver in the Django environment using: pip install "psycopg[binary]>=3.2,<4".

Run normal Django migrations against the dedicated Django database. Do not run createcachetable or migrations against the Next.js/Neon database.

The membership write path locks the parent Institute row with select_for_update() before checking the current active seat count and inserting the membership. This serializes concurrent seat additions on PostgreSQL. The PostgreSQL-only concurrency regression test is institutes.test_concurrent_seats.ConcurrentSeatLimitTests; it is skipped on SQLite because SQLite cannot prove row-level locking.

## Shared cache and throttling

The production default is Django's database cache, shared across all Django web workers using the same Django database. Create its table once with: python manage.py createcachetable django_cache

Set DJANGO_CACHE_LOCATION to the chosen table name if it differs. Alternatively configure a shared Redis-compatible cache with DJANGO_CACHE_BACKEND and DJANGO_CACHE_LOCATION, and install that backend's Python package. Never use local-memory cache for a multi-worker production deployment. Rate-limit counters use atomic cache increments and fail closed if cache operations fail.

## HTTPS, hosts, and cookies

Set DJANGO_ALLOWED_HOSTS to comma-separated exact hostnames and DJANGO_CSRF_TRUSTED_ORIGINS to comma-separated full HTTPS origins, including scheme. Production defaults enable SSL redirect, secure session and CSRF cookies, one-year HSTS, content-type sniffing protection, frame denial, and same-origin referrer policy. HSTS should only be enabled after HTTPS is working for every included hostname.

If TLS terminates at a trusted reverse proxy, set DJANGO_TRUST_X_FORWARDED_PROTO=true only when that proxy overwrites X-Forwarded-Proto and does not pass through client-supplied values. Otherwise leave it disabled.

## SMTP email delivery

Set DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend, EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, EMAIL_USE_TLS=true for STARTTLS on port 587, and DEFAULT_FROM_EMAIL to a verified sender address. Do not commit credentials.

After deployment, run python manage.py check --deploy and python manage.py check_production_readiness. To send an end-to-end test message, run python manage.py check_production_readiness --send-test-email your-address@example.com and confirm it arrives. SMTP connectivity alone does not prove inbox delivery.

## Required deployment verification

1. Confirm all Django workers use the same PostgreSQL database and shared cache.
2. Confirm the cache table exists and a cache add/increment/delete probe succeeds.
3. Confirm HTTPS redirect, secure cookies, trusted hosts/origins, and HSTS using the deployed hostname.
4. Send and receive the test email.
5. Run the full test suite against PostgreSQL so the concurrency test executes rather than skips.
