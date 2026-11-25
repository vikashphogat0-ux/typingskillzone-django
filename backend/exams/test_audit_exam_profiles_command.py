import json
from io import StringIO

from django.core.management import call_command, CommandError
from django.test import TestCase

from exams.models import ExamConfiguration


class AuditExamProfilesCommandTests(TestCase):
    def setUp(self):
        self.active = ExamConfiguration.objects.create(
            code="active-audit-profile", name="Active audit profile",
            language="ENGLISH", script="LATIN", is_active=True,
        )
        self.inactive = ExamConfiguration.objects.create(
            code="inactive-audit-profile", name="Inactive audit profile",
            language="ENGLISH", script="LATIN", is_active=False,
        )

    def test_default_audit_includes_active_and_inactive_profiles(self):
        output = StringIO()
        call_command("audit_exam_profiles", "--json", stdout=output)
        report = json.loads(output.getvalue())
        self.assertEqual(report["profiles_audited"], 2)
        self.assertEqual({item["code"] for item in report["profiles"]},
                         {"active-audit-profile", "inactive-audit-profile"})
        self.assertEqual(set(report["stage_totals"]), {
            "catalogue", "candidate_selection", "launch_and_timer",
            "interface_and_passage", "scoring", "qualification", "result_and_audit",
        })
        for counts in report["stage_totals"].values():
            self.assertEqual(counts["ready"] + counts["blocked"], 2)

    def test_active_only_filters_out_inactive_profiles(self):
        output = StringIO()
        call_command("audit_exam_profiles", "--active-only", "--json", stdout=output)
        report = json.loads(output.getvalue())
        self.assertEqual(report["profiles_audited"], 1)
        self.assertEqual([item["code"] for item in report["profiles"]], ["active-audit-profile"])

    def test_strict_mode_fails_when_any_profile_is_blocked(self):
        with self.assertRaises(CommandError):
            call_command("audit_exam_profiles", "--strict", stdout=StringIO())

    def test_json_report_contains_profile_errors_warnings_and_stage_details(self):
        output = StringIO()
        call_command("audit_exam_profiles", "--json", stdout=output)
        report = json.loads(output.getvalue())
        profile = next(item for item in report["profiles"] if item["code"] == self.active.code)
        self.assertIn("errors", profile)
        self.assertIn("warnings", profile)
        self.assertIn("stage_checks", profile)
        self.assertEqual(set(profile["stage_checks"]), set(report["stage_totals"]))
        self.assertGreater(report["blocked"], 0)

    def test_audit_does_not_modify_profile_records(self):
        before = list(ExamConfiguration.objects.order_by("code").values(
            "code", "is_active", "duration_seconds", "scoring_rules", "qualification_rules"
        ))
        call_command("audit_exam_profiles", stdout=StringIO())
        after = list(ExamConfiguration.objects.order_by("code").values(
            "code", "is_active", "duration_seconds", "scoring_rules", "qualification_rules"
        ))
        self.assertEqual(after, before)

    def test_source_identity_report_detects_missing_and_duplicate_ids(self):
        marker = "Internal rule profile: Master Exam Rulebook (source-compiled, practice only)"
        ExamConfiguration.objects.create(
            code="source-one", name="Same display name", source_title=marker,
            scoring_rules={"profile_configuration": {"source_profile_id": "source-001", "source_profile_number": 1}},
        )
        ExamConfiguration.objects.create(
            code="source-two", name="Same display name", source_title=marker,
            scoring_rules={"profile_configuration": {"source_profile_id": "source-001", "source_profile_number": 2}},
        )
        ExamConfiguration.objects.create(
            code="source-three", name="Missing identity", source_title=marker,
        )
        output = StringIO()
        call_command("audit_exam_profiles", "--json", stdout=output)
        report = json.loads(output.getvalue())
        catalogue = report["source_catalogue"]
        self.assertEqual(catalogue["rulebook_profiles_found"], 3)
        self.assertEqual(catalogue["profiles_with_source_id"], 2)
        self.assertEqual(catalogue["independent_source_ids"], 1)
        self.assertEqual(catalogue["duplicate_source_profile_ids"], ["source-001"])
        self.assertEqual(catalogue["profiles_missing_source_id"], ["source-three"])
        self.assertFalse(catalogue["count_matches_expected"])
        item = next(profile for profile in report["profiles"] if profile["code"] == "source-one")
        self.assertEqual(item["source"]["source_profile_number"], 1)
