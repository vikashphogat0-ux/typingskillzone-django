# Generated for the central exam configuration catalogue.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="ExamConfiguration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=180, unique=True)),
                ("name", models.CharField(max_length=240)),
                ("category", models.CharField(choices=[("SSC","SSC"),("COURT","High Courts & Judiciary"),("RAILWAY","Railways"),("POLICE","Police & CAPF"),("STATE","State Government"),("UNIVERSITY","Universities & Education"),("CENTRAL","Central Government"),("PSU","PSU & Other Recruitments"),("PRACTICE","Practice & Speed Booster"),("OTHER","Other")], db_index=True, default="OTHER", max_length=20)),
                ("language", models.CharField(default="ENGLISH", max_length=20)),
                ("script", models.CharField(blank=True, max_length=40)),
                ("interface_type", models.CharField(blank=True, max_length=40)),
                ("duration_seconds", models.PositiveIntegerField(blank=True, null=True)),
                ("passage_format", models.CharField(choices=[("CONTINUOUS","Continuous paragraph"),("PARAGRAPHS","Paragraphs"),("TCS","TCS-style interface"),("CUSTOM","Custom / exam-specific")], default="CUSTOM", max_length=20)),
                ("passage_word_limit", models.PositiveIntegerField(blank=True, null=True)),
                ("allow_backspace", models.BooleanField(default=True)),
                ("allow_arrow_navigation", models.BooleanField(default=True)),
                ("error_rules", models.JSONField(blank=True, default=dict)),
                ("scoring_rules", models.JSONField(blank=True, default=dict)),
                ("qualification_rules", models.JSONField(blank=True, default=dict)),
                ("verification_status", models.CharField(choices=[("UNVERIFIED","Unverified"),("PARTIAL","Partially verified"),("VERIFIED","Verified")], db_index=True, default="UNVERIFIED", max_length=12)),
                ("official_source_url", models.URLField(blank=True)),
                ("source_title", models.CharField(blank=True, max_length=240)),
                ("source_checked_at", models.DateField(blank=True, null=True)),
                ("rule_notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("display_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("category", "display_order", "name")},
        ),
        migrations.AddIndex(model_name="examconfiguration", index=models.Index(fields=["category","is_active"], name="exams_exam_categor_2c4b13_idx")),
        migrations.AddIndex(model_name="examconfiguration", index=models.Index(fields=["verification_status","is_active"], name="exams_exam_verifi_12a4ab_idx")),
    ]
