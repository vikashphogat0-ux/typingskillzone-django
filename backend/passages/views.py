from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, render

from exams.models import ExamConfiguration
from .models import SimulatorPassage


@login_required
def simulator_catalogue(request):
    """Show every active exam profile using its stored category and identity."""
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
                "key": key, "label": label,
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
    passages = (
        SimulatorPassage.objects.filter(
            exam=exam,
            status=SimulatorPassage.Status.PUBLISHED,
        )
        .select_related("source", "exam")
        .order_by("serial_number")
    )
    return render(
        request,
        "passages/simulator_list.html",
        {"exam": exam, "passages": passages},
    )


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
    return render(request, "passages/simulator_detail.html", {"exam": exam, "passage": passage})
