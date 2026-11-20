from django.db import IntegrityError, transaction
from django.db.models import Q

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

    # Another publisher may have created this source/exam publication while
    # this transaction waited for the sequence lock. Re-check under the lock
    # before allocating a serial number.
    existing = SimulatorPassage.objects.filter(exam=exam, source=source).first()
    if existing:
        if existing.status != SimulatorPassage.Status.PUBLISHED:
            existing.status = SimulatorPassage.Status.PUBLISHED
            existing.save(update_fields=("status",))
        return existing

    serial = sequence.next_number
    sequence.next_number = serial + 1
    sequence.save(update_fields=("next_number", "updated_at"))

    return SimulatorPassage.objects.create(
        exam=exam,
        source=source,
        serial_number=serial,
    )


def publish_source_to_selected_exams(source: PassageSource):
    if source.status != PassageSource.Status.PUBLISHED:
        source.status = PassageSource.Status.PUBLISHED
        source.save(update_fields=("status", "updated_at"))
    publications = []
    for exam in source.target_exams.filter(is_active=True).order_by("id"):
        publications.append(publish_source_to_exam(source, exam))
    return publications


def matching_exams(source: PassageSource):
    """Active exams that accept this passage's language, and script where both sides specify one."""
    from exams.models import ExamConfiguration

    queryset = ExamConfiguration.objects.filter(is_active=True, language__iexact=source.language)
    if source.script:
        queryset = queryset.filter(Q(script__iexact=source.script) | Q(script=""))
    return queryset.order_by("id")


def auto_target_and_publish(source: PassageSource):
    """Set every matching exam as a target, then publish to all of them."""
    source.target_exams.set(list(matching_exams(source)))
    return publish_source_to_selected_exams(source)



def publish_sources_to_matching_exams(sources):
    """Publish many sources efficiently, committing once per exam.

    The exam sequence row is locked once for the whole source batch. Existing
    source/exam publications are reactivated without changing their serial IDs;
    only missing publications consume new serial numbers. Each exam is its own
    transaction, so a failure cannot roll back already completed exams.
    """
    sources = list(sources)
    if not sources:
        return {"created": 0, "reactivated": 0, "failures": []}

    from .models import ExamPassageSequence
    grouped = {}
    for source in sources:
        exams = list(matching_exams(source))
        source.target_exams.set(exams)
        if source.status != PassageSource.Status.PUBLISHED:
            source.status = PassageSource.Status.PUBLISHED
            source.save(update_fields=("status", "updated_at"))
        for exam in exams:
            grouped.setdefault(exam.pk, (exam, []))[1].append(source)

    created = 0
    reactivated = 0
    failures = []
    for exam, exam_sources in grouped.values():
        try:
            with transaction.atomic():
                sequence, _ = ExamPassageSequence.objects.get_or_create(exam=exam)
                sequence = ExamPassageSequence.objects.select_for_update().get(pk=sequence.pk)
                source_ids = [source.pk for source in exam_sources]
                existing = list(
                    SimulatorPassage.objects.filter(
                        exam=exam, source_id__in=source_ids
                    ).order_by("source_id")
                )
                existing_by_source = {item.source_id: item for item in existing}
                archived = [
                    item for item in existing
                    if item.status != SimulatorPassage.Status.PUBLISHED
                ]
                if archived:
                    SimulatorPassage.objects.filter(
                        pk__in=[item.pk for item in archived]
                    ).update(status=SimulatorPassage.Status.PUBLISHED)
                    reactivated += len(archived)

                missing = [
                    source for source in exam_sources
                    if source.pk not in existing_by_source
                ]
                if missing:
                    first_serial = sequence.next_number
                    SimulatorPassage.objects.bulk_create([
                        SimulatorPassage(
                            exam=exam,
                            source=source,
                            serial_number=first_serial + offset,
                        )
                        for offset, source in enumerate(missing)
                    ])
                    sequence.next_number = first_serial + len(missing)
                    sequence.save(update_fields=("next_number", "updated_at"))
                    created += len(missing)
        except Exception as error:
            # Preserve successful exam commits and report the failed exam so the
            # administrator can safely retry; publication is idempotent.
            failures.append(f"{exam.name}: {error.__class__.__name__}: {error}")

    return {"created": created, "reactivated": reactivated, "failures": failures}
