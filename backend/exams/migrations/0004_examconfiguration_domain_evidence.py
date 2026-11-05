from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("exams", "0003_editable_typing_engine_rules")]

    operations = [
        migrations.AddField(
            model_name="examconfiguration",
            name="domain_evidence",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Independent evidence by specification domain. VERIFIED requires source, exact locator, checked date, and supported claims.",
            ),
        ),
    ]
