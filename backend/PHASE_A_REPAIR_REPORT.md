# Phase A Repair Report — Typing Skill Zone Project B

**Date:** 2026-11-18  
**Branch:** `phase-a-launch-blockers`  
**Base branch:** `main`  
**Overall status:** **PARTIALLY IMPLEMENTED — NOT VERIFIED; DO NOT DEPLOY**  
**Scope:** DEP-01, DEP-02, ROUTE-01, ROUTE-02, DEP-03, DEP-05 only

## 1. Executive summary

Phase A changes have been committed to the isolated `phase-a-launch-blockers` branch. The `main` branch has not been modified. No database operation, migration, provider change, DNS change, deployment, authentication architecture change, or payment/subscription change was performed.

Five issue areas have code/documentation changes prepared: production server dependency, WhiteNoise static serving, portal-specific login redirects, the public homepage, and dependency separation. DEP-03 remains **environment-dependent and not fully closed** because the hosting provider has not been selected. The application already supports `DJANGO_TRUST_X_FORWARDED_PROTO`; this branch documents the safe activation rule but deliberately does not enable trust for an unknown proxy.

**No automated tests were executed in this environment.** Django is not installed in the available execution environment, outbound network access is unavailable, and the repository has no GitHub Actions workflow runs or status checks to execute remotely. Regression tests were added, but they must not be described as passing until run.

## 2. Change inventory

| File | Change |
|---|---|
| `backend/requirements.txt` | Added pinned Gunicorn and WhiteNoise. Removed test/browser tooling from production dependencies. |
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
| `backend/PRODUCTION_SECURITY.md` | Documented Gunicorn command, collectstatic build step, dev dependency installation, and trusted-proxy requirements. |

**Not modified:** `backend/config/wsgi.py`. The existing `config.wsgi:application` entry point is preserved.

## 3. Issue-by-issue implementation

### DEP-01 — Missing production application server dependency

- **File changed:** `backend/requirements.txt`
- **Original problem:** Gunicorn was absent, so a Gunicorn production start command could fail with command-not-found.
- **Exact correction:** Added pinned `gunicorn==23.0.0`.
- **Reason:** Makes the selected WSGI application server an explicit production dependency.
- **Tests executed:** None. Dependency installation and Gunicorn startup were not executed.
- **Result:** Change committed; installation/runtime compatibility remains unverified.
- **Remaining risks:** The actual hosting provider and its expected port/start command are not yet selected. The documented command uses the provider's `PORT` environment variable.

### DEP-02 — Static files not served in production

- **Files changed:** `backend/requirements.txt`, `backend/config/settings.py`, `backend/PRODUCTION_SECURITY.md`
- **Original problem:** With DEBUG disabled, Django does not serve static files itself; the admin interface could lose its CSS and JavaScript.
- **Exact correction:** Added pinned `whitenoise==6.11.0`; inserted `whitenoise.middleware.WhiteNoiseMiddleware` immediately after Django SecurityMiddleware; configured `CompressedManifestStaticFilesStorage`; set `STATIC_URL = "/static/"`; documented `python manage.py collectstatic --noinput` as a build/release step.
- **Reason:** WhiteNoise can serve the collected, compressed, content-hashed static assets through the existing WSGI deployment.
- **Tests executed:** None. WhiteNoise installation, Django system checks, static collection, and an HTTP request for an admin static asset were not executed.
- **Result:** Configuration and regression tests added; runtime behaviour is not yet verified.
- **Remaining risks:** Manifest collection can expose missing static references during collectstatic; that must be checked in the actual environment.

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

- **Files changed:** `backend/requirements.txt`, `backend/requirements-dev.txt`, `backend/PRODUCTION_SECURITY.md`
- **Original problem:** pytest, pytest-django, Playwright, and related test tooling were installed from production requirements.
- **Exact correction:** Moved test/browser packages and their dedicated pinned dependencies into `requirements-dev.txt`, which includes `-r requirements.txt`. Production requirements retain application/runtime dependencies and add Gunicorn/WhiteNoise.
- **Reason:** Production installations remain smaller and do not install test/browser tooling; local development can install the complete environment with `pip install -r requirements-dev.txt`.
- **Tests executed:** None. Fresh production and development dependency installations were not performed.
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
| GitHub Actions checks | **NO RUNS FOUND** | The branch commit has no associated workflow runs or status checks. |

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

1. Select the hosting provider so the reverse-proxy behaviour can be verified and DEP-03 can be configured safely.
2. Run `pip install -r requirements-dev.txt` in a clean development environment.
3. Run Python compilation and the complete Django test suite.
4. Run `python manage.py check` and production settings checks using safe test environment variables.
5. Run `python manage.py collectstatic --noinput` and verify the generated admin static assets.
6. Verify anonymous student, owner, staff, and administrator redirects with Django's test client and browser checks.
7. Review any failures and repair only within the six authorized Phase A issues.

## 7. Stop condition

**STOPPED after Phase A implementation work.** No Phase B work has started. Do not merge or deploy this branch until the unexecuted checks are run, DEP-03 is configured for the selected provider, and the resulting report is reviewed.
