from django.core.management.base import BaseCommand
from django.utils.text import slugify
from exams.catalogue import EXAM_NAMES, infer_metadata
from exams.models import ExamConfiguration


class Command(BaseCommand):
    help = "Create or safely update the initial TypingSkillZone exam catalogue."

    def handle(self, *args, **options):
        created = updated = 0
        used_codes = set()
        seen_names = set()
        display_order = 0

        for name in EXAM_NAMES:
            # The source catalogue contains a few repeated labels. Keep the
            # first occurrence so reruns never change an existing exam code.
            if name in seen_names:
                continue
            seen_names.add(name)
            display_order += 1

            base = slugify(name)[:165].strip("-") or f"exam-{display_order}"
            code = base
            suffix = 2
            while code in used_codes:
                code = f"{base[:170-len(str(suffix))]}-{suffix}"
                suffix += 1
            used_codes.add(code)

            category, language, script, interface = infer_metadata(name)
            _, was_created = ExamConfiguration.objects.update_or_create(
                name=name,
                defaults={
                    "code": code,
                    "category": category,
                    "language": language,
                    "script": script,
                    "interface_type": interface,
                    "display_order": display_order,
                },
            )
            created += int(was_created)
            updated += int(not was_created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Exam catalogue ready: {created} created, {updated} refreshed, "
                f"{len(seen_names)} unique exams processed."
            )
        )
