from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from exams.models import ExamConfiguration
from passages.models import PassageSource
from passages.services import publish_source_to_exam

from .models import TypingSession
from .services import expire_session, start_session, submit_session


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
        input_policy = attempt.rules_snapshot["input_policy"]
        self.assertEqual(input_policy["backspace"]["policy"], self.exam.backspace_policy)
        self.assertFalse(input_policy["delete"])
        self.assertEqual(input_policy["enter_behavior"], self.exam.enter_behavior)
        self.assertEqual(input_policy["tab_behavior"], self.exam.tab_behavior)
        canonical = attempt.rules_snapshot["canonical_specification"]
        self.assertEqual(canonical["identity"]["code"], self.exam.code)
        self.assertEqual(canonical["identity"]["name"], self.exam.name)
        self.assertEqual(canonical["specification_schema_version"], 1)
        self.assertEqual(attempt.rules_snapshot["snapshot_metadata"]["format_version"], 1)
        self.assertEqual(attempt.rules_snapshot["snapshot_metadata"]["publication_id"], str(self.publication.pk))
        self.assertEqual(attempt.duration_seconds, 600)
        self.assertEqual(attempt.deadline_at, attempt.started_at + timedelta(seconds=600))
        self.assertEqual(attempt.rules_snapshot["timing"]["duration_seconds"], 600)
        self.assertEqual(attempt.rules_snapshot["timing_execution"]["overall_duration"], "SERVER_DEADLINE")
        self.assertEqual(
            attempt.rules_snapshot["timing_execution"]["separate_phase_execution"],
            "NOT_IMPLEMENTED",
        )

    def test_configured_auxiliary_timing_is_snapshotted_without_activating_phases(self):
        self.exam.trial_seconds = 15
        self.exam.review_seconds = 30
        self.exam.correction_seconds = 45
        self.exam.transcription_seconds = 90
        self.exam.save()

        attempt = start_session(learner=self.learner, publication=self.publication)
        timing = attempt.rules_snapshot["timing"]
        self.assertEqual(timing["duration_seconds"], 600)
        self.assertEqual(timing["trial_seconds"], 15)
        self.assertEqual(timing["review_seconds"], 30)
        self.assertEqual(timing["correction_seconds"], 45)
        self.assertEqual(timing["transcription_seconds"], 90)
        self.assertTrue(attempt.rules_snapshot["timing_execution"]["phase_values_are_metadata_only"])
        self.assertEqual(attempt.state, TypingSession.State.ACTIVE)
        self.assertEqual(attempt.deadline_at, attempt.started_at + timedelta(seconds=600))

    def test_live_session_snapshot_captures_all_passage_presentation_fields(self):
        self.exam.passage_font_family = "Georgia"
        self.exam.passage_font_size_pt = 14
        self.exam.passage_line_height = "1.80"
        self.exam.passage_paragraph_spacing_pt = 18
        self.exam.passage_alignment = "justify"
        self.exam.passage_first_line_indent_em = "1.5"
        self.exam.passage_preserve_tabs = True
        self.exam.passage_tab_size = 6
        self.exam.save()

        attempt = start_session(learner=self.learner, publication=self.publication)
        rules = attempt.rules_snapshot
        self.assertEqual(rules["passage_font_family"], "Georgia")
        self.assertEqual(rules["passage_font_size_pt"], 14)
        self.assertEqual(rules["passage_line_height"], "1.80")
        self.assertEqual(rules["passage_paragraph_spacing_pt"], 18)
        self.assertEqual(rules["passage_alignment"], "justify")
        self.assertEqual(rules["passage_first_line_indent_em"], "1.5")
        self.assertTrue(rules["passage_preserve_tabs"])
        self.assertEqual(rules["passage_tab_size"], 6)

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
        self.assertEqual(attempt.rules_snapshot["timing"]["duration_seconds"], 600)
        self.assertEqual(
            attempt.rules_snapshot["timing_execution"]["overall_duration"],
            "SERVER_DEADLINE",
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

    def test_server_rejects_newlines_when_enter_is_disabled(self):
        self.exam.enter_behavior = ExamConfiguration.EnterBehavior.DISABLED
        self.exam.save()
        attempt = start_session(learner=self.learner, publication=self.publication)

        with self.assertRaises(ValidationError):
            submit_session(
                session_id=attempt.pk, learner=self.learner, typed_text="One.\nTwo."
            )
        attempt.refresh_from_db()
        self.assertEqual(attempt.state, TypingSession.State.ACTIVE)
        self.assertEqual(attempt.submitted_text, "")

    def test_server_rejects_tabs_when_tab_is_disabled(self):
        self.exam.tab_behavior = ExamConfiguration.TabBehavior.DISABLED
        self.exam.save()
        attempt = start_session(learner=self.learner, publication=self.publication)

        with self.assertRaises(ValidationError):
            submit_session(
                session_id=attempt.pk, learner=self.learner, typed_text="One.\tTwo."
            )
        attempt.refresh_from_db()
        self.assertEqual(attempt.state, TypingSession.State.ACTIVE)

    def test_server_records_text_validation_and_unverifiable_keyboard_controls(self):
        self.exam.enter_behavior = ExamConfiguration.EnterBehavior.NEW_LINE
        self.exam.tab_behavior = ExamConfiguration.TabBehavior.INSERT_TAB
        self.exam.save()
        attempt = start_session(learner=self.learner, publication=self.publication)
        result = submit_session(
            session_id=attempt.pk, learner=self.learner, typed_text="One.\nTwo.\t"
        )

        audit = result.result_snapshot["input_policy_audit"]
        self.assertEqual(audit["status"], "TEXT_POLICY_VALIDATED")
        self.assertEqual(audit["checks"]["newline"], "PASSED")
        self.assertEqual(audit["checks"]["tab"], "PASSED")
        self.assertEqual(
            audit["client_controls"]["backspace"]["verification"], "CLIENT_SIDE_ONLY_UNVERIFIED"
        )
        self.assertEqual(audit["server_verification_scope"], "SUBMITTED_TEXT_ONLY")

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

    def test_unverified_exam_does_not_claim_scoring(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        self.assertEqual(attempt.rules_snapshot["verification_status"], "UNVERIFIED")
        self.assertEqual(attempt.result_snapshot, {})
        self.assertEqual(attempt.scoring_version, "")


class TypingScoringTests(TestCase):
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

    def test_client_reported_keystrokes_are_never_marked_server_verified(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="hello world", typed="hello world", duration_seconds=60,
            rules={"required_keystrokes": 10}, reported_keystrokes=20,
        )
        self.assertTrue(result["required_keystrokes_met"])
        self.assertEqual(result["keystroke_verification"], "UNVERIFIED_CLIENT_TELEMETRY")

    def test_error_percentage_does_not_mix_character_errors_with_word_denominator(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="the quick brown fox",
            typed="the quik brown fox",
            duration_seconds=60,
            rules={
                "verification_status": "VERIFIED",
                "scoring_mode": "ERROR_PERCENTAGE",
                "error_allowance_percent": "10",
                "minimum_wpm": None,
                "error_rules": {"count_word_errors": False},
            },
        )
        self.assertEqual(result["error_count_method"], "character")
        self.assertIsNone(result["error_percent"])
        self.assertEqual(result["error_percentage_unit"], "UNRESOLVED")
        self.assertIsNone(result["permitted_error_count"])
        self.assertIsNone(result["qualification"])

    def test_word_error_percentage_uses_word_units_consistently(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="the quick brown fox",
            typed="the quik brown fox",
            duration_seconds=60,
            rules={
                "verification_status": "VERIFIED",
                "scoring_mode": "ERROR_PERCENTAGE",
                "error_allowance_percent": "30",
                "error_rules": {"count_word_errors": True},
            },
        )
        self.assertEqual(result["error_count_method"], "word")
        self.assertEqual(result["error_percent"], 25.0)
        self.assertEqual(result["error_percentage_unit"], "WORDS")
        self.assertEqual(result["permitted_error_count"], 1)
        self.assertEqual(result["excess_error_count"], 0)
        self.assertTrue(result["qualification"])

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
        attempt = start_session(learner=self.learner, publication=self.publication)
        result = submit_session(
            session_id=attempt.pk, learner=self.learner, typed_text=attempt.reference_text
        )
        self.assertEqual(result.scoring_version, "tsz-char-word-v2")
        self.assertEqual(result.result_snapshot["accuracy_percent"], 100.0)
        self.assertEqual(result.result_snapshot["character_errors"], 0)


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
