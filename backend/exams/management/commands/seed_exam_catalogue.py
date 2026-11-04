from datetime import date

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from exams.catalogue import EXAM_NAMES, infer_metadata
from exams.models import ExamConfiguration


RKC_PASSAGE_LIBRARY = "https://www.rkcnawada.online/viewrkcpassage.php"


def presentation_defaults(name):
    """Only preconfigure layouts explicitly supported by a reviewed reference label."""
    upper = name.upper()
    if "DELHI POLICE" in upper and ("HC" in upper or "HCM" in upper):
        return {
            "passage_layout": ExamConfiguration.PassageLayout.PARA_TAB,
            "passage_format": ExamConfiguration.PassageFormat.PARAGRAPHS,
            "passage_preserve_tabs": True,
            "presentation_reference_status": ExamConfiguration.PresentationReferenceStatus.REVIEWED,
            "presentation_reference_url": RKC_PASSAGE_LIBRARY,
            "presentation_reference_title": "RKC Nawada passage library — DP HCM Para & Tab Matter",
            "presentation_reference_checked_at": date(2026, 11, 4),
            "presentation_notes": (
                "RKC lists separate Delhi Police HCM files explicitly labelled 'Para & Tab Matter'. "
                "This is a practice-format reference, not an official recruitment authority. "
                "Confirm exact tab stops, font and spacing against the current test instructions."
            ),
        }
    return {
        "passage_layout": ExamConfiguration.PassageLayout.UNCONFIGURED,
        "presentation_reference_status": ExamConfiguration.PresentationReferenceStatus.PENDING,
        "presentation_notes": (
            "No sufficiently specific presentation layout has been verified for this catalogue entry. "
            "Do not infer formatting from its exam name or a different exam's sample."
        ),
    }


class Command(BaseCommand):
    help = "Create or safely update the initial TypingSkillZone exam catalogue."

    def handle(self, *args, **options):
        created = updated = 0
        used_codes = set()
        seen_names = set()
        display_order = 0

        for name in EXAM_NAMES:
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
            defaults = {
                "code": code,
                "category": category,
                "language": language,
                "script": script,
                "interface_type": interface,
                "display_order": display_order,
            }
            defaults.update(presentation_defaults(name))
            _, was_created = ExamConfiguration.objects.update_or_create(name=name, defaults=defaults)
            created += int(was_created)
            updated += int(not was_created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Exam catalogue ready: {created} created, {updated} refreshed, "
                f"{len(seen_names)} unique exams processed."
            )
        )
