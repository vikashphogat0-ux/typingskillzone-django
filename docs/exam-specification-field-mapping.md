# Exam Specification Field Mapping

**Status:** Source-code audit baseline; no schema or runtime changes made  
**Branch:** `feat/master-exam-specification-system`  
**Scope:** Existing Django model, attempt snapshot, and scoring implementation

This document maps the current implementation to the proposed master exam specification. It is a compatibility and risk inventory, not a claim that any profile is officially verified. It does not inspect or modify a live database.

## 1. Existing architecture

- `ExamConfiguration` is the editable exam profile and currently stores identity, timing, passage presentation, input policy, scoring configuration, qualification configuration, and profile-level provenance.
- `start_session()` copies a manually selected subset of the profile into `TypingSession.rules_snapshot`.
- The attempt also stores an immutable copy of the passage in `reference_text`.
- `submit_session()` calculates the result using the attempt snapshot, then persists `scoring_version` and `result_snapshot`.
- This snapshot pattern is the correct compatibility boundary: later profile edits should not rewrite historical attempts.

## 2. Field-to-domain mapping

| Existing field(s) | Canonical domain | Current meaning / consumer | Mapping concern and compatibility rule |
|---|---|---|---|
| `code`, `name` | Exam identity | Stable code and display name | Keep codes stable; do not infer official identity from display-name similarity. |
| `category` | Classification | Broad catalogue grouping | Navigation metadata, not an official exam rule. |
| `language`, `script` | Language and script | Profile language/script; session snapshot | Preserve exact values in historical snapshots. Do not equate language with keyboard layout. |
| `interface_type` | Delivery interface | Interface label | Its meaning is not yet normalized; distinguish platform/interface from passage layout. |
| `duration_seconds` | Timing | Main session duration and deadline | Unit is seconds. Null currently means no configured deadline; do not silently substitute a default. |
| `trial_seconds`, `review_seconds`, `correction_seconds`, `transcription_seconds` | Timing phases | Optional phase durations; copied to snapshot | Define phase order and whether phases are included in total duration before execution logic is added. |
| `passage_format` | Passage presentation | Broad format enum | Not interchangeable with physical layout. Retain as a legacy field until consumers are migrated. |
| `passage_layout` | Passage presentation | Continuous, paragraphs, para/tab, TCS, custom | More specific presentation structure; preserve separately from format. |
| `passage_font_family`, `passage_font_size_pt`, `passage_line_height`, `passage_paragraph_spacing_pt`, `passage_alignment`, `passage_first_line_indent_em`, `passage_preserve_tabs`, `passage_tab_size` | Passage typography | Display/print formatting | Presentation settings are not necessarily official scoring rules. Snapshot currently omits paragraph spacing and first-line indent; add only with explicit compatibility tests. |
| `passage_word_limit` | Passage constraints | Single positive integer | Unit and operator are ambiguous: minimum, maximum, target, or exact word count. Do not interpret until represented explicitly. |
| `passage_source_mode` | Passage delivery/source | Screen, printed, manuscript, continuous, key-depression, transcription | Distinguish source medium from on-screen layout and input method. |
| `allow_backspace`, `backspace_policy` | Input policy | Boolean plus detailed policy; model clean() derives boolean for some policies | Dual representation can conflict when save() bypasses full_clean(). A future resolver must define policy precedence without rewriting old snapshots. |
| `allow_delete`, `allow_paste`, `allow_copy`, `allow_cut`, `allow_arrow_navigation` | Input policy | Editing/navigation controls; copied into attempt snapshot | These are separate capabilities. Do not collapse into a single “editing allowed” flag. |
| `enter_behavior`, `space_behavior`, `tab_behavior` | Input semantics | Newline/commit/disabled/unspecified behavior | Keep distinct; a key may affect word commitment, paragraph formatting, and scoring differently. |
| `keyboard_layout`, `text_encoding` | Input environment | Layout and encoding labels | Not enough to infer physical keystroke count. Unicode text length is not a reliable proxy for physical key depressions, especially for Indic input methods. |
| `minimum_wpm` | Qualification threshold | Numeric minimum speed; scoring branches may consult it | Define whether threshold applies to gross, correct, net, or another speed metric. Current field name does not say which. |
| `required_keystrokes` | Passage/test requirement | Numeric threshold; scorer compares against supplied reported count | Must distinguish passage minimum from candidate-input minimum. A client-reported count is untrusted evidence and cannot prove physical keystrokes. |
| `strokes_per_word` | Speed conversion | Conversion factor in profile | Must document whether this is a fixed official convention or an implementation approximation, and which text/keystroke measure it applies to. |
| `error_allowance_percent` | Error tolerance | Used by percentage/qualifying scoring branch | Define denominator and rounding policy. Current implementation uses gross words as denominator. |
| `mistake_penalty_strokes` | Error penalty | Stored and snapshotted | Current scoring implementation must be checked for actual use; storage alone does not make it executable. |
| `scoring_mode` | Scoring formula selection | Selects a branch in `calculate_result()` | Legacy enum currently mixes metrics, qualification-only behavior, and custom scoring. Preserve as a compatibility adapter while introducing a versioned formula registry. |
| `error_rules` | Error classification/counting | JSON flags/configuration; e.g. word-error counting | No schema/version validation. Define allowed keys and semantics before relying on arbitrary JSON. |
| `scoring_rules` | Score formula parameters | JSON values such as score bands, mistake penalties, disqualification threshold | No schema/version validation; numeric coercion and malformed values need explicit validation and tests. |
| `qualification_rules` | Qualification logic | JSON configuration copied into snapshot | Must remain separate from marks/score calculation. Audit actual consumers before defining schema. |
| `verification_status` | Evidence/provenance | Profile-level UNVERIFIED/PARTIAL/VERIFIED | One status for the entire profile is too coarse when timing, input, presentation, and scoring rules have different evidence quality. Keep legacy status for compatibility; future design should support per-domain evidence. |
| `official_source_url`, `source_title`, `source_checked_at`, `rule_notes` | Rule provenance | Profile-level source and notes | A single URL/date may not support every configured field. Future evidence records should attach source, page/section, checked date, and supported claims per rule domain. |
| `presentation_reference_status`, `presentation_reference_url`, `presentation_reference_title`, `presentation_reference_checked_at`, `presentation_notes` | Presentation provenance | Separate evidence for visual/reference formatting | Correctly separate from official rule verification; retain that separation. |
| `rule_config_version` | Configuration compatibility | Small integer copied to attempt snapshot | This is not the same as canonical specification schema version or scoring engine version. Do not overload it. |
| `is_active`, `display_order` | Catalogue lifecycle | Availability and ordering | Operational catalogue fields, not exam rules. |

## 3. Current scoring-mode compatibility matrix

The following describes the current `calculate_result()` branches, not a recommendation that these formulas are officially correct for any named exam.

| Mode | Current implementation behavior | Compatibility concern |
|---|---|---|
| `GENERIC` | Produces generic character/word metrics and WPM metrics. | Treat as analytics/default practice metrics, not official qualification without a verified formula. |
| `CORRECT_WORDS` | Uses correct-word count as the scoring basis. | Marks/weighting and qualification semantics need explicit tests and documented units. |
| `NET_WPM` | Net speed-oriented branch. | Confirm exact gross/net calculation and penalty source before mapping any official exam. |
| `ERROR_PERCENTAGE` | Calculates error percentage against gross words and permitted count from configured allowance. | Rounding, denominator, and excess-error treatment must be explicit. |
| `QUALIFYING_ONLY` | Shares the error-percentage/threshold branch; qualification is withheld unless profile is verified and thresholds exist. | Qualification should not be conflated with numeric marks. |
| `STROKE_PENALTY` | Dedicated stroke-based penalty branch exists in the enum/engine. | Confirm its exact parameter usage and boundary behavior before use. |
| `CORRECT_WORD_MARKS` | Multiplies correct words by configured marks per word. | Requires validated marks-per-word configuration and score cap semantics. |
| `CUSTOM` | Reads `mistake_penalty_words`, `disqualify_at_mistakes`, and `score_bands` from JSON. | JSON is weakly typed; malformed or incomplete bands can silently produce no score. |
| `FULL_HALF_MISTAKES` | Currently reports that exam-specific full/half mistake categories are required; generic classification is not assumed. | Not yet an executable official formula. |

### Cross-cutting scoring observations

- `SCORING_VERSION` is currently `tsz-char-word-v1`.
- `SequenceMatcher` provides deterministic character and word comparisons, but its alignment is not an official adjudication method by itself.
- The scoring result labels a supplied keystroke count as `client_reported`; this must never be represented as trusted physical-key evidence.
- Qualification is deliberately withheld for unverified profiles in the current implementation. Preserve this safety behavior.
- Historical attempts carry both `rules_snapshot` and `scoring_version`; new implementations must not rescore old attempts implicitly.

## 4. Snapshot coverage gaps

The current `start_session()` snapshot includes most operational rule fields, but the following model fields are not currently copied:
- `category` and `interface_type`
- `passage_word_limit`
- `passage_paragraph_spacing_pt`
- `passage_first_line_indent_em`
- `presentation_reference_status`, URL, title, checked date, and notes
- `source_title`, `source_checked_at`, and `rule_notes`

Some omissions may be intentional. Before adding fields, decide whether they affect runtime, auditability, or historical result explanation. If added, write snapshot-compatibility tests and keep old snapshots readable.

## 5. Canonical model gaps to resolve before schema changes

1. **Passage quantity:** replace ambiguous `passage_word_limit` semantics with explicit constraint type and unit (e.g. minimum words, maximum words, minimum strokes, target words).
2. **Speed basis:** define gross/correct/net speed and the exact numerator/denominator for each formula.
3. **Keystroke evidence:** separate official passage stroke requirements from candidate input telemetry; mark browser-reported counts as untrusted.
4. **Error taxonomy:** separate error categories, detection method, count unit, severity, and penalty mapping.
5. **Qualification:** model pass/fail criteria independently from score/marks.
6. **Input controls:** establish one canonical policy for backspace and other controls; retain legacy boolean fields as compatibility projections until all consumers migrate.
7. **Presentation:** separate layout, source medium, interface, typography, and key behavior.
8. **Evidence:** attach provenance to each independently verifiable rule domain rather than relying solely on one profile-level status.
9. **Versioning:** distinguish specification schema version, profile revision, and scoring engine version.
10. **JSON contracts:** define versioned schemas and validation for error, scoring, and qualification configuration.

## 6. Safe implementation sequence

1. Add compatibility tests for current snapshots and every scoring mode before changing runtime behavior.
2. Introduce a pure specification resolver that reads legacy `ExamConfiguration` fields and emits a canonical in-memory representation. No database migration in this step.
3. Add a snapshot builder that preserves legacy keys while adding explicit schema/engine version metadata.
4. Add formula adapters for existing `scoring_mode` values; initially preserve outputs exactly.
5. Compare old and new outputs over a fixed regression corpus.
6. Only after parity is demonstrated, migrate individual profiles with official source evidence and explicit review.
7. Consider schema migrations only when a proven requirement cannot be represented safely in the resolver.

## 7. Verification limits

This is a source-code audit of the feature branch. It does not establish:
- the contents of the user's local SQLite database or production database;
- whether seeded profiles in a real database have been manually edited;
- whether every current scoring mode is correctly configured for each named exam;
- whether existing source URLs are still accessible or support all configured claims.

A separate read-only database export/audit is required for actual stored-row conflicts. No database command, migration, seed command, or deployment was run for this document.
