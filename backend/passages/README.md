# Central Passage Studio

## Admin workflow

1. Open Django Admin and choose **Passage sources**.
2. Create one central source passage with its title, complete original text, language and script.
3. Select one or more target exam simulators.
4. Set the source status to **Published** and save.
5. The publishing service creates one simulator publication for each compatible target exam. The source itself remains the single centrally managed original.

You can also select multiple existing source records in the Passage Sources list and use **Publish selected central passages to their selected simulators**.

## Simulator-specific IDs and formatting

- Each exam simulator has its own serial sequence beginning at `01`.
- The same central source published to Delhi Police HCM and BSF HCM can be Passage `01` in both simulators.
- A second source published to Delhi Police HCM receives `02`, while the first source published to BSF HCM remains `01`.
- IDs are stored as numeric serials and displayed with at least two digits. They are not UUIDs, are not renumbered, and are not reused after archive.
- A source cannot be published into a simulator with an incompatible language or conflicting non-empty script.
- Continuous and paragraph/TCS presentation is rendered from the central source at read time. The original source text is not rewritten.
- PostgreSQL production uses a row lock on each exam's sequence counter to serialize concurrent ID allocation. SQLite is for local development only and does not provide the same row-lock guarantee.

## Simulator passage pages

Authenticated users can browse published passages at:

`/simulators/<exam-code>/passages/`

Example: `/simulators/delhi-police-hcm/passages/`

The passage detail page is:

`/simulators/<exam-code>/passages/<passage-id>/`

## Safety

- Archive simulator publications instead of deleting them. Their serial IDs remain reserved.
- The central source is protected from deletion while simulator publications refer to it.
- Publishing the same source to the same simulator again is idempotent: it does not create a duplicate or consume another ID.
- Historical typing attempts and the typing engine are outside this phase.
