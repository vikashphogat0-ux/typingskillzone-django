
import uuid

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
