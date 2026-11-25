"""Read-only seven-stage readiness audit for every configured exam profile."""
import json

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


class Command(BaseCommand):
    help = "Audit every exam profile without modifying configuration or attempt data."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true", help="Exit non-zero when any profile is not ready.")
        parser.add_argument("--active-only", action="store_true", help="Audit active profiles only.")
        parser.add_argument("--json", action="store_true", dest="as_json", help="Print a machine-readable audit report.")

    def handle(self, *args, **options):
        profiles = ExamConfiguration.objects.all().order_by("code")
        if options["active_only"]:
            profiles = profiles.filter(is_active=True)

        records = []
        stage_totals = {
            stage: {"ready": 0, "blocked": 0}
            for stage in PIPELINE_STAGES
        }
        for exam in profiles.iterator():
            result = audit_exam_configuration(exam)
            stage_checks = result.get("stage_checks", {})
            for stage in PIPELINE_STAGES:
                details = stage_checks.get(stage, {})
                status = details.get("status")
                if status == "READY":
                    stage_totals[stage]["ready"] += 1
                else:
                    stage_totals[stage]["blocked"] += 1

            records.append({
                "code": exam.code,
                "name": exam.name,
                "category": exam.category,
                "is_active": exam.is_active,
                "status": result.get("status", "DRAFT_INCOMPLETE"),
                "ready": bool(result.get("ready")),
                "errors": result.get("errors", []),
                "warnings": result.get("warnings", []),
                "stage_checks": stage_checks,
                "profile": result.get("profile", {}),
            })

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
                "stage_totals": stage_totals,
                "profiles": records,
            }, ensure_ascii=False, indent=2))
        else:
            self.stdout.write(f"Profiles audited: {total}")
            self.stdout.write(self.style.SUCCESS(f"Ready: {ready}"))
            self.stdout.write(self.style.WARNING(f"Blocked/incomplete: {blocked}"))
            self.stdout.write(f"Profiles with warnings: {profiles_with_warnings}")
            for stage in PIPELINE_STAGES:
                counts = stage_totals[stage]
                self.stdout.write(
                    f"{stage}: READY {counts['ready']} / BLOCKED {counts['blocked']}"
                )
            for item in records:
                if item["ready"] and not item["warnings"]:
                    continue
                self.stdout.write(f"\\n[{item['code']}] {item['name']}")
                for error in item["errors"]:
                    self.stdout.write(self.style.ERROR(f"  BLOCKER: {error}"))
                for warning in item["warnings"]:
                    self.stdout.write(self.style.WARNING(f"  WARNING: {warning}"))

        if options["strict"] and blocked:
            raise CommandError(f"{blocked} of {total} exam profiles are not release-ready.")
