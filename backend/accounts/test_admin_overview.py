from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AdminOverviewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(email="overview-admin@example.com", password="AdminStrong123!")

    def test_overview_requires_admin_login(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 302)

    def test_overview_shows_branded_cards_and_counts(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "TypingSkillZone")
        self.assertContains(response, "Pending institutes")
        self.assertContains(response, "Published passages")
        self.assertContains(response, "tsz_admin.css")

    def test_stats_are_numbers(self):
        from accounts.admin import tsz_admin_stats
        stats = tsz_admin_stats()
        self.assertEqual(len(stats), 6)
        self.assertTrue(all(isinstance(card["value"], int) for card in stats))
