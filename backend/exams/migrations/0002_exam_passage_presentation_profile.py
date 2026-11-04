from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("exams", "0001_initial"),
    ]

    operations = [
        migrations.AddField("examconfiguration", "passage_layout", models.CharField(choices=[("UNCONFIGURED", "Pending format verification"), ("CONTINUOUS", "Continuous text"), ("PARAGRAPHS", "Paragraphs"), ("PARA_TAB", "Paragraph and tab matter"), ("TCS", "TCS-style presentation"), ("CUSTOM", "Custom layout")], default="UNCONFIGURED", max_length=20)),
        migrations.AddField("examconfiguration", "passage_font_family", models.CharField(default="Arial", max_length=80)),
        migrations.AddField("examconfiguration", "passage_font_size_pt", models.PositiveSmallIntegerField(default=12)),
        migrations.AddField("examconfiguration", "passage_line_height", models.DecimalField(decimal_places=2, default=1.6, max_digits=3)),
        migrations.AddField("examconfiguration", "passage_paragraph_spacing_pt", models.PositiveSmallIntegerField(default=12)),
        migrations.AddField("examconfiguration", "passage_alignment", models.CharField(choices=[("left", "Left"), ("justify", "Justify"), ("center", "Center")], default="left", max_length=10)),
        migrations.AddField("examconfiguration", "passage_first_line_indent_em", models.DecimalField(decimal_places=1, default=0, max_digits=3)),
        migrations.AddField("examconfiguration", "passage_preserve_tabs", models.BooleanField(default=False)),
        migrations.AddField("examconfiguration", "passage_tab_size", models.PositiveSmallIntegerField(default=4)),
        migrations.AddField("examconfiguration", "presentation_reference_status", models.CharField(choices=[("PENDING", "Pending reference check"), ("REVIEWED", "Reference reviewed (practice source)"), ("VERIFIED", "Verified against authoritative presentation source")], db_index=True, default="PENDING", max_length=12)),
        migrations.AddField("examconfiguration", "presentation_reference_url", models.URLField(blank=True)),
        migrations.AddField("examconfiguration", "presentation_reference_title", models.CharField(blank=True, max_length=240)),
        migrations.AddField("examconfiguration", "presentation_reference_checked_at", models.DateField(blank=True, null=True)),
        migrations.AddField("examconfiguration", "presentation_notes", models.TextField(blank=True)),
        migrations.AddIndex("examconfiguration", models.Index(fields=["passage_layout", "presentation_reference_status"], name="exam_passage_layout_idx")),
    ]
