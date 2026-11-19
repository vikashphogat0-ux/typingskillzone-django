import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from exams.models import ExamConfiguration
from passages.models import SimulatorPassage

from django.utils import timezone

from .drafts import load_draft_text
from .models import TypingSession
from .services import expire_session, save_draft, start_session, submit_session


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
    except (PermissionDenied, ValidationError) as error:
        return render(request, "typing_sessions/error.html", {"message": str(error)}, status=403)
    return redirect("typing_sessions:session", session_id=attempt.pk)


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
    }
    return render(request, "typing_sessions/live.html", {
        "attempt": attempt,
        "clock": clock,
        "draft_text": load_draft_text(attempt.pk),
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
