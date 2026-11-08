# Cloudflare Django preview

This is an isolated preview adapter for the existing Django application.

## Safety boundary

- This configuration is not production deployment configuration.
- Do not bind the existing production Hyperdrive resource.
- Create a separate Neon development branch first, then create a dedicated
  Hyperdrive configuration for that development branch.
- Do not run migrations from the Worker.
- Do not add production credentials to local files or Git.
- Do not enable production traffic until the full verification checklist passes.

## Runtime

The Worker uses the existing Django WSGI application through Cloudflare's
Python Workers WSGI adapter. The application source remains under backend/.
The health endpoint /_worker-healthz only confirms that the Worker runtime
can answer a request; it does not test Django, PostgreSQL, Redis, or email.

## Required preview bindings and secrets

After creating a dedicated Neon test branch and Hyperdrive configuration,
bind that test configuration as HYPERDRIVE. Do not reuse the production
Hyperdrive ID.

Configure these Worker secrets/variables only after the test resources exist:

- DJANGO_SECRET_KEY
- DJANGO_ALLOWED_HOSTS
- DJANGO_CSRF_TRUSTED_ORIGINS
- DJANGO_CACHE_URL
- EMAIL_HOST
- EMAIL_PORT
- EMAIL_HOST_USER
- EMAIL_HOST_PASSWORD
- EMAIL_USE_TLS
- DEFAULT_FROM_EMAIL

The adapter obtains PostgreSQL host, port, database, username and password
from the HYPERDRIVE binding at runtime. Django persistent connections are
disabled (CONN_MAX_AGE=0) because Hyperdrive owns connection pooling.

The current application requires a shared Redis cache and SMTP email backend
in production. Those services must be provisioned and tested before normal
Django routes are enabled.

## Local Django WSGI smoke test

A separate local-only entrypoint is provided for verifying that Django can
initialize and serve a request through the Workers WSGI adapter without
external services:

- Entry point: `backend/cloudflare_local_test_worker.py`
- Settings: `config.cloudflare_test_settings`
- Route: `/_django-runtime-check`

This harness uses an in-memory SQLite configuration, local-memory cache,
in-memory email backend, and no middleware. It does not exercise application
business views, database persistence, authentication, Redis, SMTP, or
Hyperdrive. It must not be used as a deployed Worker entrypoint.

For local testing, point a separate untracked `wrangler.local.jsonc` at
`backend/cloudflare_local_test_worker.py`. Keep the normal
`wrangler.jsonc` and its isolated Neon Hyperdrive binding unchanged.

## Local tooling

Install uv and Node.js, then run:

~~~powershell
uv sync
uv run pywrangler dev
~~~

The health endpoint can be checked locally at:

~~~text
http://localhost:8787/_worker-healthz
~~~

A local health response does not prove that the Django app or database is
working. A database-enabled test requires a separate test Neon branch,
Hyperdrive local configuration, Redis, and non-production email credentials.

## Deployment gates

1. Confirm Python package compatibility in Pyodide, especially Django,
   psycopg, Pillow and ReportLab.
2. Create and verify the separate Neon test branch.
3. Create a separate Hyperdrive resource for that branch and bind it as
   HYPERDRIVE.
4. Verify Django's WSGI adapter and PostgreSQL transactions, row locking,
   sessions and authentication.
5. Verify Redis throttling and SMTP email delivery.
6. Configure static asset delivery and persistent file storage if required.
7. Run the complete application regression suite before considering release.

No database migration, production connection, or production deployment is
performed by this preview scaffold.
