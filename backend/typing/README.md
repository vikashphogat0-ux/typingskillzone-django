# Phase F — shared typing session foundation

One learner-owned typing session service for individual learners and institute members.

- Start only against an active published source and active simulator publication.
- Snapshot reference text, timer, input permissions and exam-rule provenance at start.
- Persist an absolute server-side deadline; never trust a browser timer for expiry.
- Submit once with row locking; repeated submissions are rejected.
- Keep attempts private to their learner. Institute assignment and reporting authorization are future explicit domains.
- Never calculate or claim an official qualification result from unverified exam rules.
- Scoring version and result snapshot are reserved for the future versioned scoring engine.
- No payment/seat logic and no mutation of source passages.
- This phase does **not** implement a browser typing interface, event-stream capture, pause, or verified scoring.

Run: `python manage.py test typing`.
