from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("typing_sessions", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="LearnerPracticeGoal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("profile_code", models.CharField(default="DELHI_POLICE_HCM_2025", max_length=64)),
                ("target_net_wpm", models.PositiveSmallIntegerField(default=30)),
                ("target_accuracy", models.PositiveSmallIntegerField(default=95)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("learner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="typing_practice_goals", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("learner", "profile_code"), name="unique_learner_practice_goal")
                ]
            },
        ),
    ]
