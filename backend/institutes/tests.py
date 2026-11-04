from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse

from .forms import InstituteRegistrationForm
from .models import Institute, InstituteMembership, InstituteSubscription, SubscriptionPlan

User = get_user_model()


class InstituteRegistrationViewTests(TestCase):
    def registration_data(self, **overrides):
        data = {
            "name": "Example Typing Academy",
            "email": "academy@example.test",
            "phone": "9876543210",
            "address": "Test Road",
            "city": "Panipat",
            "state": "Haryana",
            "postal_code": "132103",
            "owner_name": "Example Owner",
            "owner_email": "owner@example.test",
            "owner_phone": "9876543211",
            "password": "A-Strong-Test-Password-2026!",
            "confirm_password": "A-Strong-Test-Password-2026!",
        }
        data.update(overrides)
        return data

    def test_registration_page_renders(self):
        response = self.client.get(reverse("institutes:register"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "institutes/register.html")
        self.assertIsInstance(response.context["form"], InstituteRegistrationForm)

    def test_valid_registration_creates_pending_institute_and_owner(self):
        response = self.client.post(reverse("institutes:register"), self.registration_data())
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "institutes/registration_success.html")
        owner = User.objects.get(email="owner@example.test")
        institute = Institute.objects.get(name="Example Typing Academy")
        self.assertEqual(owner.role, User.Roles.INSTITUTE_OWNER)
        self.assertTrue(owner.check_password("A-Strong-Test-Password-2026!"))
        self.assertEqual(institute.owner, owner)
        self.assertEqual(institute.status, Institute.Status.PENDING)
        self.assertEqual(len(institute.registration_code), 36)
        self.assertIsNone(institute.approved_by)
        self.assertIsNone(institute.approved_at)

    def test_mismatched_passwords_do_not_create_records(self):
        data = self.registration_data(confirm_password="Different-Test-Password-2026!")
        response = self.client.post(reverse("institutes:register"), data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Institute.objects.count(), 0)

    def test_existing_owner_email_is_rejected(self):
        User.objects.create_user(email="owner@example.test", password="Existing-Strong-Password-2026!")
        response = self.client.post(reverse("institutes:register"), self.registration_data())
        self.assertEqual(response.status_code, 200)
        self.assertIn("owner_email", response.context["form"].errors)
        self.assertEqual(Institute.objects.count(), 0)
        self.assertEqual(User.objects.count(), 1)

    def test_authenticated_user_is_redirected_to_admin(self):
        admin_user = User.objects.create_superuser(email="admin@example.test", password="Admin-Strong-Password-2026!")
        self.client.force_login(admin_user)
        response = self.client.get(reverse("institutes:register"))
        self.assertRedirects(response, reverse("admin:index"))
        self.assertEqual(Institute.objects.count(), 0)


class InstituteOwnerVerificationTests(TestCase):
    def registration_data(self):
        return {
            "name": "Owner Verification Academy",
            "email": "academy-verify@example.test",
            "phone": "9876543210",
            "address": "Test Road",
            "city": "Panipat",
            "state": "Haryana",
            "postal_code": "132103",
            "owner_name": "Owner Verify",
            "owner_email": "owner-verify@example.test",
            "owner_phone": "9876543211",
            "password": "A-Strong-Test-Password-2026!",
            "confirm_password": "A-Strong-Test-Password-2026!",
        }

    def test_registration_sends_verification_and_owner_is_inactive(self):
        response = self.client.post(reverse("institutes:register"), self.registration_data())
        self.assertEqual(response.status_code, 200)
        owner = User.objects.get(email="owner-verify@example.test")
        self.assertFalse(owner.is_active)
        self.assertFalse(owner.is_email_verified)
        self.assertIsNotNone(owner.email_verification_sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/owner/verify/", mail.outbox[0].body)

    def test_owner_verification_requires_post_and_token_cannot_be_replayed(self):
        self.client.post(reverse("institutes:register"), self.registration_data())
        owner = User.objects.get(email="owner-verify@example.test")
        verify_line = next(line for line in mail.outbox[0].body.splitlines() if "/owner/verify/" in line)
        token = verify_line.rsplit("/owner/verify/", 1)[1].strip().rstrip("/")
        url = reverse("institutes:verify_owner_email", kwargs={"token": token})
        preview = self.client.get(url)
        self.assertEqual(preview.status_code, 200)
        owner.refresh_from_db()
        self.assertFalse(owner.is_active)
        verified = self.client.post(url)
        self.assertEqual(verified.status_code, 200)
        owner.refresh_from_db()
        self.assertTrue(owner.is_active)
        self.assertTrue(owner.is_email_verified)
        self.assertIsNone(owner.email_verification_sent_at)
        self.assertEqual(self.client.post(url).status_code, 400)

    def test_owner_login_rejects_unverified_owner(self):
        owner = User.objects.create_user(
            email="unverified-owner@example.test",
            password="Owner-Strong-Password-2026!",
            role=User.Roles.INSTITUTE_OWNER,
            is_active=True,
            is_email_verified=False,
        )
        response = self.client.post(reverse("institutes:owner_login"), {
            "username": owner.email,
            "password": "Owner-Strong-Password-2026!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)


class SuperAdminDashboardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="superadmin@example.test",
            password="Admin-Strong-Password-2026!",
        )
        self.owner = User.objects.create_user(
            email="owner@example.test",
            password="Owner-Strong-Password-2026!",
            role=User.Roles.INSTITUTE_OWNER,
        )
        self.institute = Institute.objects.create(
            name="Dashboard Test Academy",
            owner=self.owner,
            email="academy@example.test",
            phone="9876543210",
            city="Panipat",
            state="Haryana",
        )

    def test_super_admin_can_open_dashboard(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("institutes:super_admin_dashboard")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard Test Academy")
        self.assertEqual(response.context["pending_institutes"], 1)

    def test_non_super_admin_is_redirected_to_admin_login(self):
        student = User.objects.create_user(
            email="student@example.test",
            password="Student-Strong-Password-2026!",
        )
        self.client.force_login(student)
        response = self.client.get(
            reverse("institutes:super_admin_dashboard")
        )
        self.assertRedirects(
            response,
            "/admin/login/?next=/institutes/dashboard/super-admin/",
        )

    def test_super_admin_can_approve_pending_institute(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse(
                "institutes:review_institute",
                args=[self.institute.pk, "approve"],
            )
        )
        self.assertRedirects(
            response,
            reverse(
                "institutes:institute_detail",
                args=[self.institute.pk],
            ),
        )
        self.institute.refresh_from_db()
        self.assertEqual(self.institute.status, Institute.Status.APPROVED)
        self.assertEqual(self.institute.approved_by, self.admin)
        self.assertIsNotNone(self.institute.approved_at)

    def test_approval_action_rejects_get_requests(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse(
                "institutes:review_institute",
                args=[self.institute.pk, "approve"],
            )
        )
        self.assertEqual(response.status_code, 405)
        self.institute.refresh_from_db()
        self.assertEqual(self.institute.status, Institute.Status.PENDING)

    def test_admin_bulk_approval_starts_seven_day_free_trial(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            "/admin/institutes/institute/",
            {
                "action": "approve_selected",
                "index": "0",
                "_selected_action": [str(self.institute.pk)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.institute.refresh_from_db()
        self.assertEqual(self.institute.status, Institute.Status.APPROVED)
        subscription = InstituteSubscription.objects.select_related("plan").get(
            institute=self.institute
        )
        self.assertEqual(subscription.plan.code, "free-trial")
        self.assertEqual(subscription.status, InstituteSubscription.Status.ACTIVE)
        self.assertEqual(subscription.plan.max_students, 25)
        self.assertEqual(subscription.plan.max_staff, 2)
        self.assertGreater(subscription.ends_at, timezone.now())
        self.assertLessEqual(
            subscription.ends_at - subscription.starts_at,
            timedelta(days=7),
        )

    def test_admin_bulk_approval_preserves_existing_paid_subscription(self):
        paid_plan = SubscriptionPlan.objects.create(
            name="Paid Admin Action Plan",
            code="paid-admin-action",
            duration_days=30,
            price=Decimal("999.00"),
            max_students=100,
            max_staff=10,
        )
        paid_subscription = InstituteSubscription.objects.create(
            institute=self.institute,
            plan=paid_plan,
            status=InstituteSubscription.Status.ACTIVE,
            starts_at=timezone.now() - timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=29),
            amount_paid=Decimal("999.00"),
            payment_reference="PAID-KEEP-THIS",
        )
        self.client.force_login(self.admin)
        response = self.client.post(
            "/admin/institutes/institute/",
            {
                "action": "approve_selected",
                "index": "0",
                "_selected_action": [str(self.institute.pk)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        paid_subscription.refresh_from_db()
        self.assertEqual(paid_subscription.plan, paid_plan)
        self.assertEqual(paid_subscription.amount_paid, Decimal("999.00"))
        self.assertEqual(paid_subscription.payment_reference, "PAID-KEEP-THIS")
        self.assertEqual(
            InstituteSubscription.objects.filter(institute=self.institute).count(),
            1,
        )

class InstituteManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email='manager@example.test', password='Admin-Strong-Password-2026!')
        self.owner = User.objects.create_user(email='academy-owner@example.test', password='Owner-Strong-Password-2026!', role=User.Roles.INSTITUTE_OWNER)
        self.institute = Institute.objects.create(name='Management Test Academy', owner=self.owner, email='academy@example.test', phone='9876543210', city='Panipat', state='Haryana')
        self.client.force_login(self.admin)

    def test_directory_lists_and_searches_institutes(self):
        response = self.client.get(reverse('institutes:institute_list'), {'q': 'Management'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Management Test Academy')

    def test_directory_filters_by_status(self):
        response = self.client.get(reverse('institutes:institute_list'), {'status': Institute.Status.PENDING})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Management Test Academy')

    def test_profile_and_edit_page_open(self):
        detail = self.client.get(reverse('institutes:institute_detail', args=[self.institute.pk]))
        edit = self.client.get(reverse('institutes:institute_edit', args=[self.institute.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(edit.status_code, 200)

    def test_admin_can_edit_institute_contact_details(self):
        response = self.client.post(reverse('institutes:institute_edit', args=[self.institute.pk]), {'name': 'Updated Management Academy', 'email': 'updated@example.test', 'phone': '9999999999', 'address': 'New Road', 'city': 'Karnal', 'state': 'Haryana', 'postal_code': '132001'})
        self.assertRedirects(response, reverse('institutes:institute_detail', args=[self.institute.pk]))
        self.institute.refresh_from_db()
        self.assertEqual(self.institute.name, 'Updated Management Academy')
        self.assertEqual(self.institute.city, 'Karnal')

    def test_suspended_institute_can_be_reactivated(self):
        self.institute.status = Institute.Status.SUSPENDED
        self.institute.save(update_fields=['status', 'updated_at'])
        response = self.client.post(reverse('institutes:review_institute', args=[self.institute.pk, 'reactivate']))
        self.assertRedirects(response, reverse('institutes:institute_detail', args=[self.institute.pk]))
        self.institute.refresh_from_db()
        self.assertEqual(self.institute.status, Institute.Status.APPROVED)

    def test_student_cannot_open_institute_directory(self):
        student = User.objects.create_user(email='directory-student@example.test', password='Student-Strong-Password-2026!')
        self.client.force_login(student)
        response = self.client.get(reverse('institutes:institute_list'))
        self.assertEqual(response.status_code, 302)


class InstituteOwnerPortalTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="portal-owner@example.test",
            password="Owner-Strong-Password-2026!",
            first_name="Portal Owner",
            role=User.Roles.INSTITUTE_OWNER,
        )
        self.admin = User.objects.create_superuser(
            email="portal-admin@example.test",
            password="Admin-Strong-Password-2026!",
        )
        self.institute = Institute.objects.create(
            name="Approved Owner Academy",
            owner=self.owner,
            email="approved@example.test",
            phone="9876543210",
            status=Institute.Status.APPROVED,
            approved_by=self.admin,
        )

    def test_owner_login_page_renders(self):
        response = self.client.get(reverse("institutes:owner_login"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "institutes/owner_login.html")

    def test_approved_owner_can_login_and_open_dashboard(self):
        response = self.client.post(
            reverse("institutes:owner_login"),
            {"username": self.owner.email, "password": "Owner-Strong-Password-2026!"},
        )
        self.assertRedirects(response, reverse("institutes:owner_dashboard"))
        dashboard = self.client.get(reverse("institutes:owner_dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Approved Owner Academy")

    def test_pending_owner_is_blocked_from_dashboard(self):
        self.institute.status = Institute.Status.PENDING
        self.institute.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.owner)
        response = self.client.get(reverse("institutes:owner_dashboard"))
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "institutes/owner_access_status.html")
        self.assertContains(response, "Application under review", status_code=403)

    def test_suspended_owner_is_blocked_from_dashboard(self):
        self.institute.status = Institute.Status.SUSPENDED
        self.institute.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.owner)
        response = self.client.get(reverse("institutes:owner_dashboard"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Institute access suspended", status_code=403)

    def test_rejected_owner_is_blocked_from_dashboard(self):
        self.institute.status = Institute.Status.REJECTED
        self.institute.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.owner)
        response = self.client.get(reverse("institutes:owner_dashboard"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Application not approved", status_code=403)

    def test_student_cannot_login_through_owner_portal(self):
        student = User.objects.create_user(
            email="portal-student@example.test",
            password="Student-Strong-Password-2026!",
            role=User.Roles.STUDENT,
        )
        response = self.client.post(
            reverse("institutes:owner_login"),
            {"username": student.email, "password": "Student-Strong-Password-2026!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertTrue(response.context["form"].non_field_errors())

    def test_owner_dashboard_only_shows_owned_approved_institutes(self):
        other_owner = User.objects.create_user(
            email="other-owner@example.test",
            password="Other-Strong-Password-2026!",
            role=User.Roles.INSTITUTE_OWNER,
        )
        Institute.objects.create(
            name="Another Academy",
            owner=other_owner,
            email="another@example.test",
            phone="9876543211",
            status=Institute.Status.APPROVED,
            approved_by=self.admin,
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("institutes:owner_dashboard"))
        self.assertContains(response, "Approved Owner Academy")
        self.assertNotContains(response, "Another Academy")

    def test_owner_logout_requires_post(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("institutes:owner_logout"))
        self.assertEqual(response.status_code, 403)


class InstituteOwnerMemberManagementTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="members-owner@example.test",
            password="Owner-Strong-Password-2026!",
            role=User.Roles.INSTITUTE_OWNER,
        )
        self.other_owner = User.objects.create_user(
            email="members-other-owner@example.test",
            password="Other-Strong-Password-2026!",
            role=User.Roles.INSTITUTE_OWNER,
        )
        self.institute = Institute.objects.create(
            name="Member Management Academy",
            owner=self.owner,
            email="members-academy@example.test",
            phone="9876543210",
            status=Institute.Status.APPROVED,
        )
        plan = SubscriptionPlan.objects.create(
            name="Member Test Plan",
            code="member-test-plan",
            duration_days=30,
            price=Decimal("499.00"),
            max_students=25,
            max_staff=2,
        )
        InstituteSubscription.objects.create(
            institute=self.institute,
            plan=plan,
            starts_at=timezone.now() - timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=29),
        )
        self.other_institute = Institute.objects.create(
            name="Other Owner Academy",
            owner=self.other_owner,
            email="other-academy@example.test",
            phone="9876543211",
            status=Institute.Status.APPROVED,
        )
        self.student = User.objects.create_user(
            email="existing-student@example.test",
            password="Student-Strong-Password-2026!",
            role=User.Roles.STUDENT,
        )
        self.staff = User.objects.create_user(
            email="existing-staff@example.test",
            password="Staff-Strong-Password-2026!",
            role=User.Roles.INSTITUTE_STAFF,
        )
        self.client.force_login(self.owner)

    def test_owner_can_view_only_their_institute_members(self):
        own_member = InstituteMembership.objects.create(
            institute=self.institute, user=self.student,
            role=InstituteMembership.Role.STUDENT,
        )
        other_member = User.objects.create_user(
            email="other-institute-student@example.test",
            password="Student-Strong-Password-2026!",
            role=User.Roles.STUDENT,
        )
        InstituteMembership.objects.create(
            institute=self.other_institute, user=other_member,
            role=InstituteMembership.Role.STUDENT,
        )
        response = self.client.get(
            reverse("institutes:owner_member_list", args=[self.institute.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own_member.user.email)
        self.assertNotContains(response, other_member.email)

    def test_owner_can_add_existing_student(self):
        response = self.client.post(
            reverse("institutes:owner_member_add", args=[self.institute.pk]),
            {"email": self.student.email, "role": User.Roles.STUDENT},
        )
        self.assertRedirects(
            response,
            reverse("institutes:owner_member_list", args=[self.institute.pk]),
        )
        membership = InstituteMembership.objects.get(
            institute=self.institute, user=self.student
        )
        self.assertEqual(membership.role, InstituteMembership.Role.STUDENT)
        self.assertTrue(membership.is_active)

    def test_owner_can_add_existing_staff(self):
        response = self.client.post(
            reverse("institutes:owner_member_add", args=[self.institute.pk]),
            {"email": self.staff.email, "role": User.Roles.INSTITUTE_STAFF},
        )
        self.assertRedirects(
            response,
            reverse("institutes:owner_member_list", args=[self.institute.pk]),
        )
        membership = InstituteMembership.objects.get(
            institute=self.institute, user=self.staff
        )
        self.assertEqual(membership.role, InstituteMembership.Role.STAFF)

    def test_unknown_email_is_rejected_without_creating_membership(self):
        response = self.client.post(
            reverse("institutes:owner_member_add", args=[self.institute.pk]),
            {"email": "missing@example.test", "role": User.Roles.STUDENT},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        self.assertEqual(InstituteMembership.objects.count(), 0)

    def test_owner_and_admin_accounts_cannot_be_added_as_members(self):
        response = self.client.post(
            reverse("institutes:owner_member_add", args=[self.institute.pk]),
            {"email": self.other_owner.email, "role": User.Roles.INSTITUTE_OWNER},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("role", response.context["form"].errors)
        self.assertEqual(InstituteMembership.objects.count(), 0)

    def test_duplicate_membership_is_rejected(self):
        InstituteMembership.objects.create(
            institute=self.institute, user=self.student,
            role=InstituteMembership.Role.STUDENT,
        )
        response = self.client.post(
            reverse("institutes:owner_member_add", args=[self.institute.pk]),
            {"email": self.student.email, "role": User.Roles.STUDENT},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        self.assertEqual(InstituteMembership.objects.count(), 1)

    def test_owner_can_deactivate_and_reactivate_membership(self):
        membership = InstituteMembership.objects.create(
            institute=self.institute, user=self.student,
            role=InstituteMembership.Role.STUDENT,
        )
        deactivate = self.client.post(reverse(
            "institutes:owner_member_status",
            args=[self.institute.pk, membership.pk, "deactivate"],
        ))
        self.assertRedirects(
            deactivate,
            reverse("institutes:owner_member_list", args=[self.institute.pk]),
        )
        membership.refresh_from_db()
        self.assertFalse(membership.is_active)
        self.client.post(reverse(
            "institutes:owner_member_status",
            args=[self.institute.pk, membership.pk, "activate"],
        ))
        membership.refresh_from_db()
        self.assertTrue(membership.is_active)

    def test_owner_cannot_manage_another_owners_institute(self):
        response = self.client.get(
            reverse("institutes:owner_member_list", args=[self.other_institute.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_membership_status_change_rejects_get(self):
        membership = InstituteMembership.objects.create(
            institute=self.institute, user=self.student,
            role=InstituteMembership.Role.STUDENT,
        )
        response = self.client.get(reverse(
            "institutes:owner_member_status",
            args=[self.institute.pk, membership.pk, "deactivate"],
        ))
        self.assertEqual(response.status_code, 405)
        membership.refresh_from_db()
        self.assertTrue(membership.is_active)


    def test_selected_membership_type_must_match_account_role(self):
        response = self.client.post(
            reverse("institutes:owner_member_add", args=[self.institute.pk]),
            {"email": self.student.email, "role": User.Roles.INSTITUTE_STAFF},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        self.assertEqual(InstituteMembership.objects.count(), 0)


class StudentAndStaffPortalTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="portal-institute-owner@example.test",
            password="Owner-Strong-Password-2026!",
            role=User.Roles.INSTITUTE_OWNER,
        )
        self.admin = User.objects.create_superuser(
            email="portal-superadmin@example.test",
            password="Admin-Strong-Password-2026!",
        )
        self.approved_institute = Institute.objects.create(
            name="Portal Approved Academy",
            owner=self.owner,
            email="portal-academy@example.test",
            phone="9876543210",
            status=Institute.Status.APPROVED,
            approved_by=self.admin,
        )
        plan = SubscriptionPlan.objects.create(
            name="Portal Test Plan",
            code="portal-test-plan",
            duration_days=30,
            price=Decimal("499.00"),
            max_students=25,
            max_staff=2,
        )
        InstituteSubscription.objects.create(
            institute=self.approved_institute,
            plan=plan,
            starts_at=timezone.now() - timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=29),
        )
        self.student = User.objects.create_user(
            email="portal-member-student@example.test",
            password="Student-Strong-Password-2026!",
            role=User.Roles.STUDENT,
        )
        self.staff = User.objects.create_user(
            email="portal-member-staff@example.test",
            password="Staff-Strong-Password-2026!",
            role=User.Roles.INSTITUTE_STAFF,
        )
        self.student_membership = InstituteMembership.objects.create(
            institute=self.approved_institute,
            user=self.student,
            role=InstituteMembership.Role.STUDENT,
        )
        self.staff_membership = InstituteMembership.objects.create(
            institute=self.approved_institute,
            user=self.staff,
            role=InstituteMembership.Role.STAFF,
        )

    def test_student_can_login_and_view_active_approved_institute(self):
        response = self.client.post(
            reverse("institutes:student_login"),
            {"username": self.student.email, "password": "Student-Strong-Password-2026!"},
        )
        self.assertRedirects(response, reverse("institutes:student_dashboard"))
        dashboard = self.client.get(reverse("institutes:student_dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Portal Approved Academy")

    def test_staff_can_login_and_view_active_approved_institute(self):
        response = self.client.post(
            reverse("institutes:staff_login"),
            {"username": self.staff.email, "password": "Staff-Strong-Password-2026!"},
        )
        self.assertRedirects(response, reverse("institutes:staff_dashboard"))
        dashboard = self.client.get(reverse("institutes:staff_dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Portal Approved Academy")

    def test_student_cannot_login_through_staff_portal(self):
        response = self.client.post(
            reverse("institutes:staff_login"),
            {"username": self.student.email, "password": "Student-Strong-Password-2026!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_staff_cannot_login_through_student_portal(self):
        response = self.client.post(
            reverse("institutes:student_login"),
            {"username": self.staff.email, "password": "Staff-Strong-Password-2026!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_inactive_membership_blocks_student_dashboard(self):
        self.student_membership.is_active = False
        self.student_membership.save(update_fields=["is_active"])
        self.client.force_login(self.student)
        response = self.client.get(reverse("institutes:student_dashboard"))
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "institutes/member_access_status.html")

    def test_inactive_membership_blocks_staff_dashboard(self):
        self.staff_membership.is_active = False
        self.staff_membership.save(update_fields=["is_active"])
        self.client.force_login(self.staff)
        response = self.client.get(reverse("institutes:staff_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_membership_in_unapproved_institute_does_not_grant_student_access(self):
        self.approved_institute.status = Institute.Status.SUSPENDED
        self.approved_institute.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.student)
        response = self.client.get(reverse("institutes:student_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_student_dashboard_does_not_show_other_members_or_institutes(self):
        other_owner = User.objects.create_user(
            email="portal-other-owner@example.test",
            password="Other-Strong-Password-2026!",
            role=User.Roles.INSTITUTE_OWNER,
        )
        other_institute = Institute.objects.create(
            name="Private Other Academy",
            owner=other_owner,
            email="private-other@example.test",
            phone="9876543211",
            status=Institute.Status.APPROVED,
        )
        other_student = User.objects.create_user(
            email="portal-other-student@example.test",
            password="Student-Strong-Password-2026!",
            role=User.Roles.STUDENT,
        )
        InstituteMembership.objects.create(
            institute=other_institute,
            user=other_student,
            role=InstituteMembership.Role.STUDENT,
        )
        self.client.force_login(self.student)
        response = self.client.get(reverse("institutes:student_dashboard"))
        self.assertContains(response, "Portal Approved Academy")
        self.assertNotContains(response, "Private Other Academy")
        self.assertNotContains(response, other_student.email)

    def test_student_logout_requires_post(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("institutes:student_logout"))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_staff_logout_requires_post_and_post_logs_out(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("institutes:staff_logout"))
        self.assertEqual(response.status_code, 405)
        response = self.client.post(reverse("institutes:staff_logout"))
        self.assertRedirects(response, reverse("institutes:staff_login"))
        self.assertFalse(response.wsgi_request.user.is_authenticated)



class InstituteSubscriptionManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="subscription-admin@example.test",
            password="Admin-Strong-Password-2026!",
        )
        self.owner = User.objects.create_user(
            email="subscription-owner@example.test",
            password="Owner-Strong-Password-2026!",
            role=User.Roles.INSTITUTE_OWNER,
        )
        self.institute = Institute.objects.create(
            name="Subscription Academy",
            owner=self.owner,
            email="subscription-academy@example.test",
            phone="9876543210",
            status=Institute.Status.APPROVED,
        )
        self.plan = SubscriptionPlan.objects.create(
            name="Starter Monthly",
            code="starter-monthly",
            duration_days=30,
            price=Decimal("499.00"),
        )

    def test_super_admin_can_create_and_manage_subscription_in_admin(self):
        self.client.force_login(self.admin)
        response = self.client.get("/admin/institutes/institutesubscription/add/")
        self.assertEqual(response.status_code, 200)
        # Institute is an AJAX autocomplete, so its choices are loaded separately.
        self.assertContains(response, 'id="id_institute"')
        self.assertContains(response, 'data-model-name="institutesubscription"')
        self.assertContains(response, "Starter Monthly")

    def test_owner_dashboard_displays_assigned_plan_and_expiry(self):
        ends_at = timezone.now() + timedelta(days=20)
        InstituteSubscription.objects.create(
            institute=self.institute,
            plan=self.plan,
            starts_at=timezone.now(),
            ends_at=ends_at,
            amount_paid=Decimal("499.00"),
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("institutes:owner_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Starter Monthly")
        self.assertContains(response, "ACTIVE")
        self.assertContains(response, "Valid until")

    def test_owner_dashboard_explains_when_no_plan_is_assigned(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("institutes:owner_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Not assigned")
        self.assertContains(response, "Contact the platform administrator")

    def test_expired_subscription_is_not_reported_as_active(self):
        subscription = InstituteSubscription.objects.create(
            institute=self.institute,
            plan=self.plan,
            starts_at=timezone.now() - timedelta(days=40),
            ends_at=timezone.now() - timedelta(days=10),
        )
        self.assertFalse(subscription.is_currently_active)
        self.assertEqual(subscription.effective_status, InstituteSubscription.Status.EXPIRED)

    def test_suspended_subscription_is_not_active(self):
        subscription = InstituteSubscription.objects.create(
            institute=self.institute,
            plan=self.plan,
            starts_at=timezone.now() - timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=29),
            status=InstituteSubscription.Status.SUSPENDED,
        )
        self.assertFalse(subscription.is_currently_active)
        self.assertEqual(subscription.effective_status, InstituteSubscription.Status.SUSPENDED)

    def test_renewal_extends_from_existing_expiry_and_reactivates(self):
        old_expiry = timezone.now() + timedelta(days=5)
        subscription = InstituteSubscription.objects.create(
            institute=self.institute,
            plan=self.plan,
            starts_at=timezone.now() - timedelta(days=25),
            ends_at=old_expiry,
            status=InstituteSubscription.Status.SUSPENDED,
        )
        subscription.renew(amount_paid=Decimal("499.00"), payment_reference="MANUAL-RENEWAL-01")
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, InstituteSubscription.Status.ACTIVE)
        self.assertEqual(subscription.starts_at, old_expiry)
        self.assertEqual(subscription.ends_at, old_expiry + timedelta(days=30))
        self.assertEqual(subscription.amount_paid, Decimal("499.00"))
        self.assertEqual(subscription.payment_reference, "MANUAL-RENEWAL-01")

    def test_each_institute_can_have_only_one_subscription(self):
        InstituteSubscription.objects.create(
            institute=self.institute,
            plan=self.plan,
            ends_at=timezone.now() + timedelta(days=30),
        )
        with self.assertRaises(IntegrityError):
            InstituteSubscription.objects.create(
                institute=self.institute,
                plan=self.plan,
                ends_at=timezone.now() + timedelta(days=30),
            )


class InstituteTrialEnforcementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="trial-admin@example.test",
            password="Admin-Strong-Password-2026!",
        )
        self.owner = User.objects.create_user(
            email="trial-owner@example.test",
            password="Owner-Strong-Password-2026!",
            role=User.Roles.INSTITUTE_OWNER,
        )
        self.institute = Institute.objects.create(
            name="Newly Approved Trial Academy",
            owner=self.owner,
            email="trial-academy@example.test",
            phone="9876543210",
            status=Institute.Status.PENDING,
        )

    def test_approval_starts_seven_day_trial_with_defined_seat_limits(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("institutes:review_institute", args=[self.institute.pk, "approve"])
        )
        self.assertRedirects(response, reverse("institutes:institute_detail", args=[self.institute.pk]))
        subscription = InstituteSubscription.objects.select_related("plan").get(institute=self.institute)
        self.assertEqual(subscription.plan.code, "free-trial")
        self.assertEqual(subscription.plan.duration_days, 7)
        self.assertEqual(subscription.plan.max_students, 25)
        self.assertEqual(subscription.plan.max_staff, 2)
        self.assertEqual(subscription.amount_paid, Decimal("0.00"))
        self.assertLessEqual(subscription.ends_at - subscription.starts_at, timedelta(days=7))
        self.assertGreater(subscription.ends_at - subscription.starts_at, timedelta(days=6, hours=23))

    def test_expired_trial_blocks_student_and_staff_portal_access(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("institutes:review_institute", args=[self.institute.pk, "approve"]))
        subscription = InstituteSubscription.objects.get(institute=self.institute)
        subscription.ends_at = timezone.now() - timedelta(seconds=1)
        subscription.save(update_fields=["ends_at", "updated_at"])
        student = User.objects.create_user(
            email="trial-student@example.test",
            password="Student-Strong-Password-2026!",
            role=User.Roles.STUDENT,
        )
        InstituteMembership.objects.create(
            institute=self.institute, user=student, role=InstituteMembership.Role.STUDENT
        )
        self.client.force_login(student)
        response = self.client.get(reverse("institutes:student_dashboard"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "No active institute membership", status_code=403)

        staff = User.objects.create_user(
            email="trial-staff@example.test",
            password="Staff-Strong-Password-2026!",
            role=User.Roles.INSTITUTE_STAFF,
        )
        InstituteMembership.objects.create(
            institute=self.institute, user=staff, role=InstituteMembership.Role.STAFF
        )
        self.client.force_login(staff)
        staff_response = self.client.get(reverse("institutes:staff_dashboard"))
        self.assertEqual(staff_response.status_code, 403)
        self.assertContains(staff_response, "No active institute membership", status_code=403)

    def test_trial_seat_limit_prevents_adding_extra_student(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("institutes:review_institute", args=[self.institute.pk, "approve"]))
        student_users = [
            User.objects.create_user(
                email=f"trial-seat-{index}@example.test",
                password="Student-Strong-Password-2026!",
                role=User.Roles.STUDENT,
            )
            for index in range(25)
        ]
        InstituteMembership.objects.bulk_create([
            InstituteMembership(
                institute=self.institute,
                user=user,
                role=InstituteMembership.Role.STUDENT,
                is_active=True,
            )
            for user in student_users
        ])
        extra_student = User.objects.create_user(
            email="trial-extra-student@example.test",
            password="Student-Strong-Password-2026!",
            role=User.Roles.STUDENT,
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("institutes:owner_member_add", args=[self.institute.pk]),
            {"email": extra_student.email, "role": User.Roles.STUDENT},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "seat limit")
        self.assertFalse(InstituteMembership.objects.filter(institute=self.institute, user=extra_student).exists())

    def test_expired_subscription_prevents_owner_from_adding_members(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("institutes:review_institute", args=[self.institute.pk, "approve"]))
        subscription = InstituteSubscription.objects.get(institute=self.institute)
        subscription.ends_at = timezone.now() - timedelta(seconds=1)
        subscription.save(update_fields=["ends_at", "updated_at"])
        student = User.objects.create_user(
            email="expired-trial-student@example.test",
            password="Student-Strong-Password-2026!",
            role=User.Roles.STUDENT,
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("institutes:owner_member_add", args=[self.institute.pk]),
            {"email": student.email, "role": User.Roles.STUDENT},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "subscription has expired")
        self.assertFalse(InstituteMembership.objects.filter(institute=self.institute, user=student).exists())


class SuperAdminAdminPermissionTests(TestCase):
    def setUp(self):
        self.staff_admin = User.objects.create_user(
            email="limited-admin@example.test",
            password="Staff-Admin-Strong-Password-2026!",
            role=User.Roles.ADMIN,
            is_staff=True,
        )
        # Deliberately grant every app-level permission: access must still be
        # denied unless the account is the designated platform Super Admin.
        permissions = Permission.objects.filter(
            content_type__app_label__in=["accounts", "institutes"]
        )
        self.staff_admin.user_permissions.add(*permissions)

        self.super_admin = User.objects.create_superuser(
            email="permission-superadmin@example.test",
            password="Super-Admin-Strong-Password-2026!",
        )

    def test_staff_admin_with_model_permissions_cannot_access_sensitive_admin_models(self):
        self.client.force_login(self.staff_admin)
        admin_urls = [
            "/admin/accounts/user/",
            "/admin/institutes/institute/",
            "/admin/institutes/institutemembership/",
            "/admin/institutes/subscriptionplan/",
            "/admin/institutes/institutesubscription/",
        ]
        for url in admin_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 403)

    def test_superuser_with_wrong_platform_role_cannot_access_sensitive_admin_models(self):
        incorrectly_labelled_superuser = User.objects.create_superuser(
            email="wrong-role-superuser@example.test",
            password="Wrong-Role-Strong-Password-2026!",
        )
        incorrectly_labelled_superuser.role = User.Roles.ADMIN
        incorrectly_labelled_superuser.save(update_fields=["role"])
        self.client.force_login(incorrectly_labelled_superuser)
        response = self.client.get("/admin/institutes/institute/")
        self.assertEqual(response.status_code, 403)

    def test_designated_super_admin_can_access_sensitive_admin_models(self):
        self.client.force_login(self.super_admin)
        for url in [
            "/admin/accounts/user/",
            "/admin/institutes/institute/",
            "/admin/institutes/institutemembership/",
            "/admin/institutes/subscriptionplan/",
            "/admin/institutes/institutesubscription/",
        ]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
