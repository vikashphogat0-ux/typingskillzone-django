from datetime import date

from django.core.management.base import BaseCommand, CommandError

from exams.models import ExamConfiguration
from passages.scheduling import apply_schedule, default_start_date, plan_schedule


class Command(BaseCommand):
    help = "Plan, and with --apply write, release schedules for unscheduled passages."

    def add_arguments(self, parser):
        parser.add_argument("--start", help="First release date, YYYY-MM-DD (default: tomorrow).")
        parser.add_argument("--exam", help="One exam code (default: every active exam).")
        parser.add_argument("--apply", action="store_true", help="Write the schedule. Without this, nothing changes.")

    def handle(self, *args, **options):
        try:
            start = date.fromisoformat(options["start"]) if options["start"] else default_start_date()
        except ValueError:
            raise CommandError("--start must be a date in YYYY-MM-DD format.")

        exams = ExamConfiguration.objects.filter(is_active=True).order_by("code")
        if options["exam"]:
            exams = exams.filter(code=options["exam"])

        for exam in exams:
            try:
                plan = plan_schedule(exam, start)
            except ValueError as error:
                self.stderr.write(f"{exam.code}: {error}")
                continue
            if not plan:
                self.stdout.write(f"{exam.code}: nothing to schedule")
                continue
            self.stdout.write(f"{exam.code}: {len(plan)} passage(s), {plan[0][1]} to {plan[-1][1]}")
            if options["apply"]:
                apply_schedule(plan)

        if not options["apply"]:
            self.stdout.write("Dry run only. Add --apply to write the schedule.")
