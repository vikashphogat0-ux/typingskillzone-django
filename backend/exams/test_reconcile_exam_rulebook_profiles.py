import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from exams.models import ExamConfiguration


class ReconcileExamRulebookProfilesTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "profiles.json"
        self.path.write_text(json.dumps({
            "schema_version": 1,
            "profiles": [{
                "number": 1,
                "profile_id": "fresh-independent-profile-001",
                "name": "Fresh Independent Profile English",
                "source_heading": "Fresh Independent Profile English",
                "source_text": [
                    "Exam Pattern & Qualifying Nature: Practice profile.",
                    "Duration & Target: 10 minutes.",
                    "Interface, Passage & Keyboard Rules: English QWERTY.",
                ],
            }],
        }), encoding="utf-8")

        marker = "Internal rule profile: Master Exam Rulebook (superseded import, practice only)"
        self.superseded = ExamConfiguration.objects.create(
            code="old-profile", name="Old profile", source_title=marker,
            scoring_rules={"profile_configuration": {"source_profile_id": "old-profile-id"}},
            is_active=True,
        )
        self.manual = ExamConfiguration.objects.create(
            code="manual-profile", name="Manual profile",
            source_title="Administrator configured profile", is_active=True,
        )

    def test_default_is_dry_run_and_changes_nothing(self):
        call_command("reconcile_exam_rulebook_profiles", str(self.path), "--expected-count", "1")
        self.assertFalse(ExamConfiguration.objects.filter(code="fresh-independent-profile-001").exists())
        self.superseded.refresh_from_db()
        self.assertTrue(self.superseded.is_active)
        self.manual.refresh_from_db()
        self.assertTrue(self.manual.is_active)

    def test_execute_activates_current_source_and_deactivates_only_stale_owned_rows(self):
        call_command(
            "reconcile_exam_rulebook_profiles", str(self.path),
            "--expected-count", "1", "--execute",
        )
        current = ExamConfiguration.objects.get(code="fresh-independent-profile-001")
        self.assertTrue(current.is_active)
        self.assertEqual(
            current.scoring_rules["profile_configuration"]["source_profile_id"],
            "fresh-independent-profile-001",
        )
        self.superseded.refresh_from_db()
        self.assertFalse(self.superseded.is_active)
        self.assertTrue(ExamConfiguration.objects.filter(pk=self.superseded.pk).exists())
        self.manual.refresh_from_db()
        self.assertTrue(self.manual.is_active)

    def test_code_collision_with_non_rulebook_record_aborts_without_changes(self):
        ExamConfiguration.objects.create(
            code="fresh-independent-profile-001", name="Manual collision",
            source_title="Manual source", is_active=True,
        )
        with self.assertRaises(Exception):
            call_command(
                "reconcile_exam_rulebook_profiles", str(self.path),
                "--expected-count", "1", "--execute",
            )
        self.superseded.refresh_from_db()
        self.assertTrue(self.superseded.is_active)
