from django.db import IntegrityError, transaction

from .models import ExamPassageSequence, PassageSource, SimulatorPassage


@transaction.atomic
def publish_source_to_exam(source: PassageSource, exam) -> SimulatorPassage:
    """Publish one central source into one simulator with its own serial sequence."""
    if source.language.casefold() != exam.language.casefold():
        raise ValueError(
            f"Language mismatch: source is {source.language}, but {exam.name} expects {exam.language}."
        )
    if source.script and exam.script and source.script.casefold() != exam.script.casefold():
        raise ValueError(
            f"Script mismatch: source is {source.script}, but {exam.name} expects {exam.script}."
        )

    existing = SimulatorPassage.objects.filter(exam=exam, source=source).first()
    if existing:
        if existing.status != SimulatorPassage.Status.PUBLISHED:
            existing.status = SimulatorPassage.Status.PUBLISHED
            existing.save(update_fields=("status",))
        return existing

    # get_or_create safely handles the first publication racing to create a
    # simulator's counter row. The row lock serializes subsequent allocations
    # on PostgreSQL production databases.
    sequence, _ = ExamPassageSequence.objects.get_or_create(exam=exam)
    sequence = ExamPassageSequence.objects.select_for_update().get(pk=sequence.pk)

    serial = sequence.next_number
    sequence.next_number = serial + 1
    sequence.save(update_fields=("next_number", "updated_at"))

    return SimulatorPassage.objects.create(
        exam=exam,
        source=source,
        serial_number=serial,
    )


@transaction.atomic
def publish_source_to_selected_exams(source: PassageSource):
    if source.status != PassageSource.Status.PUBLISHED:
        source.status = PassageSource.Status.PUBLISHED
        source.save(update_fields=("status", "updated_at"))
    publications = []
    for exam in source.target_exams.filter(is_active=True).order_by("id"):
        publications.append(publish_source_to_exam(source, exam))
    return publications
