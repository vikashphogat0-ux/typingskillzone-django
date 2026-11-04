from django.test import TestCase
from django.utils.text import slugify
from .catalogue import EXAM_NAMES, infer_metadata
from .models import ExamConfiguration


class ExamCatalogueTests(TestCase):
    def test_every_requested_exam_is_seeded(self):
        from django.core.management import call_command
        call_command("seed_exam_catalogue")
        self.assertEqual(ExamConfiguration.objects.count(), len(set(EXAM_NAMES)))
        self.assertEqual(set(ExamConfiguration.objects.values_list("name", flat=True)), set(EXAM_NAMES))

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
        with self.assertRaises(Exception):
            exam.full_clean()
