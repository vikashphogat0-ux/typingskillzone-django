from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from exams.models import ExamConfiguration
from passages.models import PassageSource
from passages.services import publish_source_to_exam

from .models import TypingSession
from .services import activate_session, expire_session, start_session, submit_session
from .mistake_classification import classify_typing_mistakes

class TypingSessionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.learner = User.objects.create_user(email="personal@example.com", password="SafePassword123!")
        self.other = User.objects.create_user(email="institute@example.com", password="SafePassword123!")
        self.exam = ExamConfiguration.objects.create(
            code="sample-exam", name="Sample Exam", language="ENGLISH", script="LATIN",
            duration_seconds=600, allow_backspace=False,
        )
        self.source = PassageSource.objects.create(
            title="Sample", content="One.\n\nTwo.", language="ENGLISH",
            script="LATIN", status=PassageSource.Status.PUBLISHED,
        )
        self.publication = publish_source_to_exam(self.source, self.exam)

    def test_start_snapshots_text_and_exam_rules(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        self.assertEqual(attempt.state, TypingSession.State.ACTIVE)
        self.assertEqual(attempt.reference_text, self.publication.rendered_content)
        self.assertEqual(attempt.rules_snapshot["allow_backspace"], False)
        self.assertEqual(attempt.duration_seconds, 600)
        self.assertIsNone(attempt.deadline_at)


    def test_exam_clock_starts_on_first_input_activation(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        original_started_at = attempt.started_at
        self.assertIsNone(attempt.deadline_at)
        activated = activate_session(session_id=attempt.pk, learner=self.learner)
        self.assertIsNotNone(activated.deadline_at)
        self.assertGreaterEqual(activated.started_at, original_started_at)
        self.assertEqual(
            activated.deadline_at,
            activated.started_at + timedelta(seconds=600),
        )
        self.assertTrue(activated.rules_snapshot["timer_started"])

    def test_selected_exam_start_saves_and_locks_display_mode(self):
        self.client.force_login(self.learner)
        response = self.client.post(
            reverse("typing_sessions:start_selected", args=[self.exam.code]),
            {"passage_id": str(self.publication.serial_number), "display_mode": "highlighted"},
        )
        self.assertEqual(response.status_code, 302)
        attempt = TypingSession.objects.get(learner=self.learner, publication=self.publication)
        self.assertEqual(attempt.rules_snapshot["display_mode"], "highlighted")

        self.client.post(
            reverse("typing_sessions:start_selected", args=[self.exam.code]),
            {"passage_id": str(self.publication.serial_number), "display_mode": "offscreen"},
        )
        attempt.refresh_from_db()
        self.assertEqual(attempt.rules_snapshot["display_mode"], "highlighted")

    def test_timer_activation_endpoint_starts_server_deadline(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        self.client.force_login(self.learner)
        response = self.client.post(reverse("typing_sessions:activate", args=[attempt.pk]))
        self.assertEqual(response.status_code, 200)
        attempt.refresh_from_db()
        self.assertIsNotNone(attempt.deadline_at)
        self.assertTrue(attempt.rules_snapshot["timer_started"])

    def test_exam_configuration_edits_do_not_change_started_specification_snapshot(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        original_snapshot = attempt.rules_snapshot

        self.exam.name = "Changed after session start"
        self.exam.minimum_wpm = "35.00"
        self.exam.passage_layout = ExamConfiguration.PassageLayout.CONTINUOUS
        self.exam.save()

        attempt.refresh_from_db()
        self.assertEqual(attempt.rules_snapshot, original_snapshot)
        self.assertEqual(
            attempt.rules_snapshot["canonical_specification"]["identity"]["name"],
            "Sample Exam",
        )
        self.assertIsNone(
            attempt.rules_snapshot["canonical_specification"]["scoring"]["minimum_wpm"]
        )


    def test_source_edits_do_not_change_started_attempt(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        original = attempt.reference_text
        self.source.content = "Replaced later"
        self.source.save()
        attempt.refresh_from_db()
        self.assertEqual(attempt.reference_text, original)

    def test_submission_is_single_use(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        result = submit_session(session_id=attempt.pk, learner=self.learner, typed_text="One.")
        self.assertEqual(result.state, TypingSession.State.SUBMITTED)
        self.assertEqual(result.submitted_text, "One.")
        with self.assertRaises(ValidationError):
            submit_session(session_id=attempt.pk, learner=self.learner, typed_text="Overwrite")

    def test_other_learner_cannot_submit(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        with self.assertRaises(TypingSession.DoesNotExist):
            submit_session(session_id=attempt.pk, learner=self.other, typed_text="No")
        attempt.refresh_from_db()
        self.assertEqual(attempt.state, TypingSession.State.ACTIVE)

    def test_expired_attempt_is_not_marked_as_on_time(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        TypingSession.objects.filter(pk=attempt.pk).update(deadline_at=timezone.now() - timedelta(seconds=1))
        result = submit_session(session_id=attempt.pk, learner=self.learner, typed_text="Late")
        self.assertEqual(result.state, TypingSession.State.EXPIRED)

    def test_expire_requires_deadline(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        with self.assertRaises(ValidationError):
            expire_session(session_id=attempt.pk, learner=self.learner)

    def test_archived_passage_cannot_start(self):
        self.publication.status = "ARCHIVED"
        self.publication.save(update_fields=("status",))
        with self.assertRaises(ValidationError):
            start_session(learner=self.learner, publication=self.publication)

    def test_unauthenticated_start_is_denied(self):
        with self.assertRaises(PermissionDenied):
            start_session(learner=None, publication=self.publication)

    def test_inactive_student_cannot_start_typing_sessions(self):
        self.learner.is_active = False
        self.learner.save(update_fields=("is_active",))
        with self.assertRaises(PermissionDenied):
            start_session(learner=self.learner, publication=self.publication)
        self.assertFalse(
            TypingSession.objects.filter(learner=self.learner, publication=self.publication).exists()
        )

    def test_non_student_roles_cannot_start_typing_sessions(self):
        User = get_user_model()
        for role in (User.Roles.INSTITUTE_OWNER, User.Roles.INSTITUTE_STAFF, User.Roles.ADMIN, User.Roles.SUPER_ADMIN):
            with self.subTest(role=role):
                account = User.objects.create_user(
                    email=f"blocked-{role.lower()}@example.test",
                    password="SafePassword123!",
                    role=role,
                )
                with self.assertRaises(PermissionDenied):
                    start_session(learner=account, publication=self.publication)

    def test_non_student_roles_cannot_submit_or_expire_typing_sessions(self):
        User = get_user_model()
        attempt = start_session(learner=self.learner, publication=self.publication)
        owner = User.objects.create_user(
            email="blocked-owner-submit@example.test",
            password="SafePassword123!",
            role=User.Roles.INSTITUTE_OWNER,
        )
        with self.assertRaises(PermissionDenied):
            submit_session(session_id=attempt.pk, learner=owner, typed_text="One.")
        with self.assertRaises(PermissionDenied):
            expire_session(session_id=attempt.pk, learner=owner)
        attempt.refresh_from_db()
        self.assertEqual(attempt.state, TypingSession.State.ACTIVE)


    def test_unverified_exam_does_not_claim_scoring(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        self.assertEqual(attempt.rules_snapshot["verification_status"], "UNVERIFIED")
        self.assertEqual(attempt.result_snapshot, {})
        self.assertEqual(attempt.scoring_version, "")


class TypingScoringTests(TestCase):
    def test_untyped_trailing_passage_words_are_pending_not_errors(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="one two three",
            typed="one",
            duration_seconds=60,
            rules={
                "scoring_mode": "GENERIC",
                "error_rules": {"count_word_errors": True},
                "verification_status": "UNVERIFIED",
            },
        )
        self.assertEqual(result["word_errors"], 0)
        self.assertEqual(result["character_errors"], 0)
        self.assertEqual(result["deletion_errors"], 0)
        self.assertEqual(result["accuracy_percent"], 100.0)

        analysis = classify_typing_mistakes("one two three", "one")
        self.assertEqual(analysis["total_detected_errors"], 0)

        attempted_error = calculate_result(
            reference="one two three",
            typed="one wrong",
            duration_seconds=60,
            rules={
                "scoring_mode": "GENERIC",
                "error_rules": {"count_word_errors": True},
                "verification_status": "UNVERIFIED",
            },
        )
        self.assertEqual(attempted_error["word_errors"], 1)
        self.assertEqual(attempted_error["error_count"], 1)
        self.assertEqual(
            classify_typing_mistakes("one two three", "one wrong")["total_detected_errors"],
            1,
        )

    def setUp(self):
        User = get_user_model()
        self.learner = User.objects.create_user(email="scoring@example.com", password="SafePassword123!")
        self.exam = ExamConfiguration.objects.create(
            code="scoring-exam", name="Scoring Exam", language="ENGLISH", script="LATIN",
            duration_seconds=600, allow_backspace=True,
        )
        self.source = PassageSource.objects.create(
            title="Scoring sample", content="hello world", language="ENGLISH",
            script="LATIN", status=PassageSource.Status.PUBLISHED,
        )
        self.publication = publish_source_to_exam(self.source, self.exam)
    def test_stroke_net_wpm_uses_classified_mistakes(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="hello world",
            typed="hello word",
            duration_seconds=60,
            reported_keystrokes=300,
            rules={
                "scoring_mode": "CUSTOM",
                "strokes_per_word": 5,
                "verification_status": "UNVERIFIED",
                "error_rules": {"count_word_errors": True},
                "scoring_rules": {
                    "formula": "STROKE_NET_WPM",
                    "mistake_penalty_wpm": 1,
                    "score_bands": [
                        [30, 10],
                        [40, 15],
                        [50, 21],
                    ],
                },
            },
        )

        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["mistake_categories"]["substitution"], 1)
        self.assertEqual(result["mistake_categories"]["omission"], 0)
        self.assertEqual(result["tentative_wpm"], 60.0)
        self.assertEqual(result["net_wpm"], 59.0)
        self.assertIsNone(result["qualification"])
    def test_character_level_substitution_insertion_and_deletion(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="abcd", typed="abXd", duration_seconds=60, rules={}
        )
        self.assertEqual(result["correct_characters"], 3)
        self.assertEqual(result["substitution_errors"], 1)
        self.assertEqual(result["character_errors"], 1)
        self.assertEqual(result["accuracy_percent"], 75.0)

    def test_word_error_mode_counts_a_misspelled_word_once(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="the quick brown fox",
            typed="the quik brown fox",
            duration_seconds=60,
            rules={"error_rules": {"count_word_errors": True}},
        )
        self.assertEqual(result["word_errors"], 1)
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["error_count_method"], "word")

    def test_reported_keystrokes_are_measured_without_claiming_trusted_input(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="hello world", typed="hello world", duration_seconds=60,
            rules={"required_keystrokes": 1000}, reported_keystrokes=1025,
        )
        self.assertEqual(result["reported_keystrokes"], 1025)
        self.assertEqual(result["keystroke_count_source"], "client_reported")
        self.assertTrue(result["required_keystrokes_met"])
        self.assertIsNone(result["qualification"])

    def test_reported_keystrokes_are_saved_with_session_result(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        result = submit_session(
            session_id=attempt.pk, learner=self.learner,
            typed_text=attempt.reference_text, reported_keystrokes=37,
        )
        self.assertEqual(result.result_snapshot["reported_keystrokes"], 37)
        self.assertEqual(result.result_snapshot["keystroke_count_source"], "client_reported")

    def test_unverified_exam_never_receives_qualification_claim(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="hello world", typed="hello world", duration_seconds=60,
            rules={"verification_status": "UNVERIFIED"},
        )
        self.assertIsNone(result["qualification"])
        self.assertIn("not verified", result["qualification_note"])

    def test_completed_session_persists_server_score(self):
        attempt = start_session(
            learner=self.learner,
            publication=self.publication,
        )

        result = submit_session(
            session_id=attempt.pk,
            learner=self.learner,
            typed_text=attempt.reference_text,
            reported_keystrokes=300,
        )

        result.refresh_from_db()

        self.assertEqual(result.scoring_version, "tsz-char-word-v2")
        self.assertEqual(result.result_snapshot["accuracy_percent"], 100.0)
        self.assertEqual(result.result_snapshot["character_errors"], 0)

        self.assertIn("mistake_analysis", result.result_snapshot)
        self.assertIn("mistake_categories", result.result_snapshot)

        self.assertIsNone(result.result_snapshot["mistake_categories"])
        self.assertIsNone(result.result_snapshot["mistake_analysis"])

    def test_stroke_net_wpm_uses_total_strokes_and_word_mistakes(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="one two three",
            typed="one too three",
            duration_seconds=600,
            reported_keystrokes=3000,
            rules={
                "scoring_mode": "CUSTOM",
                "error_rules": {"count_word_errors": True},
                "strokes_per_word": 5,
                "scoring_rules": {
                    "formula": "STROKE_NET_WPM",
                    "mistake_penalty_wpm": 1,
                    "score_bands": [
                        [30, 10], [31, 12], [36, 15],
                        [41, 18], [46, 21], [51, 25],
                    ],
                },
            },
        )

        self.assertEqual(result["word_errors"], 1)
        self.assertEqual(result["tentative_wpm"], 60)
        self.assertEqual(result["net_wpm"], 59)
        self.assertEqual(result["score"], 25)
        self.assertEqual(result["stroke_count_source"], "client_reported")

    def test_stroke_net_wpm_uses_fallback_when_keystrokes_missing(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="hello world",
            typed="hello world",
            duration_seconds=60,
            rules={
                "scoring_mode": "CUSTOM",
                "error_rules": {"count_word_errors": True},
                "strokes_per_word": 5,
                "scoring_rules": {
                    "formula": "STROKE_NET_WPM",
                    "mistake_penalty_wpm": 1,
                    "score_bands": [[1, 10]],
                },
            },
        )

        self.assertEqual(result["stroke_count_for_speed"], len("hello world"))
        self.assertEqual(result["stroke_count_source"], "typed_character_fallback")
        self.assertIsNotNone(result["tentative_wpm"])

    def test_stroke_net_wpm_client_reported_inflates_practice_only(self):
        from .scoring import calculate_result

        # Unverified practice attempt: client-reported strokes are used as a
        # clearly-labelled provisional metric and may inflate practice marks.
        result = calculate_result(
            reference="hello world",
            typed="hello world",
            duration_seconds=60,
            reported_keystrokes=999999,
            rules={
                "scoring_mode": "CUSTOM",
                "error_rules": {"count_word_errors": True},
                "strokes_per_word": 5,
                "verification_status": "UNVERIFIED",
                "scoring_rules": {
                    "formula": "STROKE_NET_WPM",
                    "mistake_penalty_wpm": 1,
                    "score_bands": [[1, 10]],
                },
            },
        )
        self.assertEqual(result["stroke_count_source"], "client_reported")
        self.assertEqual(result["stroke_count_for_speed"], 999999)
        self.assertEqual(result["score"], 10)

    def test_stroke_net_wpm_negative_keystrokes_clamped_to_zero(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="hello world",
            typed="hello world",
            duration_seconds=60,
            reported_keystrokes=-500,
            rules={
                "scoring_mode": "CUSTOM",
                "error_rules": {"count_word_errors": True},
                "strokes_per_word": 5,
                "verification_status": "UNVERIFIED",
                "scoring_rules": {
                    "formula": "STROKE_NET_WPM",
                    "mistake_penalty_wpm": 1,
                    "score_bands": [[1, 10]],
                },
            },
        )
        self.assertEqual(result["stroke_count_source"], "client_reported")
        self.assertEqual(result["stroke_count_for_speed"], 0)
        self.assertEqual(result["tentative_wpm"], 0)

    def test_stroke_net_wpm_excessive_keystrokes_clamped(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="hello world",
            typed="hello world",
            duration_seconds=60,
            reported_keystrokes=99999999,
            rules={
                "scoring_mode": "CUSTOM",
                "error_rules": {"count_word_errors": True},
                "strokes_per_word": 5,
                "verification_status": "UNVERIFIED",
                "scoring_rules": {
                    "formula": "STROKE_NET_WPM",
                    "mistake_penalty_wpm": 1,
                    "score_bands": [[1, 10]],
                },
            },
        )
        self.assertEqual(result["stroke_count_for_speed"], 1000000)

    def test_verified_required_keystroke_threshold_never_trusts_client_count(self):
        from .scoring import calculate_result

        rules = {
            "verification_status": "VERIFIED",
            "required_keystrokes": 100,
        }
        inflated = calculate_result(
            reference="hello world",
            typed="hello world",
            duration_seconds=60,
            reported_keystrokes=100000,
            rules=rules,
        )
        underreported = calculate_result(
            reference="hello world",
            typed="hello world",
            duration_seconds=60,
            reported_keystrokes=1,
            rules=rules,
        )
        self.assertIsNone(inflated["required_keystrokes_met"])
        self.assertIsNone(underreported["required_keystrokes_met"])

    def test_stroke_net_wpm_verified_rules_use_server_derived_strokes(self):
        from .scoring import calculate_result

        # Verified/exam attempt: manipulated client keystrokes must NOT
        # influence speed, marks or qualification.
        result = calculate_result(
            reference="hello world",
            typed="hello world",
            duration_seconds=60,
            reported_keystrokes=999999,
            rules={
                "scoring_mode": "CUSTOM",
                "error_rules": {"count_word_errors": True},
                "strokes_per_word": 5,
                "verification_status": "VERIFIED",
                "scoring_rules": {
                    "formula": "STROKE_NET_WPM",
                    "mistake_penalty_wpm": 1,
                    "score_bands": [[1, 10]],
                },
            },
        )
        self.assertEqual(result["stroke_count_source"], "server_derived")
        self.assertEqual(result["stroke_count_for_speed"], len("hello world"))
        self.assertEqual(result["tentative_wpm"], 2.2)
        self.assertEqual(result["net_wpm"], 2.2)
        self.assertEqual(result["score"], 10)

    def test_stroke_net_wpm_verified_inconsistent_keystrokes_cannot_inflate_score(self):
        from .scoring import calculate_result

        base = {
            "scoring_mode": "CUSTOM",
            "error_rules": {"count_word_errors": True},
            "strokes_per_word": 5,
            "verification_status": "VERIFIED",
            "scoring_rules": {
                "formula": "STROKE_NET_WPM",
                "mistake_penalty_wpm": 1,
                "score_bands": [[40, 25]],
            },
        }
        inflated = calculate_result(
            reference="hello world",
            typed="hello world",
            duration_seconds=60,
            reported_keystrokes=1000000,
            rules=base,
        )
        honest = calculate_result(
            reference="hello world",
            typed="hello world",
            duration_seconds=60,
            reported_keystrokes=1,
            rules=base,
        )
        # Client telemetry is ignored for verified rules: identical results.
        self.assertEqual(inflated["stroke_count_source"], "server_derived")
        self.assertEqual(honest["stroke_count_source"], "server_derived")
        self.assertEqual(inflated["net_wpm"], honest["net_wpm"])
        self.assertEqual(inflated["score"], honest["score"])
    def test_verified_qualification_rules_evaluate_all_and_any_conditions(self):
        from .scoring import calculate_result
        result = calculate_result(
            reference="one two three four five", typed="one two three four five",
            duration_seconds=60, rules={
                "verification_status": "VERIFIED",
                "qualification_rules": {
                    "all": [{"metric": "net_wpm", "operator": "gte", "value": 4}],
                    "any": [{"metric": "accuracy_percent", "operator": "gte", "value": 99}],
                },
            },
        )
        self.assertTrue(result["qualification"])
        self.assertEqual(result["qualification_status"], "QUALIFIED")

    def test_verified_qualification_failure_is_explicit(self):
        from .scoring import calculate_result
        result = calculate_result(
            reference="one two three four five", typed="one",
            duration_seconds=60, rules={
                "verification_status": "VERIFIED",
                "qualification_rules": {
                    "all": [{"metric": "net_wpm", "operator": "gte", "value": 30}],
                },
            },
        )
        self.assertFalse(result["qualification"])
        self.assertEqual(result["qualification_status"], "NOT_QUALIFIED")

    def test_unverified_or_unsupported_qualification_stays_pending(self):
        from .scoring import calculate_result
        config = {"all": [{"metric": "physical_keystrokes", "operator": "gte", "value": 1000}]}
        unverified = calculate_result(
            reference="one two", typed="one two", duration_seconds=60,
            rules={"verification_status": "UNVERIFIED", "qualification_rules": config},
        )
        unsupported = calculate_result(
            reference="one two", typed="one two", duration_seconds=60,
            rules={"verification_status": "VERIFIED", "qualification_rules": config},
        )
        self.assertEqual(unverified["qualification_status"], "PENDING")
        self.assertEqual(unsupported["qualification_status"], "PENDING")
        self.assertIsNone(unsupported["qualification"])


class TypingSessionViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.learner = User.objects.create_user(email="view@example.com", password="SafePassword123!")
        self.exam = ExamConfiguration.objects.create(
            code="view-exam", name="View Exam", language="ENGLISH", script="LATIN",
            duration_seconds=600,
        )
        self.source = PassageSource.objects.create(
            title="View sample", content="sample text", language="ENGLISH",
            script="LATIN", status=PassageSource.Status.PUBLISHED,
        )
        self.publication = publish_source_to_exam(self.source, self.exam)


    def test_independent_student_can_start_typing_test_without_institute_membership(self):
        from django.urls import reverse

        self.client.force_login(self.learner)
        response = self.client.post(
            reverse("typing_sessions:start", kwargs={
                "exam_code": self.exam.code,
                "passage_id": self.publication.passage_id,
            })
        )

        self.assertEqual(response.status_code, 302)
        attempt = TypingSession.objects.get(learner=self.learner, publication=self.publication)
        self.assertRedirects(
            response,
            reverse("typing_sessions:session", kwargs={"session_id": attempt.pk}),
            fetch_redirect_response=False,
        )
        self.assertEqual(attempt.state, TypingSession.State.ACTIVE)
        self.assertEqual(attempt.reference_text, self.publication.rendered_content)

    def test_start_view_returns_403_for_non_student_role(self):
        from django.urls import reverse

        owner = get_user_model().objects.create_user(
            email="view-owner@example.test",
            password="SafePassword123!",
            role=get_user_model().Roles.INSTITUTE_OWNER,
        )
        self.client.force_login(owner)
        response = self.client.post(
            reverse("typing_sessions:start", kwargs={
                "exam_code": self.exam.code,
                "passage_id": self.publication.passage_id,
            })
        )
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "An active student account is required.", status_code=403)

    def test_start_view_returns_conflict_not_forbidden_for_unreleased_passage(self):
        from datetime import timedelta
        from django.urls import reverse

        self.publication.release_date = timezone.localdate() + timedelta(days=1)
        self.publication.release_slot = "MORNING"
        self.publication.release_position = 1
        self.publication.save()
        self.client.force_login(self.learner)
        response = self.client.post(
            reverse("typing_sessions:start", kwargs={
                "exam_code": self.exam.code,
                "passage_id": self.publication.passage_id,
            })
        )
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "This passage is not released yet.", status_code=409)

    def test_opening_expired_attempt_marks_it_expired(self):
        from django.urls import reverse

        attempt = start_session(learner=self.learner, publication=self.publication)
        TypingSession.objects.filter(pk=attempt.pk).update(
            deadline_at=timezone.now() - timedelta(seconds=1)
        )
        self.client.force_login(self.learner)
        response = self.client.get(
            reverse("typing_sessions:session", kwargs={"session_id": attempt.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "typing_sessions/result.html")
        attempt.refresh_from_db()
        self.assertEqual(attempt.state, TypingSession.State.EXPIRED)
        self.assertEqual(attempt.result_snapshot, {})
class TypingMistakeClassificationTests(TestCase):
    def test_mistake_categories(self):
        cases = [
            ("Omission", "hello world", "hello", "omission"),
            ("Substitution", "hello world", "hello word", "substitution"),
            ("Addition", "hello world", "hello x world", "addition"),
            ("Capitalization", "Hello world", "hello world", "capitalization"),
            ("Punctuation", "Hello, world.", "Hello world.", "punctuation"),
            ("Internal spacing", "hello world", "hel lo world", "internal_spacing"),
            ("Word spacing", "hello world", "hello  world", "word_spacing"),
            ("Paragraph break", "hello\nworld", "hello world", "paragraph_breaks"),
            ("Hindi substitution", "भारत महान है", "भारत विशाल है", "substitution"),
            ("Hindi omission", "भारत महान है", "भारत है", "omission"),
            ("Hindi addition", "भारत महान है", "भारत बहुत महान है", "addition"),
            ("Hindi spacing", "भारत महान है", "भा रत महान है", "internal_spacing"),
            ("Hindi punctuation", "भारत महान है।", "भारत महान है", "punctuation"),
            (
                "Missing paragraph break",
                "First paragraph.\n\nSecond paragraph.",
                "First paragraph. Second paragraph.",
                "paragraph_breaks",
            ),
            (
                "Extra paragraph break",
                "First paragraph. Second paragraph.",
                "First paragraph.\n\nSecond paragraph.",
                "paragraph_breaks",
            ),
        ]

        for name, reference, typed, expected_category in cases:
            with self.subTest(case=name):
                result = classify_typing_mistakes(reference, typed)
                self.assertEqual(result["categories"][expected_category], 1)
                self.assertEqual(result["total_detected_errors"], 1)