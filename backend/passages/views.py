from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import Http404
import re

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from exams.models import ExamConfiguration
from .models import SimulatorPassage



@login_required
def simulator_catalogue(request):
    """List active exam configurations grouped by their stored category."""
    exams = list(
        ExamConfiguration.objects.filter(is_active=True).order_by(
            "category", "display_order", "name", "code"
        )
    )
    category_counts = {
        row["category"]: row["total"]
        for row in ExamConfiguration.objects.filter(is_active=True)
        .values("category")
        .annotate(total=Count("id"))
    }
    category_icons = {
        "SSC": "📘", "COURT": "⚖️", "RAILWAY": "🚆", "POLICE": "🛡️",
        "STATE": "🏛️", "UNIVERSITY": "🎓", "CENTRAL": "🇮🇳", "PSU": "🏢",
        "PRACTICE": "⚡", "OTHER": "🗂️",
    }
    category_groups = []
    for key, label in ExamConfiguration.Category.choices:
        category_exams = [exam for exam in exams if exam.category == key]
        if category_exams:
            category_groups.append({
                "key": key,
                "label": label,
                "icon": category_icons.get(key, "🗂️"),
                "count": category_counts.get(key, len(category_exams)),
                "exams": category_exams,
            })
    return render(request, "passages/simulator_catalogue.html", {
        "category_groups": category_groups,
        "exam_count": len(exams),
        "category_count": len(category_groups),
    })

@login_required
def simulator_passage_list(request, exam_code):
    exam = get_object_or_404(ExamConfiguration, code=exam_code, is_active=True)
    return redirect("exams:exam_detail", code=exam.code)


@login_required
def simulator_passage_pdf(request, exam_code, passage_id):
    """Printable passage sheet. Published and released passages only."""
    from django.http import HttpResponse

    from .pdf import UnsupportedScript, build_passage_pdf

    exam = get_object_or_404(ExamConfiguration, code=exam_code, is_active=True)
    try:
        serial_number = int(passage_id)
    except (TypeError, ValueError):
        raise Http404("Passage not found.")
    passage = get_object_or_404(
        SimulatorPassage.objects.select_related("source", "exam"),
        exam=exam,
        serial_number=serial_number,
        status=SimulatorPassage.Status.PUBLISHED,
    )
    if not passage.is_released():
        raise Http404("This passage is not released yet.")
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", passage.source.content) if part.strip()]
    try:
        pdf = build_passage_pdf(
            test_number=passage.test_number,
            exam_name=exam.name,
            title=passage.source.title,
            paragraphs=paragraphs,
        )
    except UnsupportedScript as error:
        return HttpResponse(str(error), status=422, content_type="text/plain; charset=utf-8")
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{passage.test_number}.pdf"'
    return response


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
    return render(
        request,
        "passages/simulator_detail.html",
        {"exam": exam, "passage": passage},
    )
