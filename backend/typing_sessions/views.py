import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils.dateparse import parse_date

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
    """Learner-owned HCM practice history with optional date/language filters."""
    start_raw = request.GET.get("start_date", "").strip()
    end_raw = request.GET.get("end_date", "").strip()
    language = request.GET.get("language", "").strip().upper()
    start_date = parse_date(start_raw) if start_raw else None
    end_date = parse_date(end_raw) if end_raw else None
    filter_error = ""
    if start_raw and start_date is None:
        filter_error = "Start date is invalid. Use the date picker."
    elif end_raw and end_date is None:
        filter_error = "End date is invalid. Use the date picker."
    elif start_date and end_date and start_date > end_date:
        filter_error = "Start date must be on or before the end date."
    if language not in {"", "ENGLISH", "HINDI"}:
        filter_error = "Choose English or Hindi for the language filter."
        language = ""

    queryset = TypingSession.objects.filter(
        learner=request.user,
        result_snapshot__dphcm_attempt_report__profile="DELHI_POLICE_HCM_2025",
    )
    if not filter_error:
        if start_date:
            queryset = queryset.filter(completed_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(completed_at__date__lte=end_date)
        if language:
            queryset = queryset.filter(result_snapshot__dphcm_attempt_report__language=language)
    attempts = list(queryset.order_by("-completed_at", "-started_at")[:100])

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

    max_speed = max(speeds, default=0)
    trend_rows = []
    for row in reversed(rows):
        speed = row["speed"]
        accuracy = row["accuracy"]
        trend_rows.append({
            "date": row["attempt"].completed_at or row["attempt"].started_at,
            "passage_id": row["attempt"].rules_snapshot.get("passage_id"),
            "speed": speed,
            "speed_width": min(100, round(float(speed) * 100 / max_speed, 1)) if isinstance(speed, (int, float)) and max_speed else 0,
            "accuracy": accuracy,
            "accuracy_width": min(100, max(0, round(float(accuracy), 1))) if isinstance(accuracy, (int, float)) else 0,
        })
    return render(request, "typing_sessions/dphcm_dashboard.html", {
        "rows": rows,
        "trend_rows": trend_rows,
        "attempt_count": len(rows),
        "average_net_wpm": round(sum(speeds) / len(speeds), 2) if speeds else None,
        "average_accuracy": round(sum(accuracies) / len(accuracies), 2) if accuracies else None,
        "category_totals": sorted(category_totals.items(), key=lambda item: (-item[1], item[0])),
        "unresolved_total": unresolved_total,
        "start_date": start_raw,
        "end_date": end_raw,
        "selected_language": language,
        "filter_error": filter_error,
    })
