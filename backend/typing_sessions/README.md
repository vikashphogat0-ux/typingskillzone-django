# Shared typing-test engine

The app provides one learner-owned typing engine for individual learners and institute members. Institute visibility is not inferred; authorized assignment/reporting access must be implemented explicitly.

## Current capabilities
- Start an attempt from a published simulator passage; snapshot passage text and exam input/presentation rules.
- Server-side absolute deadline; refresh does not reset the deadline.
- Live browser interface with countdown, estimated live WPM/accuracy, keyboard restrictions, and automatic submission at timeout.
- Server-side character alignment, substitutions, insertions, deletions, word error count, accuracy, gross WPM, correct WPM and configurable net-WPM penalty.
- Persist one immutable result snapshot and scoring version; duplicate submissions are rejected under a row lock.
- Qualification is deliberately not inferred. Unverified rules never produce an official pass/fail claim.

## Important limitations requiring rule verification
- The browser countdown and live metrics are convenience displays; the server deadline and server score are authoritative.
- Backspace, arrow, Enter and Tab restrictions are client-side input controls and must be tested against each exam's verified interface requirements. A hostile client can bypass browser controls; the server can validate final text and deadline but cannot reconstruct physical keystrokes from a plain textarea submission.
- Pause/resume is not enabled by this implementation. Do not assume it is permitted by an exam.
- Word-level error mode and WPM penalty are activated only through explicit `error_rules` configuration.
- The scoring algorithm is a versioned general practice metric, not a claim that it matches every exam's official marking scheme.
- The live page currently uses a textarea-based input surface; exam-specific rich Enter/Tab navigation and event-stream integrity need a further implementation phase.

## Run tests
`python manage.py test typing_sessions`
