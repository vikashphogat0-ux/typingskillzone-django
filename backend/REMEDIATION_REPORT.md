# Remediation Report — diagnostic findings (branch `fix/diagnostic-remediation`)

Base: `origin/integration/release-review-2026-11` (88d04b6).

## Verification status — read this first
- **Executed here:** a standard-library harness (`/tmp/verify_remediation.py`, copied to outputs) passed **22/22** checks for client-IP handling, marks cap/minimum, whole-word error counting, Hindi NFC normalization, and capitalization detection. It stubs Django's settings and cache only.
- **Executed here:** `node --check` on the inline JavaScript of `live.html` passed. Template tag balance was checked for `live.html` and `passage_library.html`. A static undefined-name check passed on all 20 changed Python files.
- **NOT executed:** the Django system check, migrations check, the full test suite, the PostgreSQL concurrency test, and the browser tests. Django is not installed in the environment that produced this change. The new Django tests (`accounts/test_client_ip.py`, `config/test_routes.py`, `typing_sessions/test_remediation.py`) are written but unrun. CI must run them before any merge.

## Status of each diagnosed issue

| ID | Severity | Status | What changed | Residual risk / decision needed |
|---|---|---|---|---|
| DEP-01 | P0 | Fixed | `gunicorn==23.0.0` added to `requirements.txt`. | Gunicorn is for a conventional server. Confirm the target runtime before deploying. |
| DEP-02 | P0 | Fixed | `whitenoise==6.9.0` added; middleware inserted after `SecurityMiddleware`; `STATIC_ROOT` already set. | Not verified on the Cloudflare Python Workers runtime. |
| DEP-03 | P0 | Fixed | `DJANGO_TRUST_X_FORWARDED_PROTO` now defaults to **true** in production (was false, which caused the redirect loop). | Trusting `X-Forwarded-Proto` is safe only when the origin is reachable through the proxy only. |
| SEC-RL-01 | P1 | Fixed | `accounts/security.py` reads a client-IP header only when `DJANGO_RATE_LIMIT_CLIENT_IP_HEADER` names it; X-Forwarded-For uses the entry `DJANGO_RATE_LIMIT_TRUSTED_PROXY_HOPS` from the right; missing or malformed values fall into one shared bucket (fail closed). Production **raises at startup** if the header is unset. | Deployments must set the variable. Behaviour on the Worker runtime is not verified. |
| ROUTE-01 | P1 | Fixed | Global `LOGIN_URL` is now the student login. Owner, staff, and super-admin views pass their own `login_url`. New `member_login_required` decorator sends staff and students to their own portal. Existing browser test updated (it asserted the bug). | Verify owner and staff redirects in the browser (not executed). |
| ROUTE-02 | P1 | Fixed | `/` route added (`config/views.py`, `passages/templates/passages/home.html`) linking to each portal. | Content is a neutral landing page; confirm wording with the product owner. |
| SCORE-01 | P1 | Fixed in seed | Supreme Court JCA and BSF Hindi Mangal Inscript set `count_word_errors: true`. | **Existing database rows are not changed by the seed.** Run `reconcile_word_error_rules` (dry run first, then `--apply`) after approval. Confirm the official rule per exam. |
| SCORE-02 | P1 | Fixed in seed | AIIMS CRE English and Hindi set `count_word_errors: true`. | Same as SCORE-01 — existing rows need reconciliation. |
| EXAM-01 | P1 | Partially fixed | Copy is blocked on the reference text when the exam disallows it. The browser reports blocked actions as `client_policy_events_unverified`, stored in the result. The count never changes the score. | **Server-side enforcement of backspace, paste, and copy is not possible from final text alone.** Real enforcement needs server-recorded keystroke events — a design decision, not implemented. |
| SESS-01 | P1 | Fixed | Autosave every 15 seconds to `typing_sessions:draft`, stored in cache with expiry tied to the deadline. Drafts restore on reload and are cleared on submit. Drafts are never scored. | Drafts depend on the shared cache. If it is unavailable, drafts are simply not restored. |
| SCORE-03 | P2 | Documentation fixed | Completion document corrected (see `PROJECT_COMPLETION_STATUS.md`). | The `STROKE_NET_WPM` spec is still not seeded. Decide which Delhi Police specification is intended. |
| SCORE-04 | P2 | Fixed | `CORRECT_WORD_MARKS` caps at `maximum_marks` and qualifies at `minimum_marks` when verified and no explicit qualification rules exist. | Verify the official cap and minimum for RSMSSB before relying on them. |
| SCORE-05 | P2 | Fixed | Hindi text compared in NFC; capitalization counted even when punctuation also differs. Dead helper removed. | The classifier's rules are still not verified against official rules. Practice-only. |
| SCORE-06 | P2 | **Not implemented** | — | `trial_seconds` and `allow_passage_repeat` are stored but not enforced. Implementing trial mode and passage repeat is a product definition. Model help text was not changed because it would require a migration. |
| SESS-02 | P2 | Fixed | Countdown uses server time sent as epoch milliseconds plus an offset measured at page load. | Network latency at page load is not corrected. |
| SESS-03 | P2 | Fixed | Starting a passage reopens the learner's existing unexpired ACTIVE attempt instead of creating a second. | Expired ACTIVE attempts are not closed automatically. |
| DATA-01 | P2 | **Not changed — approval required** | — | Migration `accounts/0003` auto-verifies existing owners. Editing an applied migration is unsafe. Review the current owner list before any decision. |
| DATA-02 | P2 | **Not changed — approval required** | — | Migration `institutes/0004` grants trials to existing approved institutes. Confirm the intended dates before any change. |
| INST-01 | P2 | **Not implemented — product decision** | — | Owners can still add a registered account without consent. A consent or invitation model is a product and legal decision. |
| INST-02 | P2 | Partially fixed | Super-admin action "Rotate registration codes" revokes shared codes. | Codes still work as bearer credentials until rotated. Owner-approved enrolment is still a product decision. |
| INST-03 | P2 | Fixed | Approve and reactivate messages report the real subscription state; no longer claim a trial started. | Reactivating an institute whose trial has expired still does not renew the subscription; the message says so. |
| PERF-01 | P2 | Partially fixed | Dashboard streams only the `result_snapshot` JSON, not model instances. | Still loads every scored result. Full fix needs stored aggregates — a schema change. |
| PERF-02 | P2 | Fixed | Passage library paginates (20 per page) with previous and next links. | — |
| PERF-03 | P2 | **Not fixed** | — | Email is sent inside the request. Moving it off-request needs a task queue, which is infrastructure not present in this codebase. |
| DEP-04 | P2 | **Not verified** | CI remains on Python 3.15. | The hosting runtime's Python version must be confirmed before deployment. |
| DEP-05 | P3 | Fixed | Test and development packages moved to `requirements-dev.txt`; CI installs it. | `reportlab` and `Pillow` are installed but not imported anywhere; left in place pending a decision. |
| DOC-01 | P3 | Fixed | Completion document updated (Django 6.1.3, missing audit reference noted). | — |
| DEAD-01 | P3 | **Not changed** | — | The `ADMIN` role may exist in stored data; removing the choice would break those rows. |
| DEAD-02 | P3 | Fixed | Unused `_is_word_char` removed. | — |
| CODE-01 | P3 | Fixed | Module-level logging; stray comment removed. | — |
| CODE-02 | P3 | Partially fixed | Unused prefetch removed. | Per-institute count queries remain. |
| CODE-03 | P3 | Fixed | `timezone.timedelta` replaced with `datetime.timedelta`. | — |
| ERR-01 | P3 | Fixed | Date filter at 9999-12-31 no longer overflows. | — |
| ERR-02 | P3 | Fixed | Duplicate-email race returns a form error instead of a 500 (student and institute registration). | — |
| ERR-03 | P3 | Fixed | Malformed disqualification threshold disables the rule instead of crashing submission. | — |
| SEC-02 | P3 | Partially fixed | Content-Security-Policy header added (`config/middleware.py`). | `'unsafe-inline'` remains for scripts and styles; removing it needs the inline code moved to static files. |
| SEC-03 | P3 | **Not changed — decision** | — | Registration reveals whether an email exists. This is a usability trade-off that needs a conscious decision. |
| ADMIN-01 | P3 | Fixed | Institute `status` is read-only in Django admin; changes go through the review actions. | — |
| PERF-05 | P3 | **Not changed** | — | Learner profile is created on dashboard view. Harmless; left as is. |
| DUP-01 | P3 | **Not changed — product decision** | — | Two student dashboards exist. Consolidating them changes what students see. |
| UX-01 | P3 | **Not changed** | — | Live accuracy remains a positional estimate, labelled as an estimate. |
| DOC-02 | P3 | Fixed | Completion document no longer presents earlier test counts as current. | Test results here are unverified. |

## Counts (computed from the table above)
- **Fixed in code or configuration:** 26. SCORE-01 and SCORE-02 are fixed in the seed only; existing exam rows still need `reconcile_word_error_rules` (dry run, then `--apply`).
- **Partially fixed:** 5 (EXAM-01, PERF-01, CODE-02, SEC-02, INST-02).
- **Not implemented, not changed, not fixed, or not verified:** 11. Each needs a product decision, an approval, or infrastructure not in this codebase.
- **Total issues:** 42.

## Protected items — not changed
- No migrations were added or edited. No database was touched. Neon is unchanged.
- No payment code was added or modified (none exists in this codebase).
- No production configuration, secret, DNS, or deployment was changed.
- `main` was not modified. Nothing was pushed or merged.

## Required before merge
1. CI must pass: `manage.py check`, `makemigrations --check`, the full suite on PostgreSQL, and the browser tests.
2. Review the 13 decision or approval items above; those are not solved by this change.
3. After approval, run `python manage.py reconcile_word_error_rules` (dry run) and review the list before `--apply`.
