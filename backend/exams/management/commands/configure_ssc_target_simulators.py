from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from exams.models import ExamConfiguration


class Command(BaseCommand):
    help = (
        "Apply only the three user-approved SSC simulator profiles: "
        "CHSL 2025 English TCS, CHSL 2025 VH English, and DPA Grade-A."
    )

    TARGETS = (
        ("SSC CHSL 2025 English Test (TCS Interface)", "configure_ssc_chsl_2025_english"),
        ("SSC CHSL 2025 VH Category English", "configure_ssc_chsl_2025_vh_english"),
        ("SSC Data Processing Assistant Grade-A", "configure_ssc_dpa_grade_a"),
    )

    def handle(self, *args, **options):
        missing = [
            name for name, _command in self.TARGETS
            if not ExamConfiguration.objects.filter(name=name).exists()
        ]
        if missing:
            raise CommandError(
                "The following exact exam catalogue records are missing: "
                + ", ".join(missing)
                + ". Run seed_exam_catalogue first, then rerun this command."
            )

        for name, command in self.TARGETS:
            call_command(command)
            self.stdout.write(self.style.SUCCESS(f"Applied profile: {name}"))

        self.stdout.write(self.style.SUCCESS(
            "All three requested SSC simulator profiles have been applied. "
            "No other exam configuration was modified by this command."
        ))
