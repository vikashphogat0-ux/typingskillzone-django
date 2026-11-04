from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class LearnerProfile(models.Model):
    class Language(models.TextChoices):
        ENGLISH = "ENGLISH", "English"
        HINDI = "HINDI", "Hindi"
        MARATHI = "MARATHI", "Marathi"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="learner_profile",
    )
    display_name = models.CharField(max_length=120, blank=True)
    preferred_language = models.CharField(
        max_length=12,
        choices=Language.choices,
        default=Language.ENGLISH,
    )
    preferred_script = models.CharField(max_length=40, blank=True)
    target_wpm = models.PositiveSmallIntegerField(
        default=40,
        validators=[MinValueValidator(1), MaxValueValidator(300)],
    )
    target_accuracy = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=95.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    daily_practice_goal_minutes = models.PositiveSmallIntegerField(
        default=30,
        validators=[MaxValueValidator(600)],
    )
    timezone = models.CharField(max_length=64, default="Asia/Kolkata")
    onboarding_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("display_name", "user__email")
        indexes = [
            models.Index(fields=("preferred_language", "onboarding_completed"), name="lrn_lang_onboard_idx"),
        ]

    def __str__(self):
        return self.display_name or self.user.email
