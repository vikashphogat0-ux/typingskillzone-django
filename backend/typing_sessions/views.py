import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.utils.dateparse import parse_date

from exams.models import ExamConfiguration
from passages.models import SimulatorPassage

from .models import LearnerPracticeGoal, TypingSession
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
    """Learner-owned HCM history, filters, and personal practice targets."""
    goal, _ = LearnerPracticeGoal.objects.get_or_create(learner=request.user)
    goal_error = ""
    if request.method == "POST":
        try:
            target_wpm = int(request.POST.get("target_net_wpm", ""))
            target_accuracy = int(request.POST.get("target_accuracy", ""))
            if not 1 <= target_wpm <= 200 or not 1 <= target_accuracy <= 100:
                raise ValueError
            goal.target_net_wpm = target_wpm
            goal.target_accuracy = target_accuracy
            goal.save(update_fields=("target_net_wpm", "target_accuracy", "updated_at"))
            return redirect("typing_sessions:dphcm_dashboard")
        except (TypeError, ValueError):
            goal_error = "Enter speed from 1–200 WPM and accuracy from 1–100%."
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

    # Seven-day practice summary is presentation-only and uses saved report metrics.
    today = timezone.localdate()
    daily = {}
    for offset in range(7):
        day = today - timedelta(days=6 - offset)
        daily[day] = {"date": day, "attempt_count": 0, "speeds": [], "accuracies": []}
    for row in rows:
        stamp = row["attempt"].completed_at or row["attempt"].started_at
        day = timezone.localtime(stamp).date()
        if day not in daily:
            continue
        bucket = daily[day]
        bucket["attempt_count"] += 1
        if isinstance(row["speed"], (int, float)):
            bucket["speeds"].append(float(row["speed"]))
        if isinstance(row["accuracy"], (int, float)):
            bucket["accuracies"].append(float(row["accuracy"]))
    weekly_daily_rows = []
    for bucket in daily.values():
        day_speeds = bucket["speeds"]
        day_accuracies = bucket["accuracies"]
        avg_speed = round(sum(day_speeds) / len(day_speeds), 2) if day_speeds else None
        avg_accuracy = round(sum(day_accuracies) / len(day_accuracies), 2) if day_accuracies else None
        weekly_daily_rows.append({
            "date": bucket["date"],
            "attempt_count": bucket["attempt_count"],
            "average_net_wpm": avg_speed,
            "average_accuracy": avg_accuracy,
            "speed_goal_met": bool(avg_speed is not None and avg_speed >= goal.target_net_wpm),
            "accuracy_goal_met": bool(avg_accuracy is not None and avg_accuracy >= goal.target_accuracy),
        })
    week_attempts = sum(item["attempt_count"] for item in weekly_daily_rows)
    week_speed_values = [value for item in daily.values() for value in item["speeds"]]
    week_accuracy_values = [value for item in daily.values() for value in item["accuracies"]]
    weekly_summary = {
        "attempt_count": week_attempts,
        "average_net_wpm": round(sum(week_speed_values) / len(week_speed_values), 2) if week_speed_values else None,
        "average_accuracy": round(sum(week_accuracy_values) / len(week_accuracy_values), 2) if week_accuracy_values else None,
        "speed_goal_met": bool(week_speed_values and sum(week_speed_values) / len(week_speed_values) >= goal.target_net_wpm),
        "accuracy_goal_met": bool(week_accuracy_values and sum(week_accuracy_values) / len(week_accuracy_values) >= goal.target_accuracy),
        "start_date": today - timedelta(days=6),
        "end_date": today,
    }
    # Month-wise summary is derived from the same filtered, learner-owned saved reports.
    monthly = {}
    for row in rows:
        stamp = row["attempt"].completed_at or row["attempt"].started_at
        local_stamp = timezone.localtime(stamp)
        month_key = local_stamp.strftime("%Y-%m")
        bucket = monthly.setdefault(month_key, {"month": local_stamp.date().replace(day=1), "attempt_count": 0, "speeds": [], "accuracies": []})
        bucket["attempt_count"] += 1
        if isinstance(row["speed"], (int, float)):
            bucket["speeds"].append(float(row["speed"]))
        if isinstance(row["accuracy"], (int, float)):
            bucket["accuracies"].append(float(row["accuracy"]))
    monthly_rows = []
    for bucket in sorted(monthly.values(), key=lambda item: item["month"], reverse=True):
        month_speeds, month_accuracies = bucket["speeds"], bucket["accuracies"]
        avg_speed = round(sum(month_speeds) / len(month_speeds), 2) if month_speeds else None
        avg_accuracy = round(sum(month_accuracies) / len(month_accuracies), 2) if month_accuracies else None
        monthly_rows.append({"month": bucket["month"], "attempt_count": bucket["attempt_count"], "average_net_wpm": avg_speed, "average_accuracy": avg_accuracy, "speed_goal_met": bool(avg_speed is not None and avg_speed >= goal.target_net_wpm), "accuracy_goal_met": bool(avg_accuracy is not None and avg_accuracy >= goal.target_accuracy)})

    # 90-day practice calendar uses the full matching queryset, not the 100-row history cap.
    calendar_start = today - timedelta(days=89)
    calendar_attempts = queryset.filter(completed_at__date__gte=calendar_start).only("completed_at", "started_at")
    calendar_counts = {}
    for calendar_attempt in calendar_attempts:
        stamp = calendar_attempt.completed_at or calendar_attempt.started_at
        local_day = timezone.localtime(stamp).date()
        if calendar_start <= local_day <= today:
            calendar_counts[local_day] = calendar_counts.get(local_day, 0) + 1
    calendar_rows = []
    for offset in range(90):
        calendar_day = calendar_start + timedelta(days=offset)
        calendar_rows.append({
            "date": calendar_day,
            "attempt_count": calendar_counts.get(calendar_day, 0),
            "completed": calendar_counts.get(calendar_day, 0) > 0,
        })
    active_days = sum(1 for count in calendar_counts.values() if count > 0)
    consistency_percent = round(active_days * 100 / 90, 1)
    current_streak = 0
    streak_day = today
    while calendar_counts.get(streak_day, 0) > 0:
        current_streak += 1
        streak_day -= timedelta(days=1)
    longest_streak = 0
    running_streak = 0
    for calendar_row in calendar_rows:
        if calendar_row["completed"]:
            running_streak += 1
            longest_streak = max(longest_streak, running_streak)
        else:
            running_streak = 0
    calendar_summary = {
        "active_days": active_days,
        "consistency_percent": consistency_percent,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "attempt_count": sum(calendar_counts.values()),
        "start_date": calendar_start,
        "end_date": today,
    }

    # Compare each recent window with the immediately preceding window of equal length.
    # This uses all matching saved attempts in the date window, not only the 100-row history display.
    progress_cutoff = today - timedelta(days=180)
    progress_attempts = list(queryset.filter(completed_at__date__gte=progress_cutoff).order_by("completed_at"))
    progress_rows = []
    for progress_attempt in progress_attempts:
        report = progress_attempt.result_snapshot.get("dphcm_attempt_report") or {}
        metrics = report.get("practice_metrics") or {}
        stamp = progress_attempt.completed_at or progress_attempt.started_at
        progress_rows.append({
            "date": timezone.localtime(stamp).date(),
            "speed": metrics.get("net_wpm"),
            "accuracy": metrics.get("accuracy_percent"),
        })
    progress_comparisons = []
    for window_days in (30, 60, 90):
        current_start = today - timedelta(days=window_days - 1)
        previous_start = current_start - timedelta(days=window_days)
        previous_end = current_start - timedelta(days=1)
        current_rows = [item for item in progress_rows if current_start <= item["date"] <= today]
        previous_rows = [item for item in progress_rows if previous_start <= item["date"] <= previous_end]
        current_speeds = [float(item["speed"]) for item in current_rows if isinstance(item["speed"], (int, float))]
        previous_speeds = [float(item["speed"]) for item in previous_rows if isinstance(item["speed"], (int, float))]
        current_accuracies = [float(item["accuracy"]) for item in current_rows if isinstance(item["accuracy"], (int, float))]
        previous_accuracies = [float(item["accuracy"]) for item in previous_rows if isinstance(item["accuracy"], (int, float))]
        current_speed = round(sum(current_speeds) / len(current_speeds), 2) if current_speeds else None
        previous_speed = round(sum(previous_speeds) / len(previous_speeds), 2) if previous_speeds else None
        current_accuracy = round(sum(current_accuracies) / len(current_accuracies), 2) if current_accuracies else None
        previous_accuracy = round(sum(previous_accuracies) / len(previous_accuracies), 2) if previous_accuracies else None
        progress_comparisons.append({
            "window_days": window_days,
            "current_attempts": len(current_rows),
            "previous_attempts": len(previous_rows),
            "current_speed": current_speed,
            "previous_speed": previous_speed,
            "speed_change": round(current_speed - previous_speed, 2) if current_speed is not None and previous_speed is not None else None,
            "current_accuracy": current_accuracy,
            "previous_accuracy": previous_accuracy,
            "accuracy_change": round(current_accuracy - previous_accuracy, 2) if current_accuracy is not None and previous_accuracy is not None else None,
            "speed_goal_met": bool(current_speed is not None and current_speed >= goal.target_net_wpm),
            "accuracy_goal_met": bool(current_accuracy is not None and current_accuracy >= goal.target_accuracy),
        })

    # A transparent practice suggestion based on the rolling seven-day saved metrics.
    # These are coaching defaults, not official exam requirements.
    recent_speed = weekly_summary["average_net_wpm"]
    recent_accuracy = weekly_summary["average_accuracy"]
    if recent_speed is None:
        suggested_minutes, suggested_passages = 20, 2
        planner_focus = "Build a consistent baseline with short, careful practice."
    else:
        speed_gap = max(0, goal.target_net_wpm - recent_speed)
        if speed_gap >= goal.target_net_wpm * 0.20:
            suggested_minutes, suggested_passages = 35, 4
            planner_focus = "Prioritize controlled speed-building while maintaining accuracy."
        elif speed_gap > 0:
            suggested_minutes, suggested_passages = 30, 3
            planner_focus = "Work toward your speed target with timed passage practice."
        else:
            suggested_minutes, suggested_passages = 20, 2
            planner_focus = "Maintain your speed and focus on consistent accuracy."
        if recent_accuracy is not None and recent_accuracy < goal.target_accuracy - 5:
            suggested_minutes = min(45, suggested_minutes + 10)
            suggested_passages = min(5, suggested_passages + 1)
            planner_focus = "Prioritize accuracy: slow down, review errors, then complete timed passages."
    daily_practice_plan = {
        "minutes": suggested_minutes,
        "passages": suggested_passages,
        "warmup_minutes": 5,
        "review_minutes": 5,
        "timed_minutes": max(10, suggested_minutes - 10),
        "recent_speed": recent_speed,
        "recent_accuracy": recent_accuracy,
        "focus": planner_focus,
        "based_on_days": 7,
    }

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
        "weekly_daily_rows": weekly_daily_rows,
        "monthly_rows": monthly_rows,
        "progress_comparisons": progress_comparisons,
        "calendar_rows": calendar_rows,
        "calendar_summary": calendar_summary,\n        "daily_practice_plan": daily_practice_plan,
        "weekly_summary": weekly_summary,
        "attempt_count": len(rows),
        "average_net_wpm": round(sum(speeds) / len(speeds), 2) if speeds else None,
        "average_accuracy": round(sum(accuracies) / len(accuracies), 2) if accuracies else None,
        "category_totals": sorted(category_totals.items(), key=lambda item: (-item[1], item[0])),
        "unresolved_total": unresolved_total,
        "start_date": start_raw,
        "end_date": end_raw,
        "selected_language": language,
        "filter_error": filter_error,
        "goal": goal,
        "goal_error": goal_error,
        "goal_speed_progress": min(100, round((sum(speeds) / len(speeds)) * 100 / goal.target_net_wpm)) if speeds else 0,
        "goal_accuracy_progress": min(100, round((sum(accuracies) / len(accuracies)) * 100 / goal.target_accuracy)) if accuracies else 0,
        "goal_speed_met": bool(speeds and sum(speeds) / len(speeds) >= goal.target_net_wpm),
        "goal_accuracy_met": bool(accuracies and sum(accuracies) / len(accuracies) >= goal.target_accuracy),
    })
