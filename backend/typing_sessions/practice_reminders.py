from datetime import time

from django.conf import settings
from django.db import models


class LearnerPracticeReminder(models.Model):
    """Learner-owned dashboard reminder preference; no external notification is sent."""

    learner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="typing_practice_reminder",
    )
    enabled = models.BooleanField(default=False)
    reminder_time = models.TimeField(default=time(18, 0))
    updated_at = models.DateTimeField(auto_now=True)
