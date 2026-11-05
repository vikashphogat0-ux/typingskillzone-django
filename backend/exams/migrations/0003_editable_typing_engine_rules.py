from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("exams", "0002_exam_passage_presentation_profile")]

    operations = [
        migrations.AddField("examconfiguration", "backspace_policy", models.CharField(
            choices=[("FULL", "Unrestricted Backspace"), ("DISABLED", "Backspace disabled"),
                     ("WORD_ONLY", "Current word only"),
                     ("WORD_LOCK_AFTER_SEPARATOR", "Lock word after Space/Enter"),
                     ("NOT_SPECIFIED", "Not specified (practice default: unrestricted)"),
                     ("PROVISIONAL_WORD_ONLY", "Provisional current-word restriction")],
            default="NOT_SPECIFIED", max_length=32)),
        migrations.AddField("examconfiguration", "allow_delete", models.BooleanField(default=True)),
        migrations.AddField("examconfiguration", "allow_paste", models.BooleanField(default=True)),
        migrations.AddField("examconfiguration", "allow_copy", models.BooleanField(default=True)),
        migrations.AddField("examconfiguration", "allow_cut", models.BooleanField(default=True)),
        migrations.AddField("examconfiguration", "enter_behavior", models.CharField(
            choices=[("NEW_LINE", "Insert new line"), ("COMMIT_WORD", "Commit current word"),
                     ("DISABLED", "Disabled"), ("UNSPECIFIED", "Not specified")],
            default="UNSPECIFIED", max_length=16)),
        migrations.AddField("examconfiguration", "space_behavior", models.CharField(
            choices=[("NORMAL", "Normal space"), ("COMMIT_WORD", "Commit/lock current word"),
                     ("DISABLED", "Disabled"), ("UNSPECIFIED", "Not specified")],
            default="UNSPECIFIED", max_length=16)),
        migrations.AddField("examconfiguration", "tab_behavior", models.CharField(
            choices=[("INSERT_TAB", "Insert tab"), ("INSERT_SPACES", "Insert configured spaces"),
                     ("DISABLED", "Disabled"), ("UNSPECIFIED", "Not specified")],
            default="UNSPECIFIED", max_length=16)),
        migrations.AddField("examconfiguration", "keyboard_layout", models.CharField(blank=True, max_length=80)),
        migrations.AddField("examconfiguration", "text_encoding", models.CharField(blank=True, max_length=24)),
        migrations.AddField("examconfiguration", "passage_source_mode", models.CharField(
            choices=[("SCREEN", "On-screen passage"), ("PRINTED", "Printed passage reference"),
                     ("MANUSCRIPT", "Hard-copy manuscript"), ("CONTINUOUS", "Continuous text"),
                     ("KEY_DEPRESSION", "Key-depression test"), ("TRANSCRIPTION", "Audio/shorthand transcription"),
                     ("UNSPECIFIED", "Not specified")],
            default="UNSPECIFIED", max_length=20)),
        migrations.AddField("examconfiguration", "minimum_wpm", models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
        migrations.AddField("examconfiguration", "required_keystrokes", models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField("examconfiguration", "strokes_per_word", models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField("examconfiguration", "error_allowance_percent", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
        migrations.AddField("examconfiguration", "mistake_penalty_strokes", models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField("examconfiguration", "trial_seconds", models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField("examconfiguration", "review_seconds", models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField("examconfiguration", "correction_seconds", models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField("examconfiguration", "transcription_seconds", models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField("examconfiguration", "allow_passage_repeat", models.BooleanField(default=False)),
        migrations.AddField("examconfiguration", "rule_config_version", models.PositiveSmallIntegerField(default=1)),
        migrations.AddField("examconfiguration", "scoring_mode", models.CharField(
            choices=[("GENERIC", "Generic character/word metrics"), ("CORRECT_WORDS", "Correct words only"),
                     ("NET_WPM", "Net WPM / key-depression formula"), ("ERROR_PERCENTAGE", "Error percentage allowance"),
                     ("STROKE_PENALTY", "Stroke-based mistake penalty"),
                     ("FULL_HALF_MISTAKES", "Full and half mistakes"),
                     ("CORRECT_WORD_MARKS", "Marks per correct word"),
                     ("QUALIFYING_ONLY", "Qualifying only"), ("CUSTOM", "Custom JSON scoring rules")],
            default="GENERIC", max_length=24)),
    ]
