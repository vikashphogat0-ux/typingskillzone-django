from django.test import TestCase
from django.urls import reverse


class HomepageAndLoginRedirectTests(TestCase):
    def test_homepage_is_public_and_links_to_each_portal(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("institutes:student_login"))
        self.assertContains(response, reverse("institutes:owner_login"))
        self.assertContains(response, reverse("institutes:staff_login"))

    def test_anonymous_student_dashboard_redirects_to_student_login(self):
        response = self.client.get(reverse("accounts:student_dashboard"))
        self.assertRedirects(
            response,
            f"{reverse('accounts:student_login')}?next={reverse('accounts:student_dashboard')}",
            fetch_redirect_response=False,
        )

    def test_anonymous_owner_dashboard_redirects_to_owner_login(self):
        response = self.client.get(reverse("institutes:owner_dashboard"))
        self.assertTrue(response.url.startswith("/institutes/owner/login/"), response.url)

    def test_anonymous_super_admin_dashboard_redirects_to_admin_login(self):
        response = self.client.get(reverse("institutes:super_admin_dashboard"))
        self.assertTrue(response.url.startswith("/admin/login/"), response.url)
