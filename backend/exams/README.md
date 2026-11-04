# Central exam configuration

The `ExamConfiguration` model is the single source of truth for simulator identity and exam-specific rules. Super Admins manage entries in Django Admin. The initial catalogue is seeded by `python manage.py seed_exam_catalogue`.

**Rule safety:** catalogue names and inferred language/script/interface labels are organizational metadata, not official rule verification. All entries start UNVERIFIED with duration and scoring/qualification rules unset. Do not mark a configuration VERIFIED until an authoritative notification/specification is recorded in the source fields and the duration and rule values have been checked. A verified record requires an official source URL, source title, checked date, and duration.

Rules are stored as structured JSON so future scoring-engine versions can add explicit, versioned fields without conflating exam identity and rule values. Consumers must reject or clearly label unverified configurations rather than silently applying generic official rules.
