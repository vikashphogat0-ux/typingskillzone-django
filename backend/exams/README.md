# Central exam configuration

The `ExamConfiguration` model is the single source of truth for simulator identity, exam rules and its independent passage-presentation profile. Super Admins manage entries in Django Admin. The initial catalogue is seeded by `python manage.py seed_exam_catalogue`.

## Passage presentation profile

Every catalogue entry has its own configurable presentation profile:
- layout: pending, continuous, paragraphs, paragraph-and-tab, TCS-style or custom;
- font family and point size;
- line height, paragraph spacing, alignment and first-line indentation;
- tab preservation and tab width;
- reference URL/title/date, reference status and notes.

The profile is read independently by each simulator. A central passage source is never rewritten by rendering. A layout left as **Pending format verification** preserves the original text rather than applying a guessed transformation.

The RKC Nawada passage library is used as a practical typing-practice reference where it explicitly identifies the exam and format. For example, its Delhi Police HCM materials are labelled “Para & Tab Matter”. This supports configuring a DP HCM paragraph/tab practice layout, but does not make RKC an official recruitment authority. RKC-only evidence is recorded as **Reference reviewed (practice source)**, not official verification. See https://www.rkcnawada.online/viewrkcpassage.php.

A catalogue entry without sufficiently specific presentation evidence remains pending. A reference being listed for an exam is not, by itself, evidence of its font, spacing, alignment or tab-stop measurements. Those values must be confirmed from a suitable sample/interface before being configured.

## Rule verification is separate

Catalogue names and inferred language/script/interface labels are organizational metadata, not official rule verification. All entries start UNVERIFIED with duration and scoring/qualification rules unset. Do not mark a configuration VERIFIED until an authoritative notification/specification is recorded in the official source fields and the duration and rule values have been checked.

Presentation-reference status and official exam-rule verification are deliberately separate fields. A practice website can support a presentation reference review; it cannot establish official recruitment rules.

Rules are stored as structured JSON so future scoring-engine versions can add explicit, versioned fields without conflating exam identity and rule values. Consumers must reject or clearly label unverified configurations rather than silently applying generic official rules.
