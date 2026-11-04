# TypingSkillZone — Product and application architecture

## Product definition

TypingSkillZone is one typing-learning and examination-preparation platform serving two audiences:

1. **Direct-to-learner (B2C):** an individual registers independently, learns typing, practises at home, takes exam simulations, tracks progress and optionally buys an individual plan.
2. **Institute (B2B2C):** an institute registers and is approved, an owner manages the institute, staff teach/manage learners, and students access institute-assigned learning under the institute's subscription and policies.

The institute portal is not the whole product. Public visitors and independent learners are first-class users from the initial release.

## Non-negotiable architecture rules

- One shared user identity and authentication system. A person may be an independent learner and also have one or more institute memberships. Do not make a learner's identity or personal practice history belong to an institute.
- Separate account identity, role/permissions, learning access, and billing. A role must not be used as a subscription or account-type flag.
- One shared exam catalogue, passage library, typing engine, scoring engine and result format for both audiences.
- Individual subscriptions and institute subscriptions are separate billing relationships and entitlement sources. Never apply institute seat limits to an individual learner or an individual plan to an institute.
- Institute data is tenant-scoped. Owners and staff may access only institutes for which they have explicit membership/permissions. Personal learner records remain private to the learner unless explicitly shared or assigned.
- A student can access personal learning and institute-provided learning using the same login. The UI should let them choose the relevant learning context without creating duplicate accounts.
- Exam rules are data-driven and versioned. Do not hardcode exam-specific behavior into templates or generic views.
- Unverified exam rules must never be presented as official or used for a qualifying-result claim.
- Payment provider references and webhook processing must be isolated behind billing services. Do not couple exam execution to a payment provider.
- Preserve existing data. All future schema changes must be additive and reversible where practical; never reset, drop or truncate a database.

## Product surfaces and navigation

### Public website
- Home, product overview, how it works, exam catalogue, typing-learning curriculum, pricing, institute solution, help/FAQ, contact, sign in and registration.
- Separate calls to action: **Start learning as an individual** and **Register an institute**.
- Public exam catalogue can be browsed without authentication; starting a saved test requires an account.

### Individual learner workspace
- Personal dashboard and onboarding/skill assessment.
- Structured typing lessons: keyboard/finger placement, accuracy, speed-building and language/script-specific practice.
- Free practice, timed drills, exam simulators and passage library access according to entitlements.
- Personal progress, WPM/accuracy trends, mistakes, test history, bookmarks and goals.
- Individual plan, invoices/payment history, profile and privacy controls.

### Institute workspace
- Institute owner dashboard, institute profile, staff and student management.
- Staff workspace, class/cohort management, assignments and learner monitoring.
- Student workspace with personal progress plus institute-assigned work.
- Institute subscription, seat limits, reports and administrative controls.

### Platform administration
- Super Admin dashboard, user and institute governance, exam configuration, passage management, content moderation, subscriptions, payments, audit trail and operational settings.

## Django application boundaries

| App / domain | Responsibility |
|---|---|
| `accounts` | Shared identity, authentication, verification, security and account recovery |
| `learners` | Learner profile, goals, onboarding and individual learning preferences |
| `institutes` | Institute tenant, owner/staff/student memberships, institute subscription and seats |
| `exams` | Central exam catalogue, rule versions, source provenance and verification |
| `passages` (planned) | Passage content, language/script variants, IDs, assignment and publication |
| `typing` (planned) | Typing session lifecycle, input capture, timer and keyboard behavior |
| `scoring` (planned) | Versioned scoring algorithms, error classification, WPM and qualification |
| `learning` (planned) | Lessons, drills, curriculum, personal goals and learning progress |
| `assignments` (planned) | Institute classes, teacher assignments, due dates and submissions |
| `results` (planned) | Immutable attempt/result snapshots, history, analytics and exports |
| `billing` (planned) | Individual plans, institute plans, entitlements, payment records and provider adapters |
| `notifications` (planned) | Email/in-app notifications and delivery history |
| `audit` (planned) | Append-only security and administrative activity log |

Do not create one copy of the typing engine for individual users and another for institutes. Both contexts must call the same application services and persist results using the same domain model.

## Identity, roles and learning context

- A user is an identity, not a customer segment.
- Platform roles: Super Admin and platform support/admin roles.
- Institute permissions are granted by institute membership and tenant-scoped policy checks.
- Individual learners do not need an institute membership.
- A learner who joins an institute retains the same account, personal history and preferences.
- Institute assignments and institute-visible reports are separate records/permissions; do not expose all personal history to an institute by default.
- Avoid a single mutually exclusive `account_type` field such as PERSONAL versus INSTITUTE: it prevents one user from using both journeys.

## Entitlements and billing

- Individual entitlement is derived from the learner's individual subscription and any explicit promotional grants.
- Institute entitlement is derived from the institute subscription, seat availability, membership status and institute policy.
- A learner may have both sources of access. Access checks must identify the source/context and apply the relevant policy.
- Plans define features/limits as structured entitlements, not scattered if-statements.
- Payment callbacks must be idempotent; store provider transaction references and verify signatures before changing entitlements.
- Do not store payment secrets in the database or logs.

## Shared exam and typing domain

Each exam configuration must identify:
- exam, recruitment cycle/year and variant;
- language, keyboard layout and font/script;
- interface and passage presentation;
- duration and passage constraints;
- backspace/navigation behavior;
- error classification and penalty rules;
- scoring formula and qualification thresholds;
- official source, source date, effective period and verification status.

Use immutable/versioned rule sets for attempts. Every attempt must retain the exact rule version used, so later admin edits cannot silently rewrite historical results. A simulator may run a practice mode with provisional settings, but must clearly distinguish it from an officially verified qualifying simulation.

## Results and privacy

- Store each attempt as a durable result snapshot, including exam/rule version, passage version, duration, raw input-derived metrics, score breakdown and completion status.
- The learner owns their personal history.
- Institute dashboards query only members and assignments within that institute.
- Staff access is limited by their institute role and assigned responsibilities.
- Do not expose raw keystroke streams to institutes unless a documented feature requires it and the learner is informed.

## Suggested URL namespaces

- Public: `/`, `/exams/`, `/learn/`, `/pricing/`, `/for-institutes/`
- Auth: `/accounts/`
- Individual: `/app/`, `/app/learn/`, `/app/practice/`, `/app/results/`, `/app/billing/`
- Institute: `/institute/<slug>/` with owner, staff and student areas
- Platform admin: Django Admin and protected operational dashboards

The final URL design can evolve, but public, individual, institute and platform-admin navigation must remain clearly separated.

## Delivery order

1. Foundation: shared identity/permissions, product architecture, central exam catalogue and configuration versioning.
2. Shared learning engine: passages, typing sessions, scoring and immutable results.
3. Individual learner journey: public onboarding, lessons, practice, dashboard and individual billing.
4. Institute journey: cohorts, assignments, staff workflows, monitoring and institute reporting.
5. Platform operations: audit, analytics, support tools and operational hardening.

Build the shared engine before either portal is allowed to fork its own behavior. Deliver individual and institute journeys as separate experiences over the same services.

## Current implementation status

The current Django repository has shared accounts and institute management, the central exam catalogue, and the initial learner profile domain. The `passages`, `typing`, `scoring`, `learning`, `assignments`, `results`, `billing`, `notifications` and `audit` domains remain planned work, not claims that those applications are already implemented.
