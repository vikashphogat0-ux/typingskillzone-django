# Domain-level provenance contract

**Status:** Validation contract integrated into immutable attempt snapshots and historical result display. No database schema or migration change.

The legacy `ExamConfiguration.verification_status` remains authoritative for existing
compatibility behavior. It must not be copied into individual domain statuses: one
profile-level status cannot prove that every rule domain has independent evidence.

## Domains

- identity
- timing
- passage
- input_policy
- scoring
- qualification
- presentation

Each domain has a status (`UNVERIFIED`, `PARTIAL`, or `VERIFIED`) and a list of
references. Every reference records an HTTPS URL, source title, exact page/section/
clause locator, ISO checked date, and explicit claim paths supported by that source.

## Validation rules

- Missing domains normalize to `UNVERIFIED` with no references.
- `PARTIAL` requires at least one reference.
- `VERIFIED` requires at least one complete reference.
- A reference without an exact locator or explicit supported claims is invalid.
- HTTP URLs, invalid dates, unknown domains, and malformed payloads are rejected.
- This contract validates metadata completeness; it does not independently prove
  that a cited source is official or that its claims are interpreted correctly.
  Human review of the cited source remains mandatory.

## Compatibility and rollout

The contract remains a pure validator with no schema or migration change. At session start,
`build_exam_specification_snapshot` normalizes the evidence and captures its validation
status, domain statuses, references, claims, and capture timestamp. The same immutable
evidence object is stored at `domain_evidence_snapshot` and under
`canonical_specification.provenance.domain_evidence`. Invalid legacy/database payloads
are retained as an `INVALID` capture with validation errors rather than being silently
promoted or causing an attempt to claim verification. Missing domains remain
`UNVERIFIED`. The historical result page displays the captured evidence and explicitly
warns that metadata completeness does not prove source authority or interpretation.

This integration does not add an admin editing workflow, publication gate, automatic
status promotion, database field, or migration. Existing historical attempts are not
rewritten; they simply have no domain evidence snapshot if they predate this change.
