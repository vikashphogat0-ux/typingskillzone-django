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

## Delhi Police HCM 2025 source-grounded reference profile

backend/exams/reference_profiles/delhi_police_hcm_2025.py records the SSC 2025 notice rules from paragraph 24.1 and 24.2 (printed pages 22-23). The profile is a reference/evaluation module only; it does not modify any existing ExamConfiguration row or automatically certify a live profile.

Confirmed by the notice:
- Typing test duration: 10 minutes.
- Minimum qualifying speed: English 30 WPM; Hindi 25 WPM.
- Printed passage minimum: English 400 words or 2,000 strokes; Hindi 350 words or 1,750 strokes.
- Tentative speed: total strokes divided by five and then by test time in minutes.
- Actual speed: tentative speed minus one word per mistake.
- Mistake descriptions: omission, substitution, added punctuation, wrong capitalization, gap within a word, excess gap between words, and failure to make paragraph(s).
- Marks bands: English 30=10, 31-35=12, 36-40=15, 41-45=18, 46-50=21, above 50=25; Hindi 25=10, 26-30=12, 31-35=15, 36-40=18, 41-45=21, above 45=25.
- Backspace, Delete, paste, copy, cut and arrow-navigation restrictions are not specified in these typing-test paragraphs.

Implementation safeguards:
- The evaluator accepts an integer stroke count and a mistake count; it never guesses strokes by counting Unicode characters in submitted text.
- It only evaluates the specified 600-second test.
- It does not round fractional actual speeds. Because the notice's bands leave fractional values between integer ranges unstated, such outcomes return BAND_UNRESOLVED rather than an invented mark.
- Hindi stroke counting remains blocked until a source-backed, tested Unicode stroke counter is available.
- The current general simulator's client-reported keystrokes are not trusted input and must not be substituted for a verified stroke count.
- This reference module is not wired to production exam records and does not claim every profile is verified.

Source: SSC, Notice: Head Constable (Ministerial) in Delhi Police Examination, 2025, paragraphs 24.1-24.2, printed pages 22-23:
https://ssc.gov.in/api/attachment/uploads/masterData/Notice_of_DPHCM_2025.pdf?mode=light

## Stroke-event counting contract

`backend/typing_sessions/stroke_counting.py` adds a versioned event-based counter (`tsz-key-event-v1`) for English and Hindi practice. It counts explicit physical KEY_DOWN events, excludes modifier-only and auto-repeat events, and marks IME composition commits unresolved because the committed Unicode text does not reveal the physical key sequence.

Critical limitations:
- This is unverified client telemetry, not a trusted server-side event attestation. Its output always has official_scoring_eligible=false.
- The SSC notice specifies a stroke-based formula but does not define a browser event-capture protocol, keyboard-layout mapping, or trusted event-integrity mechanism. This counter's event convention is an engineering telemetry contract, not an official SSC definition.
- The counter is deliberately not connected to official score calculation or live attempt submission. It does not infer strokes from final English or Hindi text.
- Hindi IME composition, missing physical events, or incomplete event streams remain unresolved rather than being converted into a guessed count.
- A future production integration requires a reviewed client capture implementation, layout-specific verification, tamper-resistance assessment, and separate evidence before any official scoring eligibility can be considered.

## Delhi Police HCM 2025 mistake-analysis prototype

`backend/typing_sessions/dphcm_error_analysis.py` implements a conservative text-difference analyzer for the mistake descriptions in SSC Notice 2025 paragraph 24.2: omission, substitution, added punctuation, capitalization, internal word gaps, excess inter-word gaps, and missing paragraphs.

The analyzer deliberately distinguishes candidate categories from an official mistake count. It reports multi-token replacements, added words, and uncertain whitespace/paragraph changes as unresolved where the notice does not give a complete deterministic adjudication algorithm. `official_mistake_count` remains null and `official_scoring_eligible` remains false. The module is not wired into the general scoring engine or the Delhi Police marks evaluator.

Tests are added for the listed candidate categories, unresolved additions, exact text and invalid input. These tests have not yet been executed in CI or locally.

## Delhi Police HCM unified attempt report

`backend/typing_sessions/dphcm_attempt_report.py` composes practice speed/accuracy metrics, conservative mistake-analysis candidates, unresolved text cases, and marks eligibility into a versioned report. `submit_session` attaches this report only to exam codes beginning `delhi-police-hcm-2025`; other exam attempts retain their existing result structure. The result template displays the report and its limitations.

The report deliberately labels speed metrics PRACTICE_ONLY and keeps marks pending until both a verified physical stroke count and an officially adjudicated mistake count are available. It does not call the HCM marks evaluator, change the general score, or rewrite prior attempts. Tests cover HCM report attachment and non-HCM isolation; execution remains pending.

## Delhi Police HCM learner practice dashboard

The authenticated route `typing_sessions:dphcm_dashboard` at `reports/delhi-police-hcm/` reads only the current learner's saved attempts carrying a Delhi Police HCM attempt report. It summarizes attempt count, average practice net WPM, average accuracy, candidate mistake-category frequencies, unresolved text cases, and a reverse-chronological attempt history with links to each immutable report. The view caps history at the latest 100 attempts and performs aggregation in application code; it does not write to attempts or recalculate scores.

Official marks remain explicitly pending. These dashboard aggregates are practice indicators, not official selection or qualification predictions. A learner-isolation test was added; tests and CI have not been run in this environment.

## Delhi Police HCM practice performance trends

The learner dashboard now renders saved attempt trends in chronological order (oldest to newest). Each attempt shows its captured completion/start timestamp, passage identifier, practice net WPM, and accuracy. Speed bars are normalized against the highest displayed practice speed; accuracy bars use a 0–100 scale. The view supplies presentation-only widths and does not alter score snapshots, infer official marks, or mix unverified candidate mistake categories into the trend metrics. History remains limited to the latest 100 learner-owned HCM reports.

A test covers chronological ordering and bar scaling. Automated execution and CI remain pending.

## Delhi Police HCM dashboard filters

The learner dashboard accepts optional `start_date`, `end_date`, and `language` GET filters. Dates use ISO calendar dates from native date inputs; language is selected from the captured attempt language (English or Hindi). Filtering occurs against the learner-owned attempt queryset before the latest-100 cap, so a selected language/date window is not accidentally limited by unrelated recent attempts. A reversed or malformed filter is surfaced to the learner and does not silently apply a partial date range. Clearing filters returns the unfiltered dashboard.

Summary metrics, category totals, and trend series are recomputed from the filtered set of immutable result snapshots. No historical attempt is changed. Tests cover language isolation and reversed date ranges; test execution and CI remain pending.


## Delhi Police HCM personal practice goals

Each learner can save one personal goal for the Delhi Police HCM profile. The default targets are 30 net practice WPM and 95% practice accuracy; learners can set net WPM from 1–200 and accuracy from 1–100%. The dashboard displays progress against the average practice metrics in the currently selected date/language filter.

These goals are learner preferences only. They are not official SSC qualifying standards, do not determine eligibility or marks, and are not copied into attempt snapshots. The new `LearnerPracticeGoal` table is separate from historical attempt records. Migration `0002_learnerpracticegoal` creates this table without altering existing attempts.


## Delhi Police HCM seven-day practice report

The learner dashboard now shows a rolling seven-calendar-day summary (today and the preceding six local dates), including daily attempt count, average saved practice net WPM, average saved accuracy, and whether each daily average meets the learner's personal goals. A seven-day aggregate is shown above the daily rows. It uses the same learner-owned, date/language-filtered, latest-100 attempt set as the dashboard. Days without attempts remain visible with zero attempts and no metric value.

This is descriptive practice reporting only. It does not recalculate attempts, change historical snapshots, or determine official SSC marks or qualification. Tests cover a recent attempt and the empty seven-day state; execution remains pending.

## Completion criteria

- Every catalogue profile has a documented source/verification state for every applicable rule domain.
- Every runtime subsystem consumes one resolved specification snapshot.
- No duplicate hard-coded scoring/passage/input rules remain outside the registry and explicit compatibility adapters.
- All legacy and new tests pass; every verified formula has threshold and edge-case tests.
- Existing users, subscriptions, institute workflows, results, and production data remain intact.
- A pull request documents migration impact, compatibility behavior, test evidence, and unresolved rules.


## Delhi Police HCM monthly practice report

The learner dashboard groups the currently displayed learner-owned HCM attempt reports by local calendar month. Each month shows attempt count, average saved practice net WPM, average saved accuracy, and whether those monthly averages meet the learner's personal goals. It uses the same active date/language filters and latest-100 matching-attempt cap as the dashboard; months without attempts are omitted. The report is descriptive practice analysis, not an official SSC marks or qualification statement. The dashboard Print / Save as PDF action uses the browser print dialog; the learner can choose Save as PDF without adding a server-side PDF dependency.


## Delhi Police HCM 30/60/90-day progress analysis

The dashboard compares saved practice metrics in each recent 30-, 60-, and 90-calendar-day window against the immediately preceding window of equal length. It reports attempt counts, average practice net WPM, average accuracy, absolute changes (WPM and percentage points), and current-period personal-goal status. The comparison uses the learner-owned, active date/language-filtered queryset and all matching saved attempts in the 180-day comparison horizon; the separate attempt-history display remains capped at 100. A change is shown only when both periods have a metric value; missing data is not treated as zero. This is descriptive practice analysis, not an official SSC result or prediction.
