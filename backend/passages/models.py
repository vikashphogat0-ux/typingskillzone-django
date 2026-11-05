from django.conf import settings
from django.db import models
from django.utils import timezone


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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("exam", "serial_number")
        constraints = [
            models.UniqueConstraint(fields=("exam", "serial_number"), name="uniq_exam_passage_serial"),
            models.UniqueConstraint(fields=("exam", "source"), name="uniq_exam_source_publication"),
        ]
        indexes = [models.Index(fields=("exam", "status", "serial_number"), name="passage_exam_status_num_idx")]

    @property
    def passage_id(self):
        return f"{self.serial_number:02d}"

    @property
    def rendered_content(self):
        """Render through the canonical passage domain, retaining legacy fallback."""
        import re
        from exams.specifications import resolve_exam_specification

        passage = resolve_exam_specification(self.exam)["passage"]
        raw = self.source.content.replace("\r\n", "\n").replace("\r", "\n").strip()
        layout = passage["layout"]
        if layout == self.exam.PassageLayout.UNCONFIGURED:
            legacy_format = passage["format"]
            if legacy_format == self.exam.PassageFormat.CONTINUOUS:
                layout = self.exam.PassageLayout.CONTINUOUS
            elif legacy_format == self.exam.PassageFormat.PARAGRAPHS:
                layout = self.exam.PassageLayout.PARAGRAPHS
            elif legacy_format == self.exam.PassageFormat.TCS:
                layout = self.exam.PassageLayout.TCS

        if layout == self.exam.PassageLayout.CONTINUOUS:
            parts = [re.sub(r"\\s+", " ", p).strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
            return " ".join(parts)
        if layout == self.exam.PassageLayout.PARAGRAPHS:
            parts = [re.sub(r"\\s+", " ", p).strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
            return "\n\n".join(parts)
        if layout == self.exam.PassageLayout.PARA_TAB:
            typography = passage["typography"]
            tab_size = typography["tab_size"] or 4
            return raw if typography["preserve_tabs"] else raw.replace("\t", " " * tab_size)
        if layout == self.exam.PassageLayout.TCS:
            parts = [re.sub(r"\\s+", " ", p).strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
            return "\n\n".join(parts)
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
        return f"{self.exam.name} — Passage {self.passage_id}"    @property
    def rendered_content(self):
        """Render using the canonical passage domain, preserving legacy layout fallback."""
        import re
        from exams.specifications import resolve_exam_specification

        passage = resolve_exam_specification(self.exam)["passage"]
        raw = self.source.content.replace("\r\n", "\n").replace("\r", "\n").strip()
        layout = passage["layout"]
        if layout == self.exam.PassageLayout.UNCONFIGURED:
            legacy_format = passage["format"]
            if legacy_format == self.exam.PassageFormat.CONTINUOUS:
                layout = self.exam.PassageLayout.CONTINUOUS
            elif legacy_format == self.exam.PassageFormat.PARAGRAPHS:
                layout = self.exam.PassageLayout.PARAGRAPHS
            elif legacy_format == self.exam.PassageFormat.TCS:
                layout = self.exam.PassageLayout.TCS

        if layout == self.exam.PassageLayout.CONTINUOUS:
            parts = [re.sub(r"\\s+", " ", p).strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
            return " ".join(parts)
        if layout == self.exam.PassageLayout.PARAGRAPHS:
            parts = [re.sub(r"\\s+", " ", p).strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
            return "\n\n".join(parts)
        if layout == self.exam.PassageLayout.PARA_TAB:
            typography = passage["typography"]
            return raw if typography["preserve_tabs"] else raw.replace("\t", " " * (typography["tab_size"] or 4))
        if layout == self.exam.PassageLayout.TCS:
            parts = [re.sub(r"\\s+", " ", p).strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
            return "\n\n".join(parts)
        return raw


