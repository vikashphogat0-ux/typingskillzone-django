from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("passages", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="simulatorpassage",
            name="release_date",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="simulatorpassage",
            name="release_slot",
            field=models.CharField(
                blank=True,
                choices=[
                    ("MORNING", "Morning (07:00)"),
                    ("AFTERNOON", "Afternoon (13:00)"),
                    ("EVENING", "Evening special (19:00)"),
                ],
                default="",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="simulatorpassage",
            name="release_position",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="simulatorpassage",
            constraint=models.UniqueConstraint(
                condition=models.Q(("release_date__isnull", False)),
                fields=("exam", "release_date", "release_slot", "release_position"),
                name="uniq_exam_release_slot_position",
            ),
        ),
    ]
