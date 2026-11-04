# Generated for the centralized passage source and simulator publication domain.
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("exams", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PassageSource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=240)),
                ("content", models.TextField()),
                ("language", models.CharField(db_index=True, default="ENGLISH", max_length=20)),
                ("script", models.CharField(blank=True, max_length=40)),
                ("source_reference", models.CharField(blank=True, max_length=500)),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("PUBLISHED", "Published"), ("ARCHIVED", "Archived")], db_index=True, default="DRAFT", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_passage_sources", to=settings.AUTH_USER_MODEL)),
                ("target_exams", models.ManyToManyField(blank=True, help_text="Select every simulator that should receive this source passage.", related_name="central_passage_sources", to="exams.examconfiguration")),
            ],
            options={"ordering": ("-created_at", "title")},
        ),
        migrations.CreateModel(
            name="ExamPassageSequence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("next_number", models.PositiveBigIntegerField(default=1)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("exam", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="passage_sequence", to="exams.examconfiguration")),
            ],
        ),
        migrations.CreateModel(
            name="SimulatorPassage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("serial_number", models.PositiveBigIntegerField()),
                ("status", models.CharField(choices=[("PUBLISHED", "Published"), ("ARCHIVED", "Archived")], db_index=True, default="PUBLISHED", max_length=12)),
                ("published_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("exam", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="published_passages", to="exams.examconfiguration")),
                ("source", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="simulator_publications", to="passages.passagesource")),
            ],
            options={"ordering": ("exam", "serial_number")},
        ),
        migrations.AddIndex(
            model_name="passagesource",
            index=models.Index(fields=["status", "language"], name="passage_src_status_lang_idx"),
        ),
        migrations.AddConstraint(
            model_name="simulatorpassage",
            constraint=models.UniqueConstraint(fields=("exam", "serial_number"), name="uniq_exam_passage_serial"),
        ),
        migrations.AddConstraint(
            model_name="simulatorpassage",
            constraint=models.UniqueConstraint(fields=("exam", "source"), name="uniq_exam_source_publication"),
        ),
        migrations.AddIndex(
            model_name="simulatorpassage",
            index=models.Index(fields=["exam", "status", "serial_number"], name="passage_exam_status_num_idx"),
        ),
    ]
