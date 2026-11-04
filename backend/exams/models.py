from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify


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

    code = models.SlugField(max_length=180, unique=True)
    name = models.CharField(max_length=240)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER, db_index=True)
    language = models.CharField(max_length=20, default="ENGLISH")
    script = models.CharField(max_length=40, blank=True)
    interface_type = models.CharField(max_length=40, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    passage_format = models.CharField(max_length=20, choices=PassageFormat.choices, default=PassageFormat.CUSTOM)
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
        indexes = [models.Index(fields=("category", "is_active")), models.Index(fields=("verification_status", "is_active"))]

    def clean(self):
        super().clean()
        if self.verification_status == self.Verification.VERIFIED:
            if not self.official_source_url or not self.source_title or not self.source_checked_at:
                raise ValidationError("Verified rules require an official source URL, source title and checked date.")
            if not self.duration_seconds:
                raise ValidationError("Verified rules require a confirmed test duration.")

    def __str__(self):
        return f"{self.name} [{self.code}]"
