"""Automatic release scheduling for unscheduled published passages.

Each exam's queue is taken in upload order (serial number) and placed into daily slots:
morning (5), afternoon (5) and evening special (2). A day holds 12 passages per exam.
Passages that already have a schedule are never moved. A plan that would overlap an
existing schedule is refused instead of overwriting it.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import SimulatorPassage

DAY_SLOTS = (("MORNING", 5), ("AFTERNOON", 5), ("EVENING", 2))
PER_DAY = sum(capacity for _, capacity in DAY_SLOTS)


def default_start_date():
    """Tomorrow, so nothing is released before it has been reviewed."""
    return timezone.localdate() + timedelta(days=1)


def queue_for(exam):
    return list(
        SimulatorPassage.objects.filter(
            exam=exam, status=SimulatorPassage.Status.PUBLISHED, release_date__isnull=True
        ).order_by("serial_number")
    )


def plan_schedule(exam, start_date):
    """Return a list of (passage, date, slot, position) for the exam's unscheduled queue."""
    queue = queue_for(exam)
    if not queue:
        return []
    clash = SimulatorPassage.objects.filter(exam=exam, release_date__gte=start_date).exists()
    if clash:
        raise ValueError(f"Scheduled passages already exist on or after {start_date:%d %b %Y}. Choose a later start date.")

    plan = []
    day = start_date
    index = 0
    while index < len(queue):
        for slot, capacity in DAY_SLOTS:
            for position in range(1, capacity + 1):
                if index >= len(queue):
                    break
                plan.append((queue[index], day, slot, position))
                index += 1
        day += timedelta(days=1)
    return plan


@transaction.atomic
def apply_schedule(plan):
    for passage, day, slot, position in plan:
        passage.release_date = day
        passage.release_slot = slot
        passage.release_position = position
        passage.save(update_fields=("release_date", "release_slot", "release_position"))
    return len(plan)


def latest_scheduled_date(exam):
    return SimulatorPassage.objects.filter(exam=exam).aggregate(last=Max("release_date"))["last"]
