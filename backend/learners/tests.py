from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from .models import LearnerProfile


class LearnerProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="learner@example.com",
            password="SafeTestPassword123!",
        )

    def test_profile_belongs_to_shared_user_identity(self):
        profile = LearnerProfile.objects.create(user=self.user)
        self.assertEqual(self.user.learner_profile, profile)
        self.assertEqual(profile.preferred_language, LearnerProfile.Language.ENGLISH)

    def test_profile_is_optional_for_existing_and_institute_accounts(self):
        self.assertFalse(LearnerProfile.objects.filter(user=self.user).exists())

    def test_learning_targets_have_safe_defaults(self):
        profile = LearnerProfile.objects.create(user=self.user)
        self.assertEqual(profile.target_wpm, 40)
        self.assertEqual(profile.target_accuracy, Decimal("95.00"))
        self.assertEqual(profile.daily_practice_goal_minutes, 30)

    def test_target_validation_rejects_out_of_range_values(self):
        profile = LearnerProfile(user=self.user, target_wpm=0)
        with self.assertRaises(ValidationError):
            profile.full_clean()

        profile = LearnerProfile(user=self.user, target_accuracy=Decimal("101"))
        with self.assertRaises(ValidationError):
            profile.full_clean()
