from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LearnerProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("display_name", models.CharField(blank=True, max_length=120)),
                ("preferred_language", models.CharField(
                    choices=[("ENGLISH", "English"), ("HINDI", "Hindi"), ("MARATHI", "Marathi")],
                    default="ENGLISH",
                    max_length=12,
                )),
                ("preferred_script", models.CharField(blank=True, max_length=40)),
                ("target_wpm", models.PositiveSmallIntegerField(
                    default=40,
                    validators=[MinValueValidator(1), MaxValueValidator(300)],
                )),
                ("target_accuracy", models.DecimalField(
                    decimal_places=2,
                    default=95.00,
                    max_digits=5,
                    validators=[MinValueValidator(0), MaxValueValidator(100)],
                )),
                ("daily_practice_goal_minutes", models.PositiveSmallIntegerField(
                    default=30,
                    validators=[MaxValueValidator(600)],
                )),
                ("timezone", models.CharField(default="Asia/Kolkata", max_length=64)),
                ("onboarding_completed", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="learner_profile",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ("display_name", "user__email")},
        ),
        migrations.AddIndex(
            model_name="learnerprofile",
            index=models.Index(
                fields=["preferred_language", "onboarding_completed"],
                name="learners_lear_prefere_6a7c8f_idx",
            ),
        ),
    ]
