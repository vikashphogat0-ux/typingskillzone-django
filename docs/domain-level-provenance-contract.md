# Domain-level provenance contract

**Status:** Pure validation contract; no database or runtime behavior changed.

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

This is a pure Python contract. It adds no model field, migration, seed behavior,
admin behavior, publication gate, or automatic status promotion. Existing profiles
and historical session snapshots remain unchanged. Persistence and admin workflows
must be designed separately after this contract is reviewed and tested.
