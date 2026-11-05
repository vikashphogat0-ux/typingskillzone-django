from django.conf import settings
from django.db import models


class LearnerPracticeGoal(models.Model):
    """Personal practice targets; never used for official scoring."""

    learner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="typing_practice_goals",
    )
    profile_code = models.CharField(
        max_length=64,
        default="DELHI_POLICE_HCM_2025",
    )
    target_net_wpm = models.PositiveSmallIntegerField(default=30)
    target_accuracy = models.PositiveSmallIntegerField(default=95)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("learner", "profile_code"),
                name="unique_learner_practice_goal",
            )
        ]
