# Generated for institute subscription management.
import decimal
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("institutes", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SubscriptionPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("code", models.SlugField(max_length=40, unique=True)),
                ("description", models.TextField(blank=True)),
                ("duration_days", models.PositiveIntegerField(default=30)),
                ("price", models.DecimalField(decimal_places=2, default=decimal.Decimal("0.00"), max_digits=10)),
                ("currency", models.CharField(default="INR", max_length=3)),
                ("max_students", models.PositiveIntegerField(blank=True, null=True)),
                ("max_staff", models.PositiveIntegerField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["price", "name"]},
        ),
        migrations.CreateModel(
            name="InstituteSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("ACTIVE", "Active"), ("EXPIRED", "Expired"), ("SUSPENDED", "Suspended"), ("CANCELLED", "Cancelled")], db_index=True, default="ACTIVE", max_length=12)),
                ("starts_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("ends_at", models.DateTimeField()),
                ("amount_paid", models.DecimalField(decimal_places=2, default=decimal.Decimal("0.00"), max_digits=10)),
                ("payment_reference", models.CharField(blank=True, max_length=120)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_institute_subscriptions", to=settings.AUTH_USER_MODEL)),
                ("institute", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="subscription", to="institutes.institute")),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subscriptions", to="institutes.subscriptionplan")),
            ],
            options={"ordering": ["-ends_at"]},
        ),
    ]
