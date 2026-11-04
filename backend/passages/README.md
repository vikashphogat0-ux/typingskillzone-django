# Central Passage Studio

## Admin workflow

1. Open Django Admin and choose **Passage sources**.
2. Create one central source passage with its title, complete original text, language and script.
3. Select one or more target exam simulators.
4. Set the source status to **Published** and save.
5. The publishing service creates one simulator publication for each compatible target exam. The source itself remains the single centrally managed original.

## Simulator-specific IDs and formatting

- Each exam simulator has its own serial sequence beginning at `01`; IDs are immutable and not reused after archive.
- One source can be published to multiple simulators, receiving a separate local ID in each.
- Each simulator uses its own `ExamConfiguration` presentation profile: layout, font, size, line height, paragraph spacing, alignment, indentation and tab behavior.
- Layouts include pending, continuous, paragraphs, paragraph-and-tab, TCS-style and custom.
- The renderer does not mutate the central source. Unconfigured profiles preserve the original text and show a pending-verification notice rather than guessing.
- The RKC Nawada library is recorded as a practice reference only. A reference-reviewed profile is not labelled officially verified. The current seeded DP HCM profile uses the explicit “Para & Tab Matter” label; other catalogue entries remain pending unless an admin has reviewed sufficient format evidence.
- Reseeding the exam catalogue does not overwrite manually configured profiles for other exams.
- A source cannot be published into a simulator with an incompatible language or conflicting non-empty script.
- PostgreSQL production uses a row lock on each exam's sequence counter. SQLite is for local development and does not provide the same row-lock guarantee.

## Simulator pages

- List: `/simulators/<exam-code>/passages/`
- Detail: `/simulators/<exam-code>/passages/<passage-id>/`

## Safety

- Archive publications instead of deleting them. IDs remain reserved.
- A source cannot be deleted while simulator publications refer to it.
- Republishing the same source to the same simulator is idempotent.
- Historical typing attempts and the typing engine remain outside this phase.
