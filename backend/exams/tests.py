from django.core.exceptions import ValidationError
from django.test import TestCase
from .catalogue import EXAM_NAMES, infer_metadata
from .models import ExamConfiguration


class ExamCatalogueTests(TestCase):
    def test_every_requested_exam_is_seeded(self):
        from django.core.management import call_command

        call_command("seed_exam_catalogue")
        unique_names = set(EXAM_NAMES)
        self.assertEqual(ExamConfiguration.objects.count(), len(unique_names))
        self.assertEqual(
            set(ExamConfiguration.objects.values_list("name", flat=True)),
            unique_names,
        )

    def test_seed_command_is_idempotent_and_preserves_codes(self):
        from django.core.management import call_command

        call_command("seed_exam_catalogue")
        first_codes = dict(
            ExamConfiguration.objects.values_list("name", "code")
        )
        call_command("seed_exam_catalogue")
        second_codes = dict(
            ExamConfiguration.objects.values_list("name", "code")
        )

        self.assertEqual(first_codes, second_codes)
        self.assertEqual(ExamConfiguration.objects.count(), len(set(EXAM_NAMES)))

    def test_every_catalogue_entry_has_unique_stable_code_and_safe_unverified_defaults(self):
        from django.core.management import call_command

        call_command("seed_exam_catalogue")
        exams = list(ExamConfiguration.objects.all())
        self.assertEqual(len({exam.code for exam in exams}), len(exams))
        for exam in exams:
            self.assertEqual(exam.verification_status, ExamConfiguration.Verification.UNVERIFIED)
            self.assertIsNone(exam.duration_seconds)
            self.assertEqual(exam.error_rules, {})
            self.assertEqual(exam.scoring_rules, {})
            self.assertEqual(exam.qualification_rules, {})

    def test_metadata_inference_for_language_and_interface_variants(self):
        self.assertEqual(infer_metadata("SSC CHSL 2025 Hindi (KurtiDev)")[1:3], ("HINDI", "KURTIDEV"))
        self.assertEqual(infer_metadata("SSC CHSL 2025 English Test (TCS Interface)")[3], "TCS")
        self.assertEqual(infer_metadata("SSC CHSL 2025 VH Category English")[3], "VH")

    def test_verified_configuration_requires_official_provenance_and_duration(self):
        exam = ExamConfiguration(name="Test", code="test", verification_status="VERIFIED")
        with self.assertRaises(ValidationError):
            exam.full_clean()


    def test_full_half_scoring_accepts_supported_versioned_classification_config(self):
        exam = ExamConfiguration(
            name="Full Half Test",
            code="full-half-test",
            scoring_mode=ExamConfiguration.ScoringMode.FULL_HALF_MISTAKES,
            scoring_rules={
                "mistake_classification": {
                    "version": 1,
                    "unit": "word",
                    "overrides": [
                        {"reference": "colour", "typed": "color", "classification": "HALF"},
                        {"reference": "because", "typed": "becuse", "classification": "FULL"},
                    ],
                }
            },
        )
        exam.full_clean()

    def test_full_half_scoring_rejects_duplicate_or_invalid_classification_pairs(self):
        exam = ExamConfiguration(
            name="Invalid Full Half Test",
            code="invalid-full-half-test",
            scoring_mode=ExamConfiguration.ScoringMode.FULL_HALF_MISTAKES,
            scoring_rules={
                "mistake_classification": {
                    "version": 1,
                    "unit": "word",
                    "overrides": [
                        {"reference": "colour", "typed": "color", "classification": "HALF"},
                        {"reference": "colour", "typed": "color", "classification": "FULL"},
                        {"reference": "center", "typed": "centre", "classification": "SOMETIMES"},
                    ],
                }
            },
        )
        with self.assertRaises(ValidationError) as raised:
            exam.full_clean()
        self.assertIn("scoring_rules", raised.exception.message_dict)

    def test_full_half_source_reference_requires_valid_date_and_text_fields(self):
        exam = ExamConfiguration(
            name="Invalid Source Reference",
            code="invalid-source-reference",
            scoring_mode=ExamConfiguration.ScoringMode.FULL_HALF_MISTAKES,
            scoring_rules={
                "mistake_classification": {
                    "version": 1,
                    "unit": "word",
                    "source_reference": {
                        "url": "https://example.gov/rules",
                        "title": "Official rules",
                        "locator": "Section 2",
                        "checked_at": "not-a-date",
                    },
                    "overrides": [],
                }
            },
        )
        with self.assertRaises(ValidationError):
            exam.full_clean()

    def test_full_half_scoring_keeps_legacy_unstructured_rules_compatible(self):
        exam = ExamConfiguration(
            name="Legacy Full Half Test",
            code="legacy-full-half-test",
            scoring_mode=ExamConfiguration.ScoringMode.FULL_HALF_MISTAKES,
            scoring_rules={"legacy_note": "Retain existing data"},
        )
        exam.full_clean()
        self.assertEqual(exam.scoring_rules["legacy_note"], "Retain existing data")

    def test_seed_command_preserves_existing_admin_configured_rules(self):
        from django.core.management import call_command

        call_command("seed_exam_catalogue")
        exam = ExamConfiguration.objects.get(name="BSF Head Constable (HCM)")
        exam.passage_layout = ExamConfiguration.PassageLayout.CONTINUOUS
        exam.duration_seconds = 600
        exam.allow_backspace = False
        exam.error_rules = {"count_word_errors": True, "penalty_wpm_per_error": 1}
        exam.presentation_notes = "Manually reviewed configuration."
        exam.save()

        call_command("seed_exam_catalogue")
        exam.refresh_from_db()

        self.assertEqual(exam.passage_layout, ExamConfiguration.PassageLayout.CONTINUOUS)
        self.assertEqual(exam.duration_seconds, 600)
        self.assertFalse(exam.allow_backspace)
        self.assertEqual(exam.error_rules, {"count_word_errors": True, "penalty_wpm_per_error": 1})
        self.assertEqual(exam.presentation_notes, "Manually reviewed configuration.")
