from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from passages.models import SimulatorPassage, PassageSource

from .models import TypingSession
from .scoring import SCORING_VERSION, calculate_result
from .specification_snapshots import build_exam_specification_snapshot


@transaction.atomic
def start_session(*, learner, publication):
    if not learner or not learner.is_authenticated or not learner.is_active:
        raise PermissionDenied("An active account is required.")
    publication = SimulatorPassage.objects.select_related("exam", "source").get(pk=publication.pk)
    if (publication.status != SimulatorPassage.Status.PUBLISHED
            or publication.source.status != PassageSource.Status.PUBLISHED
            or not publication.exam.is_active):
        raise ValidationError("This passage is not available for a new attempt.")

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
        deadline_at=now + timedelta(seconds=duration) if duration else None,
        duration_seconds=duration,
        reference_text=publication.rendered_content,
        rules_snapshot=snapshot,
    )


@transaction.atomic
def submit_session(*, session_id, learner, typed_text, reported_keystrokes=None):
    if not learner or not learner.is_authenticated or not learner.is_active:
        raise PermissionDenied("An active account is required.")
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
    session.state = TypingSession.State.EXPIRED if expired else TypingSession.State.SUBMITTED
    session.submitted_text = typed_text
    session.completed_at = now
    session.scoring_version = SCORING_VERSION
    session.result_snapshot = result
    session.save(update_fields=(
        "state", "submitted_text", "completed_at", "scoring_version", "result_snapshot"
    ))
    return session


@transaction.atomic
def expire_session(*, session_id, learner):
    if not learner or not learner.is_authenticated or not learner.is_active:
        raise PermissionDenied("An active account is required.")
    session = TypingSession.objects.select_for_update().get(pk=session_id, learner=learner)
    if session.state != TypingSession.State.ACTIVE:
        return session
    if not session.deadline_at or timezone.now() < session.deadline_at:
        raise ValidationError("The timer has not expired.")
    session.state = TypingSession.State.EXPIRED
    session.completed_at = timezone.now()
    session.save(update_fields=("state", "completed_at"))
    return session
