from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def create_trial_plan_and_grant_existing_approved(apps, schema_editor):
    Institute = apps.get_model("institutes", "Institute")
    SubscriptionPlan = apps.get_model("institutes", "SubscriptionPlan")
    InstituteSubscription = apps.get_model("institutes", "InstituteSubscription")
    now = timezone.now()

    plan, _ = SubscriptionPlan.objects.using(schema_editor.connection.alias).get_or_create(
        code="free-trial",
        defaults={
            "name": "7-Day Free Trial",
            "description": "Seven-day institute trial with 25 student seats and 2 staff seats.",
            "duration_days": 7,
            "price": 0,
            "currency": "INR",
            "max_students": 25,
            "max_staff": 2,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
    )

    approved = Institute.objects.using(schema_editor.connection.alias).filter(
        status="APPROVED"
    ).exclude(subscription__isnull=False)

    for institute in approved.iterator():
        InstituteSubscription.objects.using(schema_editor.connection.alias).create(
            institute=institute,
            plan=plan,
            status="ACTIVE",
            starts_at=now,
            ends_at=now + timedelta(days=7),
            amount_paid=0,
            created_at=now,
            updated_at=now,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("institutes", "0003_merge_20261103_1400"),
    ]

    operations = [
        migrations.RunPython(
            create_trial_plan_and_grant_existing_approved,
            migrations.RunPython.noop,
        ),
    ]
