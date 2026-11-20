"""Bulk passage import from a CSV file.

Columns: title, content, language, script (optional), source_reference (optional).
Parsing never writes to the database. Import runs only after the admin confirms a preview.
"""
import csv
import io

from django.db import transaction

from .models import PassageSource
from .scheduling import apply_schedule, plan_schedule
from .services import auto_target_and_publish

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 500
MAX_CONTENT = 20000
REQUIRED_COLUMNS = ("title", "content", "language")
LANGUAGES = {"ENGLISH", "HINDI"}


def parse_passage_csv(uploaded):
    """Return (rows, errors). Each row is a dict ready for import."""
    if uploaded.size > MAX_BYTES:
        return [], ["The file is larger than 2 MB. Split it into smaller files."]
    try:
        text = uploaded.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], ["The file is not UTF-8. In Excel, choose 'CSV UTF-8' when saving, then upload again."]

    reader = csv.DictReader(io.StringIO(text))
    headers = {(name or "").strip().lower() for name in (reader.fieldnames or [])}
    missing = [column for column in REQUIRED_COLUMNS if column not in headers]
    if missing:
        return [], [f"Missing column(s): {', '.join(missing)}. Required: title, content, language. Optional: script, source_reference."]

    rows, errors = [], []
    for line_number, record in enumerate(reader, start=2):
        if len(rows) >= MAX_ROWS:
            errors.append(f"Only the first {MAX_ROWS} rows are read. Split the file to import the rest.")
            break
        cleaned = {key.strip().lower(): (value or "").strip() for key, value in record.items() if key}
        if not any(cleaned.values()):
            continue
        problems = []
        title = cleaned.get("title", "")
        content = cleaned.get("content", "")
        language = cleaned.get("language", "").upper()
        if not title:
            problems.append("title is empty")
        elif len(title) > 240:
            problems.append("title is longer than 240 characters")
        if not content:
            problems.append("content is empty")
        elif len(content) > MAX_CONTENT:
            problems.append(f"content is longer than {MAX_CONTENT:,} characters")
        if language not in LANGUAGES:
            problems.append("language must be ENGLISH or HINDI")
        if problems:
            errors.append(f"Row {line_number}: " + "; ".join(problems))
            continue
        rows.append({
            "row": line_number,
            "title": title,
            "content": content,
            "language": language,
            "script": cleaned.get("script", "").upper()[:40],
            "source_reference": cleaned.get("source_reference", "")[:500],
        })
    return rows, errors


@transaction.atomic
def import_passages(rows, user, publish, start_date):
    """Create draft sources, publish to matching exams, and optionally schedule from start_date."""
    from exams.models import ExamConfiguration

    created = 0
    published = 0
    scheduled = 0
    skipped = []
    problems = []
    for item in rows:
        if PassageSource.objects.filter(title=item["title"], language=item["language"]).exists():
            skipped.append(f"Row {item['row']}: \"{item['title']}\" already exists for {item['language']}.")
            continue
        source = PassageSource.objects.create(
            title=item["title"],
            content=item["content"],
            language=item["language"],
            script=item["script"],
            source_reference=item["source_reference"],
            created_by=user,
            status=PassageSource.Status.DRAFT,
        )
        created += 1
        if publish:
            try:
                published += len(auto_target_and_publish(source))
            except ValueError as error:
                problems.append(f"{source.title}: {error}")

    if publish and start_date:
        for exam in ExamConfiguration.objects.filter(is_active=True).order_by("code"):
            try:
                plan = plan_schedule(exam, start_date)
            except ValueError as error:
                problems.append(f"{exam.name}: {error}")
                continue
            if plan:
                scheduled += apply_schedule(plan)

    return {"created": created, "published": published, "scheduled": scheduled, "skipped": skipped, "problems": problems}
