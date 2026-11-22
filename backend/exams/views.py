from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from exams.models import ExamConfiguration
from passages.models import SimulatorPassage, released_queryset


def _published_filter():
    return Q(published_passages__status=SimulatorPassage.Status.PUBLISHED)


def catalogue(request):
    """Public, category-based exam catalogue; practice-only entries are excluded."""
    query = request.GET.get("q", "").strip()[:80]
    language = request.GET.get("lang", "").strip().upper()[:20]

    base = ExamConfiguration.objects.filter(is_active=True).exclude(
        category=ExamConfiguration.Category.PRACTICE
    )
    languages = sorted({value for value in base.values_list("language", flat=True) if value})

    exams = base.annotate(passage_count=Count("published_passages", filter=_published_filter()))
    if query:
        exams = exams.filter(Q(name__icontains=query) | Q(code__icontains=query))
    if language:
        exams = exams.filter(language=language)
    exams = exams.order_by("category", "display_order", "name")

    category_groups = []
    for key, label in ExamConfiguration.Category.choices:
        if key == ExamConfiguration.Category.PRACTICE:
            continue
        category_exams = [exam for exam in exams if exam.category == key]
        if category_exams:
            category_groups.append({
                "key": key,
                "label": label,
                "count": len(category_exams),
                "exams": category_exams,
            })

    return render(request, "exams/catalogue.html", {
        "category_groups": category_groups,
        "query": query,
        "selected_language": language,
        "languages": languages,
        "total_exams": base.count(),
        "visible_exams": sum(group["count"] for group in category_groups),
    })


@login_required
def exam_detail(request, code):
    """Pattern, rules and passages for one authenticated student's exam."""
    if request.user.role != "STUDENT":
        return HttpResponseForbidden("Student account required.")
    exam = get_object_or_404(ExamConfiguration, code=code, is_active=True)
    passages = (
        SimulatorPassage.objects.filter(exam=exam, status=SimulatorPassage.Status.PUBLISHED)
        .select_related("source")
        .order_by("-published_at", "serial_number")
    )
    passages = released_queryset(passages)
    not_published = exam.scoring_mode == "GENERIC" and not exam.rule_notes
    available_passages = passages
    selected_passage_id = request.GET.get("passage", "").strip()
    if not selected_passage_id and available_passages:
        selected_passage_id = str(available_passages[0].serial_number)
    return render(request, "exams/exam_detail.html", {
        "exam": exam,
        "duration_minutes": (exam.duration_seconds // 60) if exam.duration_seconds else None,
        "recent_passages": available_passages,
        "published_count": passages.count(),
        "not_published": not_published,
        "selected_passage_id": selected_passage_id,
    })
