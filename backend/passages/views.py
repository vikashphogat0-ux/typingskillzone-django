from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from exams.models import ExamConfiguration
from .models import SimulatorPassage, released_queryset


@login_required
def simulator_passage_list(request, exam_code):
    exam = get_object_or_404(ExamConfiguration, code=exam_code, is_active=True)
    passages = (
        SimulatorPassage.objects.filter(
            exam=exam,
            status=SimulatorPassage.Status.PUBLISHED,
        )
        .select_related("source", "exam")
        .order_by("serial_number")
    )
    passages = released_queryset(passages)
    return redirect("exams:exam_detail", code=exam.code)


@login_required
def simulator_passage_detail(request, exam_code, passage_id):
    exam = get_object_or_404(ExamConfiguration, code=exam_code, is_active=True)
    try:
        serial_number = int(passage_id)
    except (TypeError, ValueError):
        serial_number = -1
    passage = get_object_or_404(
        SimulatorPassage.objects.select_related("source", "exam"),
        exam=exam,
        serial_number=serial_number,
        status=SimulatorPassage.Status.PUBLISHED,
    )
    if not passage.is_released():
        raise Http404("This passage is not released yet.")
    workspace_url = reverse("exams:exam_detail", kwargs={"code": exam.code})
    return redirect(f"{workspace_url}?passage={passage.serial_number}")
