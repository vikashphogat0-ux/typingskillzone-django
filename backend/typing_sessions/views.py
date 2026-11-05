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
from .result_integrity import verify_result_integrity


def _result_context(attempt):
    integrity = verify_result_integrity(
        rules_snapshot=attempt.rules_snapshot,
        result_snapshot=attempt.result_snapshot,
    ) if attempt.result_snapshot else None
    return {
        "attempt": attempt,
        "result_integrity": integrity,
        "domain_evidence": attempt.rules_snapshot.get("domain_evidence_snapshot", {}),
    }


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
        return render(request, "typing_sessions/result.html", _result_context(attempt))
    if attempt.has_expired:
        attempt = expire_session(session_id=attempt.pk, learner=request.user)
        return render(request, "typing_sessions/result.html", _result_context(attempt))
    return render(request, "typing_sessions/live.html", {"attempt": attempt})


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
        attempt = submit_session(
            session_id=session_id,
            learner=request.user,
            typed_text=typed_text,
            reported_keystrokes=reported_keystrokes,
        )
    except TypingSession.DoesNotExist:
        return JsonResponse({"error": "Session not found."}, status=404)
    except (PermissionDenied, ValidationError) as error:
        return JsonResponse({"error": str(error)}, status=403)
    return render(request, "typing_sessions/result.html", _result_context(attempt))



@login_required
def delhi_police_hcm_dashboard(request):
    """Learner-owned HCM practice history; reads immutable result snapshots only."""
    attempts = list(
        TypingSession.objects.filter(
            learner=request.user,
            result_snapshot__dphcm_attempt_report__profile="DELHI_POLICE_HCM_2025",
        ).order_by("-completed_at", "-started_at")[:100]
    )
    rows = []
    speeds = []
    accuracies = []
    category_totals = {}
    unresolved_total = 0
    for attempt in attempts:
        report = attempt.result_snapshot.get("dphcm_attempt_report") or {}
        metrics = report.get("practice_metrics") or {}
        analysis = report.get("mistake_analysis") or {}
        speed = metrics.get("net_wpm")
        accuracy = metrics.get("accuracy_percent")
        if isinstance(speed, (int, float)):
            speeds.append(float(speed))
        if isinstance(accuracy, (int, float)):
            accuracies.append(float(accuracy))
        for item in analysis.get("candidate_errors") or []:
            category = item.get("category", "UNSPECIFIED")
            category_totals[category] = category_totals.get(category, 0) + 1
        unresolved = len(analysis.get("unresolved_cases") or [])
        unresolved_total += unresolved
        rows.append({
            "attempt": attempt,
            "speed": speed,
            "accuracy": accuracy,
            "candidate_count": analysis.get("candidate_error_count"),
            "unresolved_count": unresolved,
            "marks_status": (report.get("marks_eligibility") or {}).get("status", "PENDING"),
        })
    return render(request, "typing_sessions/dphcm_dashboard.html", {
        "rows": rows,
        "attempt_count": len(rows),
        "average_net_wpm": round(sum(speeds) / len(speeds), 2) if speeds else None,
        "average_accuracy": round(sum(accuracies) / len(accuracies), 2) if accuracies else None,
        "category_totals": sorted(category_totals.items(), key=lambda item: (-item[1], item[0])),
        "unresolved_total": unresolved_total,
    })
