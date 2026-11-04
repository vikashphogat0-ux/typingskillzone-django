from django.db import migrations


def mark_existing_active_owners_verified(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(
        role="INSTITUTE_OWNER",
        is_active=True,
        is_email_verified=False,
    ).update(is_email_verified=True)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_email_verification_sent_at"),
    ]

    operations = [
        migrations.RunPython(
            mark_existing_active_owners_verified,
            migrations.RunPython.noop,
        ),
    ]
