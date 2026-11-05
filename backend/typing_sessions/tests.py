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

    def test_domain_evidence_is_normalized_and_captured_immutably_at_attempt_start(self):
        self.exam.domain_evidence = {
            "timing": {
                "status": "VERIFIED",
                "references": [{
                    "url": "https://ssc.gov.in/notice.pdf",
                    "title": "Official recruitment notice",
                    "locator": "Section 8.2, page 14",
                    "checked_at": "2026-11-05",
                    "claims": ["timing.duration_seconds", "timing.minimum_wpm"],
                }],
            },
            "scoring": {"status": "PARTIAL", "references": [{
                "url": "https://ssc.gov.in/scoring.pdf",
                "title": "Scoring instructions",
                "locator": "Paragraph 3",
                "checked_at": "2026-11-04",
                "claims": ["scoring.error_allowance_percent"],
            }]},
        }
        self.exam.save()

        attempt = start_session(learner=self.learner, publication=self.publication)
        evidence = attempt.rules_snapshot["domain_evidence_snapshot"]
        self.assertEqual(evidence["capture_status"], "VALID")
        self.assertEqual(evidence["domains"]["timing"]["status"], "VERIFIED")
        self.assertEqual(
            evidence["domains"]["timing"]["references"][0]["locator"],
            "Section 8.2, page 14",
        )
        self.assertEqual(evidence["domains"]["scoring"]["status"], "PARTIAL")
        self.assertEqual(evidence["domains"]["identity"]["status"], "UNVERIFIED")
        self.assertEqual(
            attempt.rules_snapshot["canonical_specification"]["provenance"]["domain_evidence"],
            evidence,
        )

        original = attempt.rules_snapshot
        self.exam.domain_evidence = {}
        self.exam.save()
        attempt.refresh_from_db()
        self.assertEqual(attempt.rules_snapshot, original)
        self.assertEqual(
            attempt.rules_snapshot["domain_evidence_snapshot"]["domains"]["timing"]["status"],
            "VERIFIED",
        )

    def test_domain_evidence_snapshot_marks_invalid_legacy_database_payload(self):
        self.exam.domain_evidence = {
            "timing": {
                "status": "VERIFIED",
                "references": [{
                    "url": "http://example.gov/rules",
                    "title": "Untrusted source",
                    "locator": "",
                    "checked_at": "not-a-date",
                    "claims": [],
                }],
            },
        }
        self.exam.save()

        attempt = start_session(learner=self.learner, publication=self.publication)
        evidence = attempt.rules_snapshot["domain_evidence_snapshot"]
        self.assertEqual(evidence["capture_status"], "INVALID")
        self.assertTrue(evidence["validation_errors"])
        self.assertEqual(evidence["domains"]["timing"]["status"], "VERIFIED")
        self.assertEqual(evidence["domains"]["identity"]["status"], "UNVERIFIED")

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

    def test_full_half_mistakes_use_only_exact_versioned_word_pair_rules(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="alpha beta gamma",
            typed="alfa beta gmma",
            duration_seconds=60,
            rules={
                "scoring_mode": "FULL_HALF_MISTAKES",
                "rule_config_version": 3,
                "verification_status": "VERIFIED",
                "official_source_url": "https://example.gov/exam",
                "scoring_rules": {
                    "mistake_classification": {
                        "version": 1,
                        "unit": "word",
                        "source_reference": {
                            "url": "https://example.gov/rules",
                            "title": "Official typing rules",
                            "locator": "Section 4.2",
                            "checked_at": "2026-11-05",
                        },
                        "overrides": [
                            {"reference": "alpha", "typed": "alfa", "classification": "FULL"},
                            {"reference": "gamma", "typed": "gmma", "classification": "HALF"},
                        ],
                    }
                },
            },
        )
        classification = result["mistake_classification"]
        self.assertEqual(classification["status"], "CLASSIFIED")
        self.assertEqual(classification["full_mistakes"], 1)
        self.assertEqual(classification["half_mistakes"], 1)
        self.assertEqual(classification["ignored_mistakes"], 0)
        self.assertEqual(classification["weighted_mistakes"], 1.5)
        self.assertEqual(classification["rule_source"]["status"], "VERIFIED")
        self.assertEqual(classification["rule_source"]["locator"], "Section 4.2")
        self.assertEqual(classification["error_cases"][0]["rule_source"]["title"], "Official typing rules")
        self.assertEqual(result["scoring_audit"]["rule_config_version"], 3)
        self.assertEqual(result["scoring_audit"]["verification_status"], "VERIFIED")
        self.assertEqual(len(result["scoring_audit"]["scoring_rules_sha256"]), 64)
        self.assertIsNone(result["score"])
        self.assertIsNone(result["qualification"])

    def test_full_half_mistakes_remain_unresolved_when_any_error_pair_is_unconfigured(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="alpha beta",
            typed="alfa bta",
            duration_seconds=60,
            rules={
                "scoring_mode": "FULL_HALF_MISTAKES",
                "scoring_rules": {
                    "mistake_classification": {
                        "version": 1,
                        "unit": "word",
                        "overrides": [
                            {"reference": "alpha", "typed": "alfa", "classification": "FULL"},
                        ],
                    }
                },
            },
        )
        classification = result["mistake_classification"]
        self.assertEqual(classification["status"], "UNRESOLVED")
        self.assertEqual(classification["classified_error_cases"], 1)
        self.assertEqual(classification["unclassified_error_cases"], 1)
        self.assertIsNone(classification["weighted_mistakes"])
        self.assertIsNone(result["qualification"])

    def test_full_half_mistakes_reject_ambiguous_or_duplicate_configuration(self):
        from .scoring import calculate_result

        result = calculate_result(
            reference="alpha",
            typed="alfa",
            duration_seconds=60,
            rules={
                "scoring_mode": "FULL_HALF_MISTAKES",
                "scoring_rules": {
                    "mistake_classification": {
                        "version": 1,
                        "unit": "word",
                        "overrides": [
                            {"reference": "alpha", "typed": "alfa", "classification": "FULL"},
                            {"reference": "alpha", "typed": "alfa", "classification": "HALF"},
                        ],
                    }
                },
            },
        )
        self.assertEqual(result["mistake_classification"]["status"], "UNRESOLVED")
        self.assertIsNone(result["mistake_classification"]["weighted_mistakes"])

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
                "minimum_wpm": "0",
                "error_rules": {"count_word_errors": False},
                "scoring_rules": {"excess_mistake_deduction_words": 1},
            },
        )
        self.assertEqual(result["error_count_method"], "character")
        self.assertIsNone(result["error_percent"])
        self.assertEqual(result["error_percentage_unit"], "UNRESOLVED")
        self.assertIsNone(result["permitted_error_count"])
        self.assertIsNone(result["net_words"])
        self.assertIsNone(result["qualification"])
        self.assertIn("error unit is unresolved", result["qualification_note"])

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
        self.assertEqual(result.scoring_version, "tsz-char-word-v3")
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

    def test_result_page_displays_classified_full_half_mistakes(self):
        from django.urls import reverse

        self.source.content = "sample text"
        self.source.save()
        self.exam.scoring_mode = ExamConfiguration.ScoringMode.FULL_HALF_MISTAKES
        self.exam.scoring_rules = {
            "mistake_classification": {
                "version": 1,
                "unit": "word",
                "overrides": [
                    {"reference": "sample", "typed": "sampl", "classification": "HALF"},
                ],
            }
        }
        self.exam.save()

        attempt = start_session(learner=self.learner, publication=self.publication)
        submit_session(
            session_id=attempt.pk,
            learner=self.learner,
            typed_text="sampl text",
        )
        self.client.force_login(self.learner)
        response = self.client.get(
            reverse("typing_sessions:session", kwargs={"session_id": attempt.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Full / half mistake classification")
        self.assertContains(response, "Half mistakes")
        self.assertContains(response, "Weighted mistakes")
        self.assertContains(response, "not itself an official score")
        self.assertContains(response, "Historical result integrity")
        self.assertContains(response, "Valid")
        self.assertContains(response, "does not recalculate or modify your historical score")

    def test_result_page_displays_attempt_time_domain_evidence(self):
        from django.urls import reverse

        self.exam.domain_evidence = {
            "timing": {
                "status": "VERIFIED",
                "references": [{
                    "url": "https://ssc.gov.in/notice.pdf",
                    "title": "Official timing notice",
                    "locator": "Clause 7",
                    "checked_at": "2026-11-05",
                    "claims": ["timing.duration_seconds"],
                }],
            },
        }
        self.exam.save()
        attempt = start_session(learner=self.learner, publication=self.publication)
        submit_session(
            session_id=attempt.pk,
            learner=self.learner,
            typed_text=attempt.reference_text,
        )
        self.client.force_login(self.learner)
        response = self.client.get(
            reverse("typing_sessions:session", kwargs={"session_id": attempt.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Exam rule evidence captured at attempt start")
        self.assertContains(response, "Official timing notice")
        self.assertContains(response, "Clause 7")
        self.assertContains(response, "Captured")
        self.assertContains(response, "not an independent guarantee")

    def test_result_integrity_checker_validates_without_recalculating_or_mutating(self):
        from copy import deepcopy
        from .result_integrity import verify_result_integrity

        rules_snapshot = {
            "rule_config_version": 3,
            "scoring_rules": {"mistake_classification": {"version": 1, "overrides": []}},
        }
        result_snapshot = {
            "scoring_version": "tsz-char-word-v3",
            "score": 12.5,
            "scoring_audit": {
                "engine_version": "tsz-char-word-v3",
                "rule_config_version": 3,
                "scoring_rules_sha256": "PLACEHOLDER",
            },
        }
        from .result_integrity import scoring_rules_fingerprint
        result_snapshot["scoring_audit"]["scoring_rules_sha256"] = scoring_rules_fingerprint(
            rules_snapshot["scoring_rules"]
        )
        original_result = deepcopy(result_snapshot)
        integrity = verify_result_integrity(
            rules_snapshot=rules_snapshot,
            result_snapshot=result_snapshot,
        )
        self.assertEqual(integrity["status"], "VALID")
        self.assertEqual(result_snapshot, original_result)
        self.assertEqual(result_snapshot["score"], 12.5)

    def test_result_integrity_checker_detects_tampered_snapshot_metadata(self):
        from .result_integrity import verify_result_integrity

        integrity = verify_result_integrity(
            rules_snapshot={
                "rule_config_version": 3,
                "scoring_rules": {"threshold": 10},
            },
            result_snapshot={
                "scoring_version": "tsz-char-word-v3",
                "scoring_audit": {
                    "engine_version": "tsz-char-word-v3",
                    "rule_config_version": 3,
                    "scoring_rules_sha256": "0" * 64,
                },
            },
        )
        self.assertEqual(integrity["status"], "MISMATCH")
        self.assertIn("MISMATCH", [item["status"] for item in integrity["checks"]])

    def test_result_integrity_checker_marks_legacy_results_uncheckable(self):
        from .result_integrity import verify_result_integrity

        integrity = verify_result_integrity(
            rules_snapshot={"scoring_rules": {}},
            result_snapshot={"scoring_version": "legacy"},
        )
        self.assertEqual(integrity["status"], "LEGACY_UNCHECKABLE")

    def test_delhi_police_hcm_submission_stores_unified_practice_report(self):
        self.exam.code = "delhi-police-hcm-2025-english"
        self.exam.language = "ENGLISH"
        self.exam.save()
        attempt = start_session(learner=self.learner, publication=self.publication)
        result = submit_session(
            session_id=attempt.pk,
            learner=self.learner,
            typed_text="One. Two.",
        )
        report = result.result_snapshot["dphcm_attempt_report"]
        self.assertEqual(report["profile"], "DELHI_POLICE_HCM_2025")
        self.assertEqual(report["practice_metrics"]["metric_status"], "PRACTICE_ONLY")
        self.assertIn("mistake_analysis", report)
        self.assertEqual(report["marks_eligibility"]["status"], "PENDING_VERIFIED_INPUTS")
        self.assertIsNone(report["marks_eligibility"]["marks"])
        self.assertFalse(report["official_result_claimed"])

    def test_non_delhi_police_attempt_does_not_receive_dphcm_report(self):
        attempt = start_session(learner=self.learner, publication=self.publication)
        result = submit_session(
            session_id=attempt.pk,
            learner=self.learner,
            typed_text="One. Two.",
        )
        self.assertNotIn("dphcm_attempt_report", result.result_snapshot)

    def test_dphcm_dashboard_shows_only_learner_attempt_reports(self):
        from django.urls import reverse

        self.exam.code = "delhi-police-hcm-2025-english"
        self.exam.language = "ENGLISH"
        self.exam.save()
        own = start_session(learner=self.learner, publication=self.publication)
        submit_session(session_id=own.pk, learner=self.learner, typed_text=own.reference_text)
        other = start_session(learner=self.other, publication=self.publication)
        submit_session(session_id=other.pk, learner=self.other, typed_text=other.reference_text)

        self.client.force_login(self.learner)
        response = self.client.get(reverse("typing_sessions:dphcm_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["attempt_count"], 1)
        self.assertContains(response, "Delhi Police HCM practice dashboard")
        self.assertContains(response, "Average net practice WPM")

    def test_dphcm_dashboard_trends_are_chronological_and_scaled(self):
        from django.urls import reverse

        self.exam.code = "delhi-police-hcm-2025-english"
        self.exam.language = "ENGLISH"
        self.exam.save()
        first = start_session(learner=self.learner, publication=self.publication)
        first_result = submit_session(
            session_id=first.pk, learner=self.learner, typed_text=first.reference_text
        )
        second = start_session(learner=self.learner, publication=self.publication)
        second_result = submit_session(
            session_id=second.pk, learner=self.learner, typed_text=second.reference_text
        )

        self.client.force_login(self.learner)
        response = self.client.get(reverse("typing_sessions:dphcm_dashboard"))
        self.assertEqual(response.status_code, 200)
        trend = response.context["trend_rows"]
        self.assertEqual(len(trend), 2)
        self.assertLessEqual(trend[0]["date"], trend[1]["date"])
        self.assertEqual(trend[0]["speed_width"], 100)
        self.assertEqual(trend[1]["speed_width"], 100)
        self.assertGreaterEqual(trend[0]["accuracy_width"], 0)
        self.assertLessEqual(trend[0]["accuracy_width"], 100)

    def test_dphcm_dashboard_filters_attempts_by_captured_language(self):
        from django.urls import reverse

        self.exam.code = "delhi-police-hcm-2025-english"
        self.exam.language = "ENGLISH"
        self.exam.save()
        english = start_session(learner=self.learner, publication=self.publication)
        submit_session(session_id=english.pk, learner=self.learner, typed_text=english.reference_text)

        self.exam.language = "HINDI"
        self.exam.save()
        hindi = start_session(learner=self.learner, publication=self.publication)
        submit_session(session_id=hindi.pk, learner=self.learner, typed_text=hindi.reference_text)

        self.client.force_login(self.learner)
        response = self.client.get(
            reverse("typing_sessions:dphcm_dashboard"), {"language": "ENGLISH"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["attempt_count"], 1)
        self.assertEqual(response.context["selected_language"], "ENGLISH")

    def test_dphcm_dashboard_rejects_reversed_date_range_without_querying_filtered_results(self):
        from django.urls import reverse

        self.client.force_login(self.learner)
        response = self.client.get(
            reverse("typing_sessions:dphcm_dashboard"),
            {"start_date": "2026-11-10", "end_date": "2026-11-01"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Start date must be on or before the end date.", response.context["filter_error"])
        self.assertEqual(response.context["attempt_count"], 0)

    def test_dphcm_dashboard_saves_learner_personal_goals(self):
        from django.urls import reverse
        from .models import LearnerPracticeGoal

        self.client.force_login(self.learner)
        response = self.client.post(
            reverse("typing_sessions:dphcm_dashboard"),
            {"target_net_wpm": "42", "target_accuracy": "97"},
        )
        self.assertEqual(response.status_code, 302)
        goal = LearnerPracticeGoal.objects.get(learner=self.learner)
        self.assertEqual(goal.target_net_wpm, 42)
        self.assertEqual(goal.target_accuracy, 97)

    def test_dphcm_dashboard_rejects_out_of_range_personal_goals(self):
        from django.urls import reverse
        from .models import LearnerPracticeGoal

        self.client.force_login(self.learner)
        response = self.client.post(
            reverse("typing_sessions:dphcm_dashboard"),
            {"target_net_wpm": "250", "target_accuracy": "97"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter speed from 1")
        goal = LearnerPracticeGoal.objects.get(learner=self.learner)
        self.assertEqual(goal.target_net_wpm, 30)
        self.assertEqual(goal.target_accuracy, 95)

    def test_dphcm_dashboard_goals_are_private_per_learner(self):
        from .models import LearnerPracticeGoal

        own = LearnerPracticeGoal.objects.create(
            learner=self.learner, target_net_wpm=45, target_accuracy=98
        )
        other = LearnerPracticeGoal.objects.create(
            learner=self.other, target_net_wpm=35, target_accuracy=96
        )
        self.assertNotEqual(own.pk, other.pk)
        self.assertEqual(LearnerPracticeGoal.objects.filter(learner=self.learner).count(), 1)

    def test_dphcm_dashboard_seven_day_report_includes_recent_attempt(self):
        from django.urls import reverse
        from django.utils import timezone

        self.exam.code = "delhi-police-hcm-2025-english"
        self.exam.language = "ENGLISH"
        self.exam.save()
        attempt = start_session(learner=self.learner, publication=self.publication)
        submit_session(session_id=attempt.pk, learner=self.learner, typed_text=attempt.reference_text)

        self.client.force_login(self.learner)
        response = self.client.get(reverse("typing_sessions:dphcm_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["weekly_daily_rows"]), 7)
        self.assertEqual(response.context["weekly_summary"]["attempt_count"], 1)
        today_row = next(
            row for row in response.context["weekly_daily_rows"]
            if row["date"] == timezone.localdate()
        )
        self.assertEqual(today_row["attempt_count"], 1)
        self.assertIsNotNone(today_row["average_net_wpm"])

    def test_dphcm_dashboard_seven_day_report_is_empty_without_recent_attempts(self):
        from django.urls import reverse

        self.client.force_login(self.learner)
        response = self.client.get(reverse("typing_sessions:dphcm_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["weekly_daily_rows"]), 7)
        self.assertEqual(response.context["weekly_summary"]["attempt_count"], 0)
        self.assertIsNone(response.context["weekly_summary"]["average_net_wpm"])


    def test_dphcm_dashboard_monthly_report_aggregates_saved_attempts(self):
        from django.urls import reverse
        from django.utils import timezone

        self.exam.code = "delhi-police-hcm-2025-english"
        self.exam.language = "ENGLISH"
        self.exam.save()
        attempt = start_session(learner=self.learner, publication=self.publication)
        submit_session(session_id=attempt.pk, learner=self.learner, typed_text=attempt.reference_text)

        self.client.force_login(self.learner)
        response = self.client.get(reverse("typing_sessions:dphcm_dashboard"))
        self.assertEqual(response.status_code, 200)
        monthly_rows = response.context["monthly_rows"]
        self.assertEqual(len(monthly_rows), 1)
        self.assertEqual(monthly_rows[0]["month"], timezone.localdate().replace(day=1))
        self.assertEqual(monthly_rows[0]["attempt_count"], 1)
        self.assertIsNotNone(monthly_rows[0]["average_net_wpm"])
        self.assertIsNotNone(monthly_rows[0]["average_accuracy"])
        self.assertContains(response, "Monthly performance report")
        self.assertContains(response, "Print / Save as PDF")


    def test_dphcm_dashboard_progress_comparison_handles_missing_prior_period(self):
        from django.urls import reverse

        self.exam.code = "delhi-police-hcm-2025-english"
        self.exam.language = "ENGLISH"
        self.exam.save()
        attempt = start_session(learner=self.learner, publication=self.publication)
        submit_session(session_id=attempt.pk, learner=self.learner, typed_text=attempt.reference_text)

        self.client.force_login(self.learner)
        response = self.client.get(reverse("typing_sessions:dphcm_dashboard"))
        self.assertEqual(response.status_code, 200)
        comparisons = response.context["progress_comparisons"]
        self.assertEqual([item["window_days"] for item in comparisons], [30, 60, 90])
        self.assertEqual(comparisons[0]["current_attempts"], 1)
        self.assertIsNotNone(comparisons[0]["current_speed"])
        self.assertIsNone(comparisons[0]["speed_change"])
        self.assertIsNone(comparisons[0]["accuracy_change"])
        self.assertContains(response, "30 / 60 / 90-day progress analysis")


    def test_dphcm_dashboard_practice_calendar_counts_active_days_and_streak(self):
        from django.urls import reverse

        self.exam.code = "delhi-police-hcm-2025-english"
        self.exam.language = "ENGLISH"
        self.exam.save()
        attempt = start_session(learner=self.learner, publication=self.publication)
        submit_session(session_id=attempt.pk, learner=self.learner, typed_text=attempt.reference_text)

        self.client.force_login(self.learner)
        response = self.client.get(reverse("typing_sessions:dphcm_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["calendar_rows"]), 90)
        summary = response.context["calendar_summary"]
        self.assertEqual(summary["active_days"], 1)
        self.assertEqual(summary["current_streak"], 1)
        self.assertEqual(summary["longest_streak"], 1)
        self.assertEqual(summary["consistency_percent"], round(100 / 90, 1))
        self.assertEqual(summary["attempt_count"], 1)
        self.assertContains(response, "90-day practice calendar")

    def test_dphcm_dashboard_practice_calendar_is_empty_without_attempts(self):
        from django.urls import reverse

        self.client.force_login(self.learner)
        response = self.client.get(reverse("typing_sessions:dphcm_dashboard"))
        self.assertEqual(response.status_code, 200)
        summary = response.context["calendar_summary"]
        self.assertEqual(len(response.context["calendar_rows"]), 90)
        self.assertEqual(summary["active_days"], 0)
        self.assertEqual(summary["current_streak"], 0)
        self.assertEqual(summary["longest_streak"], 0)
        self.assertEqual(summary["consistency_percent"], 0)


    def test_dphcm_dashboard_daily_plan_has_foundation_defaults_without_recent_data(self):
        from django.urls import reverse

        self.client.force_login(self.learner)
        response = self.client.get(reverse("typing_sessions:dphcm_dashboard"))
        self.assertEqual(response.status_code, 200)
        plan = response.context["daily_practice_plan"]
        self.assertEqual(plan["minutes"], 20)
        self.assertEqual(plan["passages"], 2)
        self.assertEqual(plan["warmup_minutes"], 5)
        self.assertEqual(plan["review_minutes"], 5)
        self.assertContains(response, "Your suggested daily practice plan")

    def test_dphcm_dashboard_daily_plan_adjusts_for_accuracy_gap(self):
        from django.urls import reverse

        self.exam.code = "delhi-police-hcm-2025-english"
        self.exam.language = "ENGLISH"
        self.exam.save()
        attempt = start_session(learner=self.learner, publication=self.publication)
        submit_session(session_id=attempt.pk, learner=self.learner, typed_text=attempt.reference_text)

        self.client.force_login(self.learner)
        response = self.client.get(reverse("typing_sessions:dphcm_dashboard"))
        self.assertEqual(response.status_code, 200)
        plan = response.context["daily_practice_plan"]
        self.assertGreaterEqual(plan["minutes"], 20)
        self.assertGreaterEqual(plan["passages"], 2)
        self.assertIn(plan["minutes"], (20, 30, 35, 40, 45))


    def test_dphcm_dashboard_weekly_timetable_has_sunday_recovery_and_future_days(self):
        from django.urls import reverse
        from django.utils import timezone

        self.client.force_login(self.learner)
        response = self.client.get(reverse("typing_sessions:dphcm_dashboard"))
        self.assertEqual(response.status_code, 200)
        rows = response.context["weekly_timetable_rows"]
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0]["date"].weekday(), 0)
        self.assertEqual(rows[-1]["date"].weekday(), 6)
        self.assertEqual(rows[-1]["status"], "REST")
        today = timezone.localdate()
        future_rows = [row for row in rows if row["date"] > today and not row["is_rest_day"]]
        self.assertTrue(all(row["status"] == "UPCOMING" for row in future_rows))
        self.assertEqual(response.context["weekly_plan_summary"]["completed_days"], 0)
        self.assertContains(response, "Weekly practice timetable")


    def test_dphcm_dashboard_saves_private_daily_reminder_preference(self):
        from django.urls import reverse
        from .models import LearnerPracticeReminder

        self.client.force_login(self.learner)
        response = self.client.post(
            reverse("typing_sessions:dphcm_dashboard"),
            {"form_action": "save_reminder", "reminder_enabled": "on", "reminder_time": "19:30"},
        )
        self.assertEqual(response.status_code, 302)
        reminder = LearnerPracticeReminder.objects.get(learner=self.learner)
        self.assertTrue(reminder.enabled)
        self.assertEqual(reminder.reminder_time.strftime("%H:%M"), "19:30")
        self.assertFalse(LearnerPracticeReminder.objects.filter(learner=self.other).exists())

    def test_dphcm_dashboard_shows_due_reminder_only_after_time_without_attempt(self):
        from datetime import time
        from django.urls import reverse
        from .models import LearnerPracticeReminder

        LearnerPracticeReminder.objects.create(
            learner=self.learner, enabled=True, reminder_time=time(0, 0)
        )
        self.client.force_login(self.learner)
        response = self.client.get(reverse("typing_sessions:dphcm_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["reminder_due"])
        self.assertContains(response, "Your scheduled practice time has arrived")

    def test_dphcm_dashboard_does_not_show_due_reminder_after_completed_attempt(self):
        from datetime import time
        from django.urls import reverse
        from .models import LearnerPracticeReminder

        self.exam.code = "delhi-police-hcm-2025-english"
        self.exam.language = "ENGLISH"
        self.exam.save()
        attempt = start_session(learner=self.learner, publication=self.publication)
        submit_session(session_id=attempt.pk, learner=self.learner, typed_text=attempt.reference_text)
        LearnerPracticeReminder.objects.create(
            learner=self.learner, enabled=True, reminder_time=time(0, 0)
        )
        self.client.force_login(self.learner)
        response = self.client.get(reverse("typing_sessions:dphcm_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["reminder_due"])
