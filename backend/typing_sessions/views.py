import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from exams.models import ExamConfiguration
from passages.models import SimulatorPassage

from .models import TypingSession
from .services import expire_session, start_session, submit_session


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
    return render(request, "typing_sessions/live.html", {"attempt": attempt})


@login_required
@require_POST
def submit_typing_session(request, session_id):
    typed_text = request.POST.get("typed_text", "")
    try:
        attempt = submit_session(
            session_id=session_id,
            learner=request.user,
            typed_text=typed_text,
        )
    except TypingSession.DoesNotExist:
        return JsonResponse({"error": "Session not found."}, status=404)
    except (PermissionDenied, ValidationError) as error:
        return JsonResponse({"error": str(error)}, status=403)
    return render(request, "typing_sessions/result.html", {"attempt": attempt})
