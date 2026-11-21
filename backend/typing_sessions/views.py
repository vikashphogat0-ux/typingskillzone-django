import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
import logging
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from exams.models import ExamConfiguration
from passages.models import SimulatorPassage

from django.utils import timezone

from .drafts import load_draft_text
from .models import TypingSession
from .services import activate_session, expire_session, save_draft, start_session, submit_session

DISPLAY_MODES = {"normal", "highlighted", "offscreen"}


logger = logging.getLogger(__name__)


@login_required
@require_POST
def start_typing_session(request, exam_code, passage_id):
    exam = get_object_or_404(ExamConfiguration, code=exam_code, is_active=True)
    try:
        serial_number = int(passage_id)
    except (TypeError, ValueError):
        serial_number = -1
    publication = get_object_or_404(
        SimulatorPassage.objects.select_related("exam", "source"),
        exam=exam,
        serial_number=serial_number,
        status=SimulatorPassage.Status.PUBLISHED,
    )
    try:
        attempt = start_session(learner=request.user, publication=publication)
        # The mode chosen at start is saved. It can still change until typing begins
        # (the server clock starts on the first keystroke); after that it stays fixed.
        requested_mode = (request.POST.get("display_mode") or "").strip().lower()
        current_mode = attempt.rules_snapshot.get("display_mode")
        if requested_mode in DISPLAY_MODES and attempt.deadline_at is None and requested_mode != current_mode:
            attempt.rules_snapshot = {**attempt.rules_snapshot, "display_mode": requested_mode}
            attempt.save(update_fields=("rules_snapshot",))
        elif not current_mode:
            attempt.rules_snapshot = {**attempt.rules_snapshot, "display_mode": "normal"}
            attempt.save(update_fields=("rules_snapshot",))
    except PermissionDenied as error:
        logger.warning(
            "Typing session start denied: user_id=%s role=%s active=%s exam=%s passage=%s reason=%s",
            request.user.pk, request.user.role, request.user.is_active,
            exam.code, passage_id, error,
        )
        return render(request, "typing_sessions/error.html", {"message": str(error), "exam": exam}, status=403)
    except ValidationError as error:
        # The account is authorized; the requested publication is unavailable
        # under its current publication/release state. Do not misreport this as
        # an authentication or role failure.
        logger.info(
            "Typing session unavailable: user_id=%s role=%s exam=%s passage=%s reason=%s",
            request.user.pk, request.user.role, exam.code, passage_id, error,
        )
        return render(request, "typing_sessions/error.html", {"message": str(error), "exam": exam}, status=409)
    return redirect("typing_sessions:session", session_id=attempt.pk)


@login_required
@require_POST
def start_selected_typing_session(request, exam_code):
    """Start the passage selected inside one exam's dedicated workspace."""
    passage_id = request.POST.get("passage_id", "").strip()
    return start_typing_session(request, exam_code, passage_id)


@login_required
def typing_session(request, session_id):
    attempt = get_object_or_404(
        TypingSession.objects.select_related("publication__exam"),
        pk=session_id,
        learner=request.user,
    )
    if attempt.state != TypingSession.State.ACTIVE:
        return render(request, "typing_sessions/result.html", {"attempt": attempt})
    if attempt.has_expired:
        attempt = expire_session(session_id=attempt.pk, learner=request.user)
        return render(request, "typing_sessions/result.html", {"attempt": attempt})
    # Server clock and deadline are sent as epoch milliseconds so the countdown does not
    # depend on the device clock.
    clock = {
        "server_now_ms": int(timezone.now().timestamp() * 1000),
        "deadline_ms": int(attempt.deadline_at.timestamp() * 1000) if attempt.deadline_at else None,
        "duration_ms": int(attempt.duration_seconds * 1000) if attempt.duration_seconds else None,
    }
    return render(request, "typing_sessions/live.html", {
        "attempt": attempt,
        "clock": clock,
        "draft_text": load_draft_text(attempt.pk),
    })


@login_required
@require_POST
def activate_typing_session(request, session_id):
    try:
        attempt = activate_session(session_id=session_id, learner=request.user)
    except TypingSession.DoesNotExist:
        return JsonResponse({"error": "Session not found."}, status=404)
    except (PermissionDenied, ValidationError) as error:
        return JsonResponse({"error": str(error)}, status=403)
    return JsonResponse({
        "server_now_ms": int(timezone.now().timestamp() * 1000),
        "deadline_ms": int(attempt.deadline_at.timestamp() * 1000) if attempt.deadline_at else None,
    })


@login_required
@require_POST
def submit_typing_session(request, session_id):
    typed_text = request.POST.get("typed_text", "")
    raw_keystrokes = request.POST.get("keystroke_count", "")
    try:
        reported_keystrokes = int(raw_keystrokes) if raw_keystrokes else None
    except (TypeError, ValueError):
        reported_keystrokes = None
    try:
        client_policy_events = int(request.POST.get("policy_events", "") or 0)
    except (TypeError, ValueError):
        client_policy_events = None
    try:
        attempt = submit_session(
            session_id=session_id,
            learner=request.user,
            typed_text=typed_text,
            reported_keystrokes=reported_keystrokes,
            client_policy_events=client_policy_events,
        )
    except TypingSession.DoesNotExist:
        return JsonResponse({"error": "Session not found."}, status=404)
    except (PermissionDenied, ValidationError) as error:
        return JsonResponse({"error": str(error)}, status=403)
    return render(request, "typing_sessions/result.html", {"attempt": attempt})


@login_required
@require_POST
def save_typing_draft(request, session_id):
    try:
        save_draft(
            session_id=session_id,
            learner=request.user,
            typed_text=request.POST.get("typed_text", ""),
        )
    except TypingSession.DoesNotExist:
        return JsonResponse({"error": "Session not found."}, status=404)
    except (PermissionDenied, ValidationError) as error:
        return JsonResponse({"error": str(error)}, status=403)
    return JsonResponse({"saved": True})
