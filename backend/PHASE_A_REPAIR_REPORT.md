# Phase A Repair Report — Typing Skill Zone Project B

**Date:** 2026-11-18  
**Branch:** `phase-a-launch-blockers`  
**Base branch:** `main`  
**Overall status:** **PARTIALLY IMPLEMENTED — NOT VERIFIED; DO NOT DEPLOY**  
**Scope:** DEP-01, DEP-02, ROUTE-01, ROUTE-02, DEP-03, DEP-05 only

## 1. Executive summary

Phase A changes have been committed to the isolated `phase-a-launch-blockers` branch. The `main` branch has not been modified. No database operation, migration, provider change, DNS change, deployment, authentication architecture change, or payment/subscription change was performed.

Four issue areas have code/documentation changes prepared: portal-specific login redirects, the public homepage, dependency separation, and provisional static-file configuration. The hosting target is now Cloudflare Python Workers. This changes the DEP-01/DEP-02/DEP-03 implementation: Cloudflare's WSGI adapter hosts Django without a conventional Gunicorn process, and Cloudflare Worker static assets are the preferred static delivery mechanism. The current Gunicorn/WhiteNoise setup is therefore provisional and must be reconciled before Phase A can be declared complete. No Cloudflare Worker entry point, Wrangler configuration, Hyperdrive binding, Redis binding, or deployment has been added. Existing PostgreSQL/Redis connectivity and Python package compatibility still require verification.

**No automated tests have completed successfully.** The GitHub Actions run for the updated workflow was cancelled during PostgreSQL service-container initialization before checkout or test steps; an older pre-correction run failed. Regression tests were added, but they must not be described as passing until a complete run finishes.

## 2. Change inventory

| File | Change |
|---|---|
| `backend/requirements.txt` | Added pinned Gunicorn and WhiteNoise as an initial conventional-WSGI implementation; removed test/browser tooling from production dependencies. These two production choices are under review for the selected Cloudflare Workers target. |
| `backend/requirements-dev.txt` | Added development/test dependency file including production requirements plus pinned pytest and Playwright tooling. |
| `backend/config/settings.py` | Added WhiteNoise middleware after SecurityMiddleware; configured compressed manifest static storage; changed STATIC_URL to root-relative `/static/`; set default LOGIN_URL to student login. Existing WSGI_APPLICATION and proxy-header conditional retained. |
| `backend/config/urls.py` | Added the public root route named `home`. |
| `backend/passages/views.py` | Added a public homepage view. Existing simulator views remain protected. |
| `backend/passages/templates/passages/base.html` | Added links to the public home, student login, student registration, institute owner login, and admin studio using the existing visual style. |
| `backend/passages/templates/passages/home.html` | Added the public landing page using the existing shared base template and portal routes. |
| `backend/institutes/views.py` | Added explicit owner login URLs to owner-protected views; retained explicit admin login URLs; made student/staff member dashboard and logout redirects portal-specific. |
| `backend/accounts/tests.py` | Added anonymous student dashboard and result-history redirect regression tests. |
| `backend/institutes/tests.py` | Added owner, staff, and super-admin redirect regression tests. |
| `backend/passages/tests.py` | Added homepage, simulator redirect, WhiteNoise/static configuration, and WSGI preservation regression tests. |
| `backend/PRODUCTION_SECURITY.md` | Documented the initial conventional-WSGI/Gunicorn path, collectstatic, dev dependency installation, and trusted-proxy requirements; this document must be revised for Cloudflare Workers before deployment. |
| `.github/workflows/django-ci.yml` | Updated CI to install `requirements-dev.txt` and use Python 3.14, aligning test dependencies with the new split and the currently documented Python Workers runtime generation. |

**Not modified:** `backend/config/wsgi.py`. The existing `config.wsgi:application` entry point is preserved.

## 3. Issue-by-issue implementation

### DEP-01 — Production application entry point (Cloudflare target)

- **Initial branch change:** `backend/requirements.txt` adds `gunicorn==23.0.0` for a conventional WSGI host.
- **Cloudflare finding:** Cloudflare Python Workers provides a WSGI adapter for Django. A normal Gunicorn process is not the Worker entry point; the Worker entry module must call `get_wsgi_application()` and pass it to `workers.wsgi.entrypoint()` (or `workers.wsgi.fetch()`).
- **Current result:** **NOT CLOSED for Cloudflare.** No Worker entry module or Wrangler configuration has been added yet, and the provisional Gunicorn dependency/documentation must be revised after the complete dependency/runtime audit.
- **Tests executed:** None. `pywrangler dev` and Worker request handling have not been tested.
- **Remaining risks:** Python Workers run on Pyodide/WebAssembly. The project's full dependency set and Django runtime behaviour must be proven in that environment before this target is considered viable.

### DEP-02 — Static files not served in production

- **Initial branch change:** WhiteNoise middleware and compressed manifest storage were added to Django settings, with `collectstatic` documented.
- **Cloudflare finding:** Cloudflare Workers supports native static asset bindings, which can serve collected files at the edge independently of the Django Worker. This is the preferred production delivery path to validate for this target.
- **Current result:** **PARTIALLY IMPLEMENTED, NOT VERIFIED.** The WhiteNoise configuration remains in the branch, but no Wrangler `assets.directory` configuration exists yet. The correct collected-static directory, URL behaviour, admin assets, and asset/Worker routing still need a local Worker test.
- **Tests executed:** None. `collectstatic` and Worker static requests have not been tested.
- **Remaining risks:** Do not assume that a normal server filesystem or WhiteNoise alone is sufficient inside the Workers runtime.

### ROUTE-01 — Incorrect student login redirect

- **Files changed:** `backend/config/settings.py`, `backend/institutes/views.py`, and redirect tests in `accounts/tests.py`, `institutes/tests.py`, and `passages/tests.py`
- **Original problem:** The global LOGIN_URL pointed to `/admin/login/`, so anonymous students opening protected student pages were sent to the admin portal.
- **Exact correction:** Changed the default LOGIN_URL to `/institutes/student/login/`. Owner-protected views explicitly use `/institutes/owner/login/`; super-admin views explicitly retain `/admin/login/`. The shared student/staff member dashboard and logout handlers select the appropriate portal login route based on the requested portal.
- **Reason:** Student redirects are corrected without sending owners, staff, or administrators to the wrong portal.
- **Tests added:** Student dashboard, result history, simulator, owner dashboard/member list, staff dashboard, and super-admin dashboard redirect regression tests.
- **Tests executed:** None; the added tests are unverified.
- **Remaining risks:** Existing test coverage may reveal additional login-required views or assumptions after the full suite is run.

### ROUTE-02 — Missing public homepage

- **Files changed:** `backend/config/urls.py`, `backend/passages/views.py`, `backend/passages/templates/passages/base.html`, `backend/passages/templates/passages/home.html`, `backend/passages/tests.py`
- **Original problem:** The root URL had no route and returned 404, although shared navigation linked to `/`.
- **Exact correction:** Added a public `home` view and root URL pattern. Added a landing template extending the existing passages base template, with links to student login, student registration, and institute owner login. Updated shared navigation while retaining the admin link.
- **Reason:** The domain root now has a defined public landing-page implementation consistent with the existing dark visual system.
- **Tests added:** Homepage status/template/content and portal-link assertions.
- **Tests executed:** None; homepage response and template rendering remain unverified.
- **Remaining risks:** Copy/content is intentionally concise and should be reviewed in a browser after tests.

### DEP-03 — Production HTTPS proxy configuration

- **Files changed:** `backend/PRODUCTION_SECURITY.md`; `backend/config/settings.py` comments clarified. No provider environment variables were changed.
- **Original problem:** Production SSL redirect is enabled by default, while `DJANGO_TRUST_X_FORWARDED_PROTO` defaults to false. When TLS terminates at a trusted reverse proxy, Django may see the upstream request as HTTP and redirect repeatedly if the proxy header is not trusted.
- **Exact correction:** The existing conditional mapping to `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` was preserved and documented. The documentation now states that `DJANGO_TRUST_X_FORWARDED_PROTO=true` must be set in the hosting environment only after confirming that the chosen proxy overwrites `X-Forwarded-Proto`.
- **Reason:** Trusting a forwarded header from an unknown or untrusted proxy can create a security weakness. The diagnostic report did not identify a selected hosting provider.
- **Tests executed:** None. No production proxy or HTTPS request was available to validate.
- **Result:** **Not fully closed.** Provider-specific activation is pending provider selection and proxy verification.
- **Remaining risks:** Do not deploy with SSL redirect enabled behind a TLS-terminating proxy until this environment value is configured and verified. Do not enable it for a proxy that passes through client-supplied header values.

### DEP-05 — Separate development dependencies from production dependencies

- **Files changed:** `backend/requirements.txt`, `backend/requirements-dev.txt`, `backend/PRODUCTION_SECURITY.md`, `.github/workflows/django-ci.yml`
- **Original problem:** pytest, pytest-django, Playwright, and related test tooling were installed from production requirements; CI continued installing only production requirements, so its Playwright command would not have the package available after the split.
- **Exact correction:** Moved test/browser packages and their dedicated pinned dependencies into `requirements-dev.txt`, which includes `-r requirements.txt`. Updated CI to install `requirements-dev.txt`, use it as the pip cache dependency file, and run on Python 3.14.
- **Reason:** Production installs remain separate from test tooling, while CI explicitly installs the complete development/test environment. Python 3.14 also aligns the CI interpreter generation with Cloudflare's currently documented Python Workers runtime.
- **Tests executed:** No tests ran. The updated workflow was observed in a GitHub Actions run, but that run was cancelled during PostgreSQL service-container initialization before checkout, dependency installation, or test steps. An earlier run on the pre-correction commit failed; it does not verify the updated workflow.
- **Remaining risks:** A clean local environment must install `requirements-dev.txt`; installing only `requirements.txt` is now intentionally insufficient to run pytest/Playwright.

## 4. Test and verification matrix

| Required check | Status | Evidence |
|---|---|---|
| Python compilation | **NOT RUN** | Python source was not compiled in this environment. |
| Django system check | **NOT RUN** | Django is not installed in the execution environment. |
| URL resolution | **NOT RUN** | Homepage and route regression tests were added, not executed. |
| Anonymous student redirect | **TEST ADDED — NOT RUN** | Tests added in accounts and passages apps. |
| Owner login redirect | **TEST ADDED — NOT RUN** | Owner portal redirect tests added. |
| Admin login redirect | **TEST ADDED — NOT RUN** | Super-admin redirect test added. |
| Homepage response | **TEST ADDED — NOT RUN** | Homepage response/template/link test added. |
| Static file collection | **NOT RUN** | `collectstatic` was not executed. |
| Production settings validation | **NOT RUN** | No production environment variables or hosting runtime available. |
| Existing regression tests | **NOT RUN** | Full existing suite was not executed. |
| GitHub Actions checks | **NOT VERIFIED** | A run using the updated workflow was cancelled during service-container initialization before checkout or test steps. An earlier run on an older commit failed before the CI dependency correction. The latest branch head has no completed successful run. |

No test is reported as passed. No test is reported as failed. The checks above are unexecuted unless explicitly marked “test added — not run”.

## 5. Preservation and scope controls

- All edits were made on `phase-a-launch-blockers`, based on `main`.
- `main` was not changed.
- `backend/config/wsgi.py` was not changed.
- No migration file was added or changed.
- No migration command was run.
- No database connection, reset, drop, truncate, or data update was performed.
- No database provider, authentication architecture, payment gateway, subscription logic, DNS, hosting account, or production environment variable was changed.
- No deployment was performed.
- No Phase B, C, D, or E issue was intentionally modified.

## 6. Remaining blockers before Phase A can be declared complete

1. Audit every runtime dependency for Pyodide/Python Workers compatibility, especially Django, `psycopg`, `psycopg-binary`, `django-redis`, `redis`, Pillow, and ReportLab.
2. Confirm the existing PostgreSQL provider and Redis/cache provider. If PostgreSQL is external, assess Cloudflare Hyperdrive as a connection layer to that same database only; do not create or switch providers without approval. Hyperdrive for Python Workers is documented as beta and requires compatibility date `2026-09-08` or later.
3. Add and test the Cloudflare WSGI Worker entry point and Wrangler configuration only after the dependency and database/cache design is validated.
4. Configure native Worker static assets and verify admin CSS/JS after `collectstatic`.
5. Verify HTTPS scheme handling through the actual WSGI adapter; do not set `DJANGO_TRUST_X_FORWARDED_PROTO=true` without proof that the header is trusted and overwritten.
6. Run `pip install -r requirements-dev.txt`, Python compilation, Django system checks, the complete PostgreSQL test suite, and Worker local tests.
7. Verify anonymous student, owner, staff, and administrator redirects; review any failures and repair only within the six authorized Phase A issues.

## 7. Stop condition

**STOPPED after Phase A implementation work.** No Phase B work has started. Do not merge or deploy this branch until the unexecuted checks are run, DEP-03 is configured for the selected provider, and the resulting report is reviewed.
