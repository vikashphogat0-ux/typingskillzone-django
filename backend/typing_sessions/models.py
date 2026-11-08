import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class TypingSession(models.Model):
    """Private learner-owned attempt; institute context is deliberately not inferred."""

    class State(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUBMITTED = "SUBMITTED", "Submitted"
        EXPIRED = "EXPIRED", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    learner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="typing_sessions")
    publication = models.ForeignKey("passages.SimulatorPassage", on_delete=models.PROTECT, related_name="typing_sessions")
    state = models.CharField(max_length=12, choices=State.choices, default=State.ACTIVE, db_index=True)
    started_at = models.DateTimeField(default=timezone.now)
    deadline_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    # Snapshots protect historical attempts when a passage or exam configuration changes.
    reference_text = models.TextField()
    submitted_text = models.TextField(blank=True)
    rules_snapshot = models.JSONField(default=dict)
    # Persist the exact scoring implementation version used for this attempt.
    scoring_version = models.CharField(max_length=32, blank=True)
    result_snapshot = models.JSONField(default=dict)

    class Meta:
        ordering = ("-started_at",)
        indexes = [models.Index(fields=("learner", "state", "started_at"), name="typing_user_state_idx")]

    @property
    def has_expired(self):
        return bool(self.deadline_at and timezone.now() >= self.deadline_at)

    def __str__(self):
        return f"{self.learner_id}: {self.publication_id} ({self.state})"
