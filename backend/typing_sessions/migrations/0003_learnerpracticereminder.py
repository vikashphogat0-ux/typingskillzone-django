import datetime

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("typing_sessions", "0002_learnerpracticegoal"),
    ]

    operations = [
        migrations.CreateModel(
            name="LearnerPracticeReminder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(default=False)),
                ("reminder_time", models.TimeField(default=datetime.time(18, 0))),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("learner", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="typing_practice_reminder", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
