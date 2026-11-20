from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

# Release schedule is in Indian Standard Time, whatever the server's timezone.
LOCAL_TZ = ZoneInfo("Asia/Kolkata")


class ReleaseSlot(models.TextChoices):
    MORNING = "MORNING", "Morning (07:00)"
    AFTERNOON = "AFTERNOON", "Afternoon (13:00)"
    EVENING = "EVENING", "Evening special (19:00)"


RELEASE_TIMES = {
    "MORNING": time(7, 0),
    "AFTERNOON": time(13, 0),
    "EVENING": time(19, 0),
}
SLOT_CAPACITY = {"MORNING": 5, "AFTERNOON": 5, "EVENING": 2}


class PassageSource(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        ARCHIVED = "ARCHIVED", "Archived"

    title = models.CharField(max_length=240)
    content = models.TextField()
    language = models.CharField(max_length=20, default="ENGLISH", db_index=True)
    script = models.CharField(max_length=40, blank=True)
    source_reference = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default="DRAFT", db_index=True)
    target_exams = models.ManyToManyField("exams.ExamConfiguration", blank=True, related_name="central_passage_sources", help_text="Select every simulator that should receive this source passage.")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_passage_sources")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "title")
        indexes = [models.Index(fields=("status", "language"), name="passage_src_status_lang_idx")]

    def __str__(self):
        return f"{self.title} [{self.language}]"


class ExamPassageSequence(models.Model):
    """Independent, locked serial counter for each exam simulator."""
    exam = models.OneToOneField("exams.ExamConfiguration", on_delete=models.PROTECT, related_name="passage_sequence")
    next_number = models.PositiveBigIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.exam.code}: next {self.next_number}"


class SimulatorPassage(models.Model):
    class Status(models.TextChoices):
        PUBLISHED = "PUBLISHED", "Published"
        ARCHIVED = "ARCHIVED", "Archived"

    exam = models.ForeignKey("exams.ExamConfiguration", on_delete=models.PROTECT, related_name="published_passages")
    source = models.ForeignKey(PassageSource, on_delete=models.PROTECT, related_name="simulator_publications")
    serial_number = models.PositiveBigIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default="PUBLISHED", db_index=True)
    published_at = models.DateTimeField(default=timezone.now)
    release_date = models.DateField(null=True, blank=True, db_index=True)
    release_slot = models.CharField(max_length=10, choices=ReleaseSlot.choices, blank=True, default="")
    release_position = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("exam", "serial_number")
        constraints = [
            models.UniqueConstraint(fields=("exam", "serial_number"), name="uniq_exam_passage_serial"),
            models.UniqueConstraint(fields=("exam", "source"), name="uniq_exam_source_publication"),
            models.UniqueConstraint(
                fields=("exam", "release_date", "release_slot", "release_position"),
                condition=Q(release_date__isnull=False),
                name="uniq_exam_release_slot_position",
            ),
        ]
        indexes = [models.Index(fields=("exam", "status", "serial_number"), name="passage_exam_status_num_idx")]

    @property
    def passage_id(self):
        return f"{self.serial_number:02d}"

    @property
    def release_at(self):
        """The moment this passage opens, or None if it has no schedule."""
        if not (self.release_date and self.release_slot):
            return None
        return datetime.combine(self.release_date, RELEASE_TIMES[self.release_slot], tzinfo=LOCAL_TZ)

    def is_released(self, now=None):
        """Unscheduled passages stay available. Scheduled ones open at their slot time."""
        release = self.release_at
        if release is None:
            return True
        return (now or timezone.now()) >= release

    def clean(self):
        super().clean()
        scheduled = [bool(self.release_date), bool(self.release_slot), self.release_position is not None]
        if any(scheduled) and not all(scheduled):
            raise ValidationError("Set the release date, slot and position together, or leave all three empty.")
        if self.release_slot:
            capacity = SLOT_CAPACITY[self.release_slot]
            if not (1 <= (self.release_position or 0) <= capacity):
                raise ValidationError(f"Position must be between 1 and {capacity} for this slot.")

    @property
    def rendered_content(self):
        """Format the shared original using this simulator's independently configured layout."""
        import re

        raw = self.source.content.replace("\r\n", "\n").replace("\r", "\n").strip()
        exam = self.exam
        layout = exam.passage_layout
        # Backward compatibility for records configured before presentation profiles existed.
        if layout == exam.PassageLayout.UNCONFIGURED:
            if exam.passage_format == exam.PassageFormat.CONTINUOUS:
                layout = exam.PassageLayout.CONTINUOUS
            elif exam.passage_format == exam.PassageFormat.PARAGRAPHS:
                layout = exam.PassageLayout.PARAGRAPHS
            elif exam.passage_format == exam.PassageFormat.TCS:
                layout = exam.PassageLayout.TCS
        if layout == exam.PassageLayout.CONTINUOUS:
            parts = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
            return " ".join(parts)
        if layout == exam.PassageLayout.PARAGRAPHS:
            parts = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
            return "\n\n".join(parts)
        if layout == exam.PassageLayout.PARA_TAB:
            # Preserve source tabs and line boundaries; browser tab-size is configured in the template.
            return raw.replace("\t", " " * exam.passage_tab_size) if not exam.passage_preserve_tabs else raw
        if layout == exam.PassageLayout.TCS:
            parts = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
            return "\n\n".join(parts)
        # Unconfigured/custom layouts never silently impose a guessed transformation.
        return raw

    @property
    def rendered_paragraphs(self):
        """Return normalized paragraph blocks for paragraph-based simulator templates."""
        return [
            paragraph.strip()
            for paragraph in self.rendered_content.split("\n\n")
            if paragraph.strip()
        ]

    def __str__(self):
        return f"{self.exam.name} — Passage {self.passage_id}"


def released_queryset(queryset, now=None):
    """Keep scheduled passages whose slot has opened, plus all unscheduled passages."""
    local_now = timezone.localtime(now or timezone.now(), LOCAL_TZ)
    today = local_now.date()
    open_slots = [slot for slot, opens in RELEASE_TIMES.items() if opens <= local_now.time()]
    return queryset.filter(
        Q(release_date__isnull=True)
        | Q(release_date__lt=today)
        | Q(release_date=today, release_slot__in=open_slots)
    )

