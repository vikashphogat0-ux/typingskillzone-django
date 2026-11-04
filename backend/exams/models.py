from django.core.exceptions import ValidationError
from django.db import models


class ExamConfiguration(models.Model):
    class Category(models.TextChoices):
        SSC = "SSC", "SSC"
        COURT = "COURT", "High Courts & Judiciary"
        RAILWAY = "RAILWAY", "Railways"
        POLICE = "POLICE", "Police & CAPF"
        STATE = "STATE", "State Government"
        UNIVERSITY = "UNIVERSITY", "Universities & Education"
        CENTRAL = "CENTRAL", "Central Government"
        PSU = "PSU", "PSU & Other Recruitments"
        PRACTICE = "PRACTICE", "Practice & Speed Booster"
        OTHER = "OTHER", "Other"

    class Verification(models.TextChoices):
        UNVERIFIED = "UNVERIFIED", "Unverified"
        PARTIAL = "PARTIAL", "Partially verified"
        VERIFIED = "VERIFIED", "Verified"

    class PassageFormat(models.TextChoices):
        CONTINUOUS = "CONTINUOUS", "Continuous paragraph"
        PARAGRAPHS = "PARAGRAPHS", "Paragraphs"
        TCS = "TCS", "TCS-style interface"
        CUSTOM = "CUSTOM", "Custom / exam-specific"

    class PassageLayout(models.TextChoices):
        UNCONFIGURED = "UNCONFIGURED", "Pending format verification"
        CONTINUOUS = "CONTINUOUS", "Continuous text"
        PARAGRAPHS = "PARAGRAPHS", "Paragraphs"
        PARA_TAB = "PARA_TAB", "Paragraph and tab matter"
        TCS = "TCS", "TCS-style presentation"
        CUSTOM = "CUSTOM", "Custom layout"

    class PresentationReferenceStatus(models.TextChoices):
        PENDING = "PENDING", "Pending reference check"
        REVIEWED = "REVIEWED", "Reference reviewed (practice source)"
        VERIFIED = "VERIFIED", "Verified against authoritative presentation source"

    class TextAlignment(models.TextChoices):
        LEFT = "left", "Left"
        JUSTIFY = "justify", "Justify"
        CENTER = "center", "Center"

    code = models.SlugField(max_length=180, unique=True)
    name = models.CharField(max_length=240)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER, db_index=True)
    language = models.CharField(max_length=20, default="ENGLISH")
    script = models.CharField(max_length=40, blank=True)
    interface_type = models.CharField(max_length=40, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    passage_format = models.CharField(max_length=20, choices=PassageFormat.choices, default=PassageFormat.CUSTOM)
    passage_layout = models.CharField(max_length=20, choices=PassageLayout.choices, default=PassageLayout.UNCONFIGURED)
    passage_font_family = models.CharField(max_length=80, default="Arial")
    passage_font_size_pt = models.PositiveSmallIntegerField(default=12)
    passage_line_height = models.DecimalField(max_digits=3, decimal_places=2, default=1.60)
    passage_paragraph_spacing_pt = models.PositiveSmallIntegerField(default=12)
    passage_alignment = models.CharField(max_length=10, choices=TextAlignment.choices, default=TextAlignment.LEFT)
    passage_first_line_indent_em = models.DecimalField(max_digits=3, decimal_places=1, default=0)
    passage_preserve_tabs = models.BooleanField(default=False)
    passage_tab_size = models.PositiveSmallIntegerField(default=4)
    presentation_reference_status = models.CharField(max_length=12, choices=PresentationReferenceStatus.choices, default=PresentationReferenceStatus.PENDING, db_index=True)
    presentation_reference_url = models.URLField(blank=True)
    presentation_reference_title = models.CharField(max_length=240, blank=True)
    presentation_reference_checked_at = models.DateField(null=True, blank=True)
    presentation_notes = models.TextField(blank=True)
    passage_word_limit = models.PositiveIntegerField(null=True, blank=True)
    allow_backspace = models.BooleanField(default=True)
    allow_arrow_navigation = models.BooleanField(default=True)
    error_rules = models.JSONField(default=dict, blank=True)
    scoring_rules = models.JSONField(default=dict, blank=True)
    qualification_rules = models.JSONField(default=dict, blank=True)
    verification_status = models.CharField(max_length=12, choices=Verification.choices, default=Verification.UNVERIFIED, db_index=True)
    official_source_url = models.URLField(blank=True)
    source_title = models.CharField(max_length=240, blank=True)
    source_checked_at = models.DateField(null=True, blank=True)
    rule_notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("category", "display_order", "name")
        indexes = [
            models.Index(fields=("category", "is_active"), name="exams_exam_categor_2c4b13_idx"),
            models.Index(fields=("verification_status", "is_active"), name="exams_exam_verifi_12a4ab_idx"),
            models.Index(fields=("passage_layout", "presentation_reference_status"), name="exam_passage_layout_idx"),
        ]

    def clean(self):
        super().clean()
        if self.passage_font_size_pt < 8 or self.passage_font_size_pt > 32:
            raise ValidationError({"passage_font_size_pt": "Passage font size must be between 8 and 32 pt."})
        if self.passage_line_height < 1 or self.passage_line_height > 3:
            raise ValidationError({"passage_line_height": "Line height must be between 1.00 and 3.00."})
        if self.passage_tab_size < 1 or self.passage_tab_size > 16:
            raise ValidationError({"passage_tab_size": "Tab size must be between 1 and 16."})
        if self.presentation_reference_status == self.PresentationReferenceStatus.REVIEWED:
            if not self.presentation_reference_url or not self.presentation_reference_title or not self.presentation_reference_checked_at:
                raise ValidationError("A reviewed presentation reference requires its URL, title and checked date.")
        if self.presentation_reference_status == self.PresentationReferenceStatus.VERIFIED:
            if not self.presentation_reference_url or not self.presentation_reference_title or not self.presentation_reference_checked_at:
                raise ValidationError("Verified presentation requires an authoritative source URL, title and checked date.")
        if self.verification_status == self.Verification.VERIFIED:
            if not self.official_source_url or not self.source_title or not self.source_checked_at:
                raise ValidationError("Verified rules require an official source URL, source title and checked date.")
            if not self.duration_seconds:
                raise ValidationError("Verified rules require a confirmed test duration.")

    def __str__(self):
        return f"{self.name} [{self.code}]"
