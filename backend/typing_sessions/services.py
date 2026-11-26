from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from passages.models import SimulatorPassage, PassageSource

from .drafts import DRAFT_MAX_CHARS, clear_draft, save_draft_text
from .models import TypingSession
from .scoring import SCORING_VERSION, calculate_result
from .specification_snapshots import build_exam_specification_snapshot
from .candidate_selectors import apply_candidate_selections, validate_candidate_selections, validate_candidate_snapshot


def _require_active_student(learner):
    if (
        not learner
        or not learner.is_authenticated
        or not learner.is_active
        or learner.role != "STUDENT"
    ):
        raise PermissionDenied("An active student account is required.")


@transaction.atomic
def start_session(*, learner, publication, candidate_selections=None):
    _require_active_student(learner)
    publication = SimulatorPassage.objects.select_related("exam", "source").get(pk=publication.pk)
    if (publication.status != SimulatorPassage.Status.PUBLISHED
            or publication.source.status != PassageSource.Status.PUBLISHED
            or not publication.exam.is_active):
        raise ValidationError("This passage is not available for a new attempt.")
    if not publication.is_released():
        raise ValidationError("This passage is not released yet.")

    exam = publication.exam
    duration = exam.duration_seconds
    now = timezone.now()
    # Validate all candidate choices before ending an existing attempt. A malformed
    # selector submission must never destroy a valid in-progress attempt.
    validated_selections = validate_candidate_selections(exam, candidate_selections or {})
    # Every valid start is a new test. Unfinished tests for this passage end without scoring.
    abandon_active_attempts(learner=learner, publication=publication)
    snapshot = build_exam_specification_snapshot(
        exam=exam,
        publication=publication,
        captured_at=now,
    )
    snapshot = apply_candidate_selections(snapshot, validated_selections)
    duration = snapshot.get("duration_seconds") or duration
    if duration is None and validated_selections.get("duration_seconds"):
        duration = validated_selections["duration_seconds"]
    reference_text = publication.rendered_content
    if exam.code == "ssc-data-processing-assistant-grade-a":
        import re

        passage_range = (exam.scoring_rules or {}).get("passage_character_range") or {}
        minimum_chars = int(passage_range.get("minimum", 3700))
        maximum_chars = int(passage_range.get("maximum", 4000))
        paragraphs = [part for part in re.split(r"\n\s*\n", reference_text) if part.strip()]
        reference_text = "\n\n".join(
            part if part.startswith("\t") else "\t" + part.lstrip(" \t")
            for part in paragraphs
        )
        if not minimum_chars <= len(reference_text) <= maximum_chars:
            raise ValidationError(
                f"SSC DPA Grade-A passage must contain {minimum_chars}–{maximum_chars} characters including paragraph tabs."
            )

    if exam.code in {"ssc-chsl-2025-vh-category-english", "ssc-chsl-2025-english-test-tcs-interface"}:
        import re
        word_range = (exam.scoring_rules or {}).get("passage_word_range") or {}
        minimum_words = int(word_range.get("minimum", 350))
        maximum_words = int(word_range.get("maximum", 400))
        passage_words = len(re.findall(r"\S+", publication.rendered_content or ""))
        if not minimum_words <= passage_words <= maximum_words:
            raise ValidationError(
                f"{exam.name} passage must contain {minimum_words}–{maximum_words} words."
            )
    return TypingSession.objects.create(
        learner=learner,
        publication=publication,
        started_at=now,
        deadline_at=None,
        duration_seconds=duration,
        reference_text=reference_text,
        rules_snapshot=snapshot,
    )


@transaction.atomic
def activate_session(*, session_id, learner, compensatory_time=False):
    """Start the server-owned exam clock on the learner's first input."""
    _require_active_student(learner)
    session = TypingSession.objects.select_for_update().get(pk=session_id, learner=learner)
    if session.state != TypingSession.State.ACTIVE:
        raise ValidationError("This session has already ended.")
    if not session.rules_snapshot.get("timer_started"):
        now = timezone.now()
        if session.deadline_at is None:
            session.started_at = now
            scoring_rules = session.rules_snapshot.get("scoring_rules") or {}
            selector_snapshot = session.rules_snapshot.get("candidate_selectors") or {}
            selected_duration = session.rules_snapshot.get("selected_variant_duration_seconds")
            if selected_duration:
                session.duration_seconds = int(selected_duration)
            compensatory_seconds = scoring_rules.get("compensatory_duration_seconds")
            if compensatory_time:
                if not scoring_rules.get("compensatory_time_enabled") or not compensatory_seconds:
                    raise ValidationError("Compensatory time is not configured for this examination profile.")
                # The explicit in-exam attestation is used only by profiles whose
                # setup exposes this control (for example, the DPA Grade-A profile).
                # A post-eligibility attestation must never grant extra time.
                session.duration_seconds = int(compensatory_seconds)
                selector_snapshot = {
                    **selector_snapshot,
                    "eligibility_attested": True,
                    "eligibility_status": "CANDIDATE_ATTESTED",
                    "compensatory_time_attested": True,
                }
            if session.duration_seconds:
                session.deadline_at = now + timedelta(seconds=session.duration_seconds)
        scoring_rules = session.rules_snapshot.get("scoring_rules") or {}
        compensatory_seconds = scoring_rules.get("compensatory_duration_seconds")
        session.rules_snapshot = {
            **session.rules_snapshot,
            "candidate_selectors": selector_snapshot,
            "timer_started": True,
            "compensatory_time_applied": bool(
                compensatory_seconds
                and session.duration_seconds == int(compensatory_seconds)
                and session.duration_seconds > int(scoring_rules.get("standard_duration_seconds") or 0)
            ),
        }
        session.save(update_fields=("started_at", "deadline_at", "duration_seconds", "rules_snapshot"))
    return session


@transaction.atomic
def submit_session(*, session_id, learner, typed_text, reported_keystrokes=None, client_policy_events=None):
    _require_active_student(learner)
    session = TypingSession.objects.select_for_update().select_related("publication").get(
        pk=session_id, learner=learner
    )
    if session.state != TypingSession.State.ACTIVE:
        raise ValidationError("This session has already ended.")
    if not isinstance(typed_text, str):
        raise ValidationError("Typed text must be a string.")
    if len(typed_text) > 100000:
        raise ValidationError("Submission exceeds the allowed size.")
    if reported_keystrokes is not None and (
        isinstance(reported_keystrokes, bool)
        or not isinstance(reported_keystrokes, int)
        or reported_keystrokes < 0
        or reported_keystrokes > 1000000
    ):
        raise ValidationError("Keystroke count is outside the allowed range.")

    now = timezone.now()
    if not session.rules_snapshot.get("timer_started"):
        if session.deadline_at is None:
            session.started_at = now
            if session.duration_seconds:
                session.deadline_at = now + timedelta(seconds=session.duration_seconds)
        session.rules_snapshot = {**session.rules_snapshot, "timer_started": True}
        session.save(update_fields=("started_at", "deadline_at", "rules_snapshot"))
    expired = bool(session.deadline_at and now >= session.deadline_at)
    if (
        (session.rules_snapshot.get("scoring_rules") or {}).get("formula") == "SSC_DPA_GRADE_A"
        and not expired
    ):
        raise ValidationError("SSC DPA Grade-A submissions are accepted only when the evaluated test timer expires.")
    effective_end = min(now, session.deadline_at) if session.deadline_at else now
    elapsed = max(1, int((effective_end - session.started_at).total_seconds()))
    if session.duration_seconds:
        elapsed = min(elapsed, session.duration_seconds)

    # An expired attempt is scored only from text received by this endpoint; the
    # browser's countdown or claimed completion time is never accepted.
    scoring_snapshot = dict(session.rules_snapshot)
    # Candidate selections are read only from the persisted start-time snapshot.
    # Submission POST fields cannot replace category, standard, post or eligibility.
    validate_candidate_snapshot(scoring_snapshot)
    result = calculate_result(
        reference=session.reference_text,
        typed=typed_text,
        duration_seconds=elapsed,
        rules=scoring_snapshot,
        reported_keystrokes=reported_keystrokes,
    )
    result["candidate_selections"] = dict(scoring_snapshot.get("candidate_selectors") or {})
    if scoring_snapshot.get("resolved_candidate_configuration"):
        result["resolved_candidate_configuration"] = dict(
            scoring_snapshot["resolved_candidate_configuration"]
        )
    # Clipboard and backspace blocks are counted in the browser only. Keep the count as
    # clearly labelled, unverified telemetry; it never changes the score.
    if client_policy_events is not None:
        result["client_policy_events_unverified"] = max(0, min(1000, int(client_policy_events)))
    session.state = TypingSession.State.EXPIRED if expired else TypingSession.State.SUBMITTED
    session.submitted_text = typed_text
    session.completed_at = now
    session.scoring_version = SCORING_VERSION
    session.result_snapshot = result
    session.save(update_fields=(
        "state", "submitted_text", "completed_at", "scoring_version", "result_snapshot"
    ))
    clear_draft(session.pk)
    return session


@transaction.atomic
def save_draft(*, session_id, learner, typed_text):
    """Store an autosave draft for an active attempt. Drafts are never scored."""
    _require_active_student(learner)
    session = TypingSession.objects.get(pk=session_id, learner=learner)
    if session.state != TypingSession.State.ACTIVE:
        raise ValidationError("This session has already ended.")
    if session.has_expired:
        raise ValidationError("The timer has expired.")
    if not isinstance(typed_text, str) or len(typed_text) > DRAFT_MAX_CHARS:
        raise ValidationError("Draft is missing or exceeds the allowed size.")
    now = timezone.now()
    timeout = 3600
    if session.deadline_at:
        timeout = max(60, int((session.deadline_at - now).total_seconds()) + 300)
    save_draft_text(session.pk, typed_text, timeout)
    return session


@transaction.atomic
def expire_session(*, session_id, learner):
    _require_active_student(learner)
    session = TypingSession.objects.select_for_update().get(pk=session_id, learner=learner)
    if session.state != TypingSession.State.ACTIVE:
        return session
    if not session.deadline_at or timezone.now() < session.deadline_at:
        raise ValidationError("The timer has not expired.")
    session.state = TypingSession.State.EXPIRED
    session.completed_at = timezone.now()
    session.save(update_fields=("state", "completed_at"))
    return session


@transaction.atomic
def abandon_active_attempts(*, learner, publication=None):
    """End unfinished tests without scoring them (used when a new test starts or the page is refreshed)."""
    queryset = TypingSession.objects.select_for_update().filter(learner=learner, state=TypingSession.State.ACTIVE)
    if publication is not None:
        queryset = queryset.filter(publication=publication)
    now = timezone.now()
    ended = 0
    for attempt in queryset:
        attempt.state = TypingSession.State.EXPIRED
        attempt.completed_at = now
        attempt.result_snapshot = {}
        attempt.scoring_version = ""
        attempt.save(update_fields=("state", "completed_at", "result_snapshot", "scoring_version"))
        ended += 1
    return ended

