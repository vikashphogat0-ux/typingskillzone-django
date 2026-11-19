"""Enable whole-word error counting on existing exams that lack it.

Dry run by default. Run with --apply only after reviewing the printed list. The seed command
never updates exams already at rule_config_version >= 2, so existing rows need this command.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from exams.models import ExamConfiguration

ERROR_BASED_MODES = {"ERROR_PERCENTAGE", "STROKE_PENALTY"}


class Command(BaseCommand):
    help = "Report or apply count_word_errors=true to error-based exams that do not set it."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the change. Without this flag the command only reports.",
        )

    def handle(self, *args, **options):
        pending = [
            exam
            for exam in ExamConfiguration.objects.filter(scoring_mode__in=ERROR_BASED_MODES).order_by("name")
            if not (exam.error_rules or {}).get("count_word_errors")
        ]
        if not pending:
            self.stdout.write(self.style.SUCCESS("No error-based exams need changes."))
            return

        verb = "UPDATE" if options["apply"] else "WOULD UPDATE"
        for exam in pending:
            self.stdout.write(f"{verb}: {exam.name} ({exam.scoring_mode})")

        if options["apply"]:
            with transaction.atomic():
                for exam in pending:
                    exam.error_rules = {**(exam.error_rules or {}), "count_word_errors": True}
                    exam.save(update_fields=["error_rules", "updated_at"])
            self.stdout.write(self.style.SUCCESS(f"Updated {len(pending)} exam(s)."))
        else:
            self.stdout.write("Dry run only. Re-run with --apply after review.")
