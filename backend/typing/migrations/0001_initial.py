import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("passages", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TypingSession",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("state", models.CharField(choices=[("ACTIVE", "Active"), ("SUBMITTED", "Submitted"), ("EXPIRED", "Expired")], db_index=True, default="ACTIVE", max_length=12)),
                ("started_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("deadline_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("duration_seconds", models.PositiveIntegerField(blank=True, null=True)),
                ("reference_text", models.TextField()),
                ("submitted_text", models.TextField(blank=True)),
                ("rules_snapshot", models.JSONField(default=dict)),
                ("scoring_version", models.CharField(blank=True, max_length=32)),
                ("result_snapshot", models.JSONField(default=dict)),
                ("learner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="typing_sessions", to=settings.AUTH_USER_MODEL)),
                ("publication", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="typing_sessions", to="passages.simulatorpassage")),
            ],
            options={"ordering": ("-started_at",)},
        ),
        migrations.AddIndex(
            model_name="typingsession",
            index=models.Index(fields=["learner", "state", "started_at"], name="typing_user_state_idx"),
        ),
    ]
