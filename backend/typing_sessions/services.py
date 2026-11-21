from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from passages.models import SimulatorPassage, PassageSource

from .drafts import DRAFT_MAX_CHARS, clear_draft, save_draft_text
from .models import TypingSession
from .scoring import SCORING_VERSION, calculate_result
from .specification_snapshots import build_exam_specification_snapshot


def _require_active_student(learner):
    if (
        not learner
        or not learner.is_authenticated
        or not learner.is_active
        or learner.role != "STUDENT"
    ):
        raise PermissionDenied("An active student account is required.")


@transaction.atomic
def start_session(*, learner, publication):
    _require_active_student(learner)
    publication = SimulatorPassage.objects.select_related("exam", "source").get(pk=publication.pk)
    if (publication.status != SimulatorPassage.Status.PUBLISHED
            or publication.source.status != PassageSource.Status.PUBLISHED
            or not publication.exam.is_active):
        raise ValidationError("This passage is not available for a new attempt.")
    if not publication.is_released():
        raise ValidationError("This passage is not released yet.")

    # One live attempt per learner and passage: reopen it instead of creating a second.
    existing = (
        TypingSession.objects.select_for_update()
        .filter(learner=learner, publication=publication, state=TypingSession.State.ACTIVE)
        .order_by("-started_at")
        .first()
    )
    if existing is not None and not existing.has_expired:
        return existing

    exam = publication.exam
    duration = exam.duration_seconds
    now = timezone.now()
    snapshot = build_exam_specification_snapshot(
        exam=exam,
        publication=publication,
        captured_at=now,
    )
    return TypingSession.objects.create(
        learner=learner,
        publication=publication,
        started_at=now,
        deadline_at=None,
        duration_seconds=duration,
        reference_text=publication.rendered_content,
        rules_snapshot=snapshot,
    )


@transaction.atomic
def activate_session(*, session_id, learner):
    """Start the server-owned exam clock on the learner's first input."""
    _require_active_student(learner)
    session = TypingSession.objects.select_for_update().get(pk=session_id, learner=learner)
    if session.state != TypingSession.State.ACTIVE:
        raise ValidationError("This session has already ended.")
    if not session.rules_snapshot.get("timer_started"):
        now = timezone.now()
        session.started_at = now
        if session.duration_seconds and session.deadline_at is None:
            session.deadline_at = now + timedelta(seconds=session.duration_seconds)
        session.rules_snapshot = {**session.rules_snapshot, "timer_started": True}
        session.save(update_fields=("started_at", "deadline_at", "rules_snapshot"))
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
        session.started_at = now
        if session.duration_seconds:
            session.deadline_at = now + timedelta(seconds=session.duration_seconds)
        session.rules_snapshot = {**session.rules_snapshot, "timer_started": True}
        session.save(update_fields=("started_at", "deadline_at", "rules_snapshot"))
    expired = bool(session.deadline_at and now >= session.deadline_at)
    effective_end = min(now, session.deadline_at) if session.deadline_at else now
    elapsed = max(1, int((effective_end - session.started_at).total_seconds()))
    if session.duration_seconds:
        elapsed = min(elapsed, session.duration_seconds)

    # An expired attempt is scored only from text received by this endpoint; the
    # browser's countdown or claimed completion time is never accepted.
    result = calculate_result(
        reference=session.reference_text,
        typed=typed_text,
        duration_seconds=elapsed,
        rules=session.rules_snapshot,
        reported_keystrokes=reported_keystrokes,
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
