# Master Exam Specification System

## Objective

Make one versioned, auditable specification the source of truth for every typing exam profile. The simulator, passage renderer, keyboard controls, mistake classifier, scoring engine, result screen, and admin panel must consume the same resolved specification. Avoid separate hard-coded exam rules in views, templates, seed commands, and scoring branches.

## Non-negotiable safeguards

- Preserve the existing Django architecture, authentication, institute/student/admin features, payment integrations, and current database.
- Do not reset, drop, truncate, or replace any database.
- Do not run bulk seed operations that overwrite admin-edited profiles.
- Do not deploy as part of this work.
- Do not mark a rule VERIFIED unless its authoritative source, exact clause/page, and review date are recorded.
- Keep unknown values explicit as UNKNOWN / NOT_SPECIFIED; never infer a restriction from a practice website.
- Separate official examination requirements from TypingSkillZone practice presentation choices.
- Preserve legacy profile behavior until a profile has a reviewed migration mapping and regression coverage.

## Specification domains

Each profile must resolve these domains:

1. Identity: exam, recruitment authority, post, notification/year, stage, language, script, keyboard layout.
2. Test pattern: duration, sections, trial/review/correction time, qualifying or merit status, minimum speed, marks.
3. Passage: source mode (screen/printed/manuscript), minimum/target length and its unit (words/strokes/characters), paragraph structure, tabs, line breaks, continuation/repeat rules.
4. Input policy: Backspace, Delete, arrows, paste, copy, cut, Space, Enter, Tab. Each value must distinguish allowed, prohibited, not specified, and practice-only default.
5. Error taxonomy: omission, substitution, insertion/addition, transposition, capitalization, punctuation, spacing, paragraph, and any source-defined full/half mistake classes.
6. Scoring: raw input metric, strokes-per-word convention, gross/tentative/net speed, error unit, penalty, allowance, marks bands, rounding policy, disqualification and qualification conditions.
7. Provenance: official source URL/title, notification identifier, page/clause, publication date, checked date, verification status, reviewer notes.
8. Practice presentation: passage layout, typography, simulator-specific UI behavior. This is not evidence of official exam rules.

## Architecture target

- A versioned Exam Specification Registry resolves the active specification for a profile and language.
- Passage rendering reads only passage fields from the resolved specification.
- Typing input policy reads only keyboard/input fields from the same specification.
- Mistake analysis produces a structured, explainable category report.
- Scoring consumes the resolved formula and its declared units; no exam-specific hidden conditionals scattered across endpoints.
- Qualification is separate from a practice score and is only claimed for verified rules.
- Results persist the immutable specification snapshot and scoring-engine version used for that attempt.
- Admin edits are validated, versioned, and auditable; historical attempt snapshots never change.

## Rollout sequence

### Phase 1 — Inventory and source audit
- Enumerate every active and inactive exam profile and language variant.
- Group profiles by the exact recruitment notification and post; do not merge profiles merely because their names look similar.
- Identify duplicate, incomplete, conflicting, and legacy fields.
- Collect authoritative notices/rulebooks and record page/clause references.
- Mark each domain independently as VERIFIED, PARTIAL, or UNVERIFIED.

### Phase 2 — Canonical schema and compatibility
- Define a versioned specification schema and validation rules.
- Map existing ExamConfiguration fields and JSON settings into the canonical schema.
- Preserve existing values and historical snapshots.
- Add compatibility tests before switching runtime consumers.

### Phase 3 — Shared engines
- Refactor passage rendering, input policy, mistake classification, scoring, and qualification to consume the same resolved specification.
- Keep existing formulas available through explicit legacy adapters until migrated and tested.
- Define exact rounding, word/stroke counting, Unicode/Hindi handling, and incomplete-attempt behavior.

### Phase 4 — Admin and audit controls
- Provide grouped exam-profile editing and source provenance.
- Show unresolved/contradictory fields clearly.
- Require source details before VERIFIED status.
- Record who changed a rule, when, old/new values, and why.

### Phase 5 — Validation and controlled rollout
- Add boundary tests for every formula and score band.
- Add English/Hindi, punctuation, spacing, paragraph, backspace, timeout, and passage-format tests.
- Run existing regression suite and migration checks.
- Review the full profile matrix before enabling the new resolver.
- Use a staged, reversible rollout; do not deploy until explicitly approved.

## Canonical scoring registry (implementation stage)

`backend/exams/scoring_registry.py` now resolves a versioned scoring descriptor for
each attempt. It identifies a formula, records the parameters available in the
captured profile, and reports missing or ambiguous inputs without inventing values.
The scoring engine stores this descriptor with the result and displays unresolved
requirements on the result page.

Registered formula identifiers currently cover generic practice metrics, correct
words per minute, stroke-adjusted net speed, word-error allowance, stroke penalty,
exact full/half word classification, marks per correct word, qualifying-only, and
custom formulas. Generic metrics are explicitly practice-only. Unknown modes are
unsupported by the registry.

The registry is currently a compatibility/readiness layer around the existing
scoring engine, not a complete replacement of its legacy formula branches. A
qualification result is withheld when the registry says required parameters are
incomplete or required scoring/qualification domain evidence is not verified.
Existing score metrics remain available as practice analysis. Profiles that use
legacy settings must be reviewed and explicitly mapped before they can claim
official qualification.

The registry does not yet define every official rounding convention, Hindi/Unicode
stroke counting algorithm, or all exam-specific error taxonomies. Those remain
source-audit and formula-implementation work, not assumed defaults.

## Delhi Police HCM 2025 reference case

The official SSC notice states a 10-minute typing test, minimum 30 WPM English / 25 WPM Hindi, and minimum printed passage size of 400 English words / 350 Hindi words (also expressed as 2,000 / 1,750 strokes). The notice describes tentative speed from strokes divided by five and time, then subtracts one word for each mistake. It provides language-specific marks bands. The passage-size stroke count is not a candidate input minimum. The notice does not specify a Backspace restriction; the practice simulator must not present a restriction as official.

Source: https://ssc.gov.in/api/attachment/uploads/masterData/NoticeBoards/Notice_of_DPHCM_2025.pdf?mode=light

This case remains subject to implementation-level validation of fractional-speed band boundaries and the precise official mistake-classification instructions. Do not infer a rounding rule that the notice does not state.

## Completion criteria

- Every catalogue profile has a documented source/verification state for every applicable rule domain.
- Every runtime subsystem consumes one resolved specification snapshot.
- No duplicate hard-coded scoring/passage/input rules remain outside the registry and explicit compatibility adapters.
- All legacy and new tests pass; every verified formula has threshold and edge-case tests.
- Existing users, subscriptions, institute workflows, results, and production data remain intact.
- A pull request documents migration impact, compatibility behavior, test evidence, and unresolved rules.
