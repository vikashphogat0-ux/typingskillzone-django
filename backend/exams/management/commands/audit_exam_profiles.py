"""Read-only seven-stage readiness and source-catalogue audit for exam profiles."""
import json
from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from exams.configuration_audit import audit_exam_configuration
from exams.models import ExamConfiguration


PIPELINE_STAGES = (
    "catalogue",
    "candidate_selection",
    "launch_and_timer",
    "interface_and_passage",
    "scoring",
    "qualification",
    "result_and_audit",
)
INTERNAL_SOURCE_PREFIX = "Internal rule profile: Master Exam Rulebook"


def source_identity(exam):
    """Return importer provenance without assuming exam names are unique."""
    scoring = exam.scoring_rules or {}
    profile_config = scoring.get("profile_configuration") or {}
    source_id = profile_config.get("source_profile_id") or scoring.get("source_profile_id")
    source_number = profile_config.get("source_profile_number") or scoring.get("source_profile_number")
    return {
        "source_title": exam.source_title,
        "source_profile_id": source_id,
        "source_profile_number": source_number,
        "verification_status": exam.verification_status,
    }


class Command(BaseCommand):
    help = "Audit every exam profile and source identity without modifying records or attempts."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true", help="Exit non-zero when any profile is not ready.")
        parser.add_argument("--active-only", action="store_true", help="Audit active profiles only.")
        parser.add_argument("--json", action="store_true", dest="as_json", help="Print a machine-readable audit report.")

    def handle(self, *args, **options):
        all_profiles = ExamConfiguration.objects.all().order_by("code")
        profiles = all_profiles.filter(is_active=True) if options["active_only"] else all_profiles

        records = []
        stage_totals = {stage: {"ready": 0, "blocked": 0} for stage in PIPELINE_STAGES}
        for exam in profiles.iterator():
            result = audit_exam_configuration(exam)
            stage_checks = result.get("stage_checks", {})
            for stage in PIPELINE_STAGES:
                if stage_checks.get(stage, {}).get("status") == "READY":
                    stage_totals[stage]["ready"] += 1
                else:
                    stage_totals[stage]["blocked"] += 1
            records.append({
                "code": exam.code,
                "name": exam.name,
                "category": exam.category,
                "is_active": exam.is_active,
                "source": source_identity(exam),
                "status": result.get("status", "DRAFT_INCOMPLETE"),
                "ready": bool(result.get("ready")),
                "errors": result.get("errors", []),
                "warnings": result.get("warnings", []),
                "stage_checks": stage_checks,
                "profile": result.get("profile", {}),
            })

        # Catalogue reconciliation is deliberately independent of --active-only:
        # filtering the readiness report must not hide inactive source profiles.
        source_profiles = list(
            ExamConfiguration.objects.filter(source_title__startswith=INTERNAL_SOURCE_PREFIX)
        )
        source_ids = []
        source_profiles_missing_id = []
        for exam in source_profiles:
            identity = source_identity(exam)
            if identity["source_profile_id"]:
                source_ids.append(identity["source_profile_id"])
            else:
                source_profiles_missing_id.append(exam.code)
        duplicate_source_ids = sorted(
            source_id for source_id, count in Counter(source_ids).items() if count > 1
        )
        source_catalogue = {
            "rulebook_profiles_found": len(source_profiles),
            "active_rulebook_profiles": sum(exam.is_active for exam in source_profiles),
            "inactive_rulebook_profiles": sum(not exam.is_active for exam in source_profiles),
            "profiles_with_source_id": len(source_ids),
            "profiles_missing_source_id": source_profiles_missing_id,
            "duplicate_source_profile_ids": duplicate_source_ids,
            "independent_source_ids": len(set(source_ids)),
            "expected_independent_source_profiles": 161,
            "count_matches_expected": (
                len(source_profiles) == 161
                and len(source_ids) == 161
                and len(set(source_ids)) == 161
            ),
        }

        total = len(records)
        ready = sum(item["ready"] for item in records)
        blocked = total - ready
        profiles_with_warnings = sum(bool(item["warnings"]) for item in records)

        if options["as_json"]:
            self.stdout.write(json.dumps({
                "profiles_audited": total,
                "ready": ready,
                "blocked": blocked,
                "profiles_with_warnings": profiles_with_warnings,
                "source_catalogue": source_catalogue,
                "stage_totals": stage_totals,
                "profiles": records,
            }, ensure_ascii=False, indent=2))
        else:
            self.stdout.write(f"Profiles audited: {total}")
            self.stdout.write(self.style.SUCCESS(f"Ready: {ready}"))
            self.stdout.write(self.style.WARNING(f"Blocked/incomplete: {blocked}"))
            self.stdout.write(f"Profiles with warnings: {profiles_with_warnings}")
            self.stdout.write(
                "Rulebook source profiles: "
                f"{len(source_profiles)}; active: {source_catalogue['active_rulebook_profiles']}; "
                f"inactive: {source_catalogue['inactive_rulebook_profiles']}; "
                f"identified: {len(source_ids)}; missing IDs: {len(source_profiles_missing_id)}; "
                f"duplicate IDs: {len(duplicate_source_ids)}; "
                f"161-profile catalogue match: {source_catalogue['count_matches_expected']}"
            )
            for stage in PIPELINE_STAGES:
                counts = stage_totals[stage]
                self.stdout.write(f"{stage}: READY {counts['ready']} / BLOCKED {counts['blocked']}")
            for item in records:
                if item["ready"] and not item["warnings"]:
                    continue
                self.stdout.write(f"\n[{item['code']}] {item['name']}")
                for error in item["errors"]:
                    self.stdout.write(self.style.ERROR(f"  BLOCKER: {error}"))
                for warning in item["warnings"]:
                    self.stdout.write(self.style.WARNING(f"  WARNING: {warning}"))

        if options["strict"] and (blocked or not source_catalogue["count_matches_expected"]):
            raise CommandError(
                f"{blocked} of {total} profiles are not release-ready, or the independent "
                "161-profile source catalogue does not match."
            )
