"""Read-only seven-stage readiness audit for every configured exam profile."""
from django.core.management.base import BaseCommand, CommandError

from exams.configuration_audit import audit_exam_configuration
from exams.models import ExamConfiguration


class Command(BaseCommand):
    help = "Audit every exam profile without modifying configuration or attempt data."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true", help="Exit non-zero when any profile is not ready.")
        parser.add_argument("--active-only", action="store_true", help="Audit active profiles only.")

    def handle(self, *args, **options):
        profiles = ExamConfiguration.objects.all().order_by("code")
        if options["active_only"]:
            profiles = profiles.filter(is_active=True)

        total = ready = 0
        stage_totals = {}
        blocked = []
        for exam in profiles.iterator():
            total += 1
            result = audit_exam_configuration(exam)
            if result["ready"]:
                ready += 1
            else:
                blocked.append((exam.code, result["errors"]))
            for stage, details in result["stage_checks"].items():
                counts = stage_totals.setdefault(stage, {"ready": 0, "blocked": 0})
                counts["ready" if details["status"] == "READY" else "blocked"] += 1

        self.stdout.write(f"Profiles audited: {total}")
        self.stdout.write(f"Ready: {ready}; blocked/incomplete: {total - ready}")
        for stage, counts in stage_totals.items():
            self.stdout.write(
                f"{stage}: READY {counts['ready']} / BLOCKED {counts['blocked']}"
            )
        for code, errors in blocked:
            self.stdout.write(self.style.WARNING(f"{code}: " + " | ".join(errors)))

        if options["strict"] and blocked:
            raise CommandError(f"{len(blocked)} of {total} exam profiles are not release-ready.")
