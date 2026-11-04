from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from passages.models import SimulatorPassage, PassageSource

from .models import TypingSession


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
    if not learner or not learner.is_authenticated:
        raise PermissionDenied("Authentication required.")
    session = TypingSession.objects.select_for_update().get(pk=session_id, learner=learner)
    if session.state != TypingSession.State.ACTIVE:
        raise ValidationError("This session has already ended.")
    if not isinstance(typed_text, str):
        raise ValidationError("Typed text must be a string.")
    if len(typed_text) > 100000:
        raise ValidationError("Submission exceeds the allowed size.")
    now = timezone.now()
    session.state = TypingSession.State.EXPIRED if session.deadline_at and now >= session.deadline_at else TypingSession.State.SUBMITTED
    session.submitted_text = typed_text
    session.completed_at = now
    session.save(update_fields=("state", "submitted_text", "completed_at"))
    return session


@transaction.atomic
def expire_session(*, session_id, learner):
    session = TypingSession.objects.select_for_update().get(pk=session_id, learner=learner)
    if session.state != TypingSession.State.ACTIVE:
        return session
    if not session.deadline_at or timezone.now() < session.deadline_at:
        raise ValidationError("The timer has not expired.")
    session.state = TypingSession.State.EXPIRED
    session.completed_at = timezone.now()
    session.save(update_fields=("state", "completed_at"))
    return session
