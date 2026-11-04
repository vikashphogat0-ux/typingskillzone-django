from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from passages.models import SimulatorPassage, PassageSource

from .models import TypingSession
from .scoring import SCORING_VERSION, calculate_result


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
    snapshot = {
        "exam_code": exam.code,
        "exam_name": exam.name,
        "passage_id": publication.passage_id,
        "language": exam.language,
        "script": exam.script,
        "allow_backspace": exam.allow_backspace,
        "allow_arrow_navigation": exam.allow_arrow_navigation,
        "verification_status": exam.verification_status,
        "official_source_url": exam.official_source_url,
        "error_rules": exam.error_rules,
        "scoring_rules": exam.scoring_rules,
        "qualification_rules": exam.qualification_rules,
        "passage_layout": exam.passage_layout,
        "passage_format": exam.passage_format,
        "passage_font_family": exam.passage_font_family,
        "passage_font_size_pt": exam.passage_font_size_pt,
        "passage_line_height": str(exam.passage_line_height),
        "passage_alignment": exam.passage_alignment,
        "passage_preserve_tabs": exam.passage_preserve_tabs,
        "passage_tab_size": exam.passage_tab_size,
    }
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
def submit_session(*, session_id, learner, typed_text):
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
