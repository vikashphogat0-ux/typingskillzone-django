from django.test import TestCase
from django.urls import reverse


class CatalogueRedirectTests(TestCase):
    def test_old_simulator_catalogue_redirects_to_exam_catalogue(self):
        response = self.client.get(reverse("passages:simulator-catalogue"))
        self.assertRedirects(response, reverse("exams:catalogue"), fetch_redirect_response=False)
