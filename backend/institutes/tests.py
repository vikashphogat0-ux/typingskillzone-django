from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import InstituteRegistrationForm
from .models import Institute

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


class SuperAdminDashboardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="superadmin@example.test", password="Admin-Strong-Password-2026!")
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
        response = self.client.get(reverse("institutes:super_admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard Test Academy")
        self.assertEqual(response.context["pending_institutes"], 1)

    def test_non_super_admin_is_redirected_to_admin_login(self):
        student = User.objects.create_user(email="student@example.test", password="Student-Strong-Password-2026!")
        self.client.force_login(student)
        response = self.client.get(reverse("institutes:super_admin_dashboard"))
        self.assertRedirects(response, "/admin/login/?next=/institutes/dashboard/super-admin/")

    def test_super_admin_can_approve_pending_institute(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("institutes:review_institute", args=[self.institute.pk, "approve"]))
        self.assertRedirects(response, reverse("institutes:super_admin_dashboard"))
        self.institute.refresh_from_db()
        self.assertEqual(self.institute.status, Institute.Status.APPROVED)
        self.assertEqual(self.institute.approved_by, self.admin)
        self.assertIsNotNone(self.institute.approved_at)

    def test_approval_action_rejects_get_requests(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("institutes:review_institute", args=[self.institute.pk, "approve"]))
        self.assertEqual(response.status_code, 405)
        self.institute.refresh_from_db()
        self.assertEqual(self.institute.status, Institute.Status.PENDING)


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
