from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone

from .models import Institute, InstituteMembership, InstituteSubscription, SubscriptionPlan
from .views import create_membership_within_limits

User = get_user_model()


class MembershipForm:
    def __init__(self, institute_id, user_id):
        self.institute_id = institute_id
        self.user_id = user_id

    def save(self):
        return InstituteMembership.objects.create(
            institute_id=self.institute_id,
            user_id=self.user_id,
            role=InstituteMembership.Role.STUDENT,
            is_active=True,
        )


@skipUnlessDBFeature("has_select_for_update")
class ConcurrentSeatLimitTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        owner = User.objects.create_user(
            email="concurrent-owner@example.test",
            password="Owner-Strong-Password-2026!",
            role=User.Roles.INSTITUTE_OWNER,
            is_email_verified=True,
        )
        self.institute = Institute.objects.create(
            name="Concurrent Seat Academy",
            owner=owner,
            email="concurrent-academy@example.test",
            phone="9876543210",
            status=Institute.Status.APPROVED,
        )
        plan = SubscriptionPlan.objects.create(
            name="One Seat Plan", code="one-seat-concurrency", duration_days=30,
            price=0, max_students=1, max_staff=1,
        )
        now = timezone.now()
        InstituteSubscription.objects.create(
            institute=self.institute, plan=plan,
            status=InstituteSubscription.Status.ACTIVE,
            starts_at=now - timedelta(minutes=1),
            ends_at=now + timedelta(days=30), amount_paid=0,
        )
        self.students = [
            User.objects.create_user(
                email=f"concurrent-student-{i}@example.test",
                password="Student-Strong-Password-2026!",
                role=User.Roles.STUDENT,
            ) for i in range(2)
        ]

    def _attempt_add(self, user_id, barrier):
        close_old_connections()
        try:
            institute = Institute.objects.get(pk=self.institute.pk)
            form = MembershipForm(institute.pk, user_id)
            barrier.wait(timeout=10)
            try:
                create_membership_within_limits(
                    institute, form, InstituteMembership.Role.STUDENT
                )
                return "created"
            except ValidationError:
                return "full"
        finally:
            connections.close_all()

    def test_two_simultaneous_requests_cannot_overbook_last_seat(self):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(
                lambda user: self._attempt_add(user.pk, barrier), self.students
            ))
        self.assertCountEqual(outcomes, ["created", "full"])
        self.assertEqual(
            InstituteMembership.objects.filter(
                institute=self.institute,
                role=InstituteMembership.Role.STUDENT,
                is_active=True,
            ).count(),
            1,
        )
