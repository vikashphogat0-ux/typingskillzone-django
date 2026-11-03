
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q


class Institute(models.Model):

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Approval"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        SUSPENDED = "SUSPENDED", "Suspended"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(max_length=200)
    registration_code = models.CharField(
        max_length=36,
        unique=True,
        default=uuid.uuid4,
        editable=False,
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_institutes",
        limit_choices_to={"role": "INSTITUTE_OWNER"},
    )

    email = models.EmailField()
    phone = models.CharField(max_length=20)

    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=12, blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_institutes",
    )

    approved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["city", "state"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.registration_code})"


class InstituteMembership(models.Model):

    class Role(models.TextChoices):
        STAFF = "STAFF", "Institute Staff"
        STUDENT = "STUDENT", "Student"

    institute = models.ForeignKey(
        Institute,
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="institute_memberships",
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
    )

    is_active = models.BooleanField(default=True)

    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-joined_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["institute", "user"],
                name="unique_institute_membership",
            ),
            models.CheckConstraint(
                condition=Q(role__in=["STAFF", "STUDENT"]),
                name="valid_institute_membership_role",
            ),
        ]

        indexes = [
            models.Index(fields=["institute", "role", "is_active"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.institute.name}"


from decimal import Decimal
from django.utils import timezone


class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=40, unique=True)
    description = models.TextField(blank=True)
    duration_days = models.PositiveIntegerField(default=30)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="INR")
    max_students = models.PositiveIntegerField(null=True, blank=True)
    max_staff = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["price", "name"]

    def __str__(self):
        return f"{self.name} ({self.currency} {self.price})"


class InstituteSubscription(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        EXPIRED = "EXPIRED", "Expired"
        SUSPENDED = "SUSPENDED", "Suspended"
        CANCELLED = "CANCELLED", "Cancelled"

    institute = models.OneToOneField(Institute, on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField()
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    payment_reference = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_institute_subscriptions")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-ends_at"]

    def __str__(self):
        return f"{self.institute.name} — {self.plan.name}"

    @property
    def is_currently_active(self):
        now = timezone.now()
        return self.status == self.Status.ACTIVE and self.starts_at <= now < self.ends_at

    @property
    def effective_status(self):
        if self.status == self.Status.ACTIVE and self.ends_at <= timezone.now():
            return self.Status.EXPIRED
        return self.status

    def renew(self, *, start_at=None, amount_paid=None, payment_reference=None):
        start_at = start_at or max(timezone.now(), self.ends_at)
        self.starts_at = start_at
        self.ends_at = start_at + timedelta(days=self.plan.duration_days)
        self.status = self.Status.ACTIVE
        if amount_paid is not None:
            self.amount_paid = amount_paid
        if payment_reference is not None:
            self.payment_reference = payment_reference
        self.save(update_fields=["starts_at", "ends_at", "status", "amount_paid", "payment_reference", "updated_at"])
