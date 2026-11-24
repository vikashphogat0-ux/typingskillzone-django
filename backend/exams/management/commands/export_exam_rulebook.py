"""Export the supplied Master Exam Rulebook into a lossless profile catalogue.

This command does not interpret or activate rules. It preserves source wording,
duplicate profile headings, ordering, and caveats for a later reviewed mapping.
"""
import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify


PROFILE_START = "Exam Pattern & Qualifying Nature:"


def extract_profile_blocks(paragraphs):
    """Extract heading + source paragraphs without normalizing their contents."""
    lines = [str(value).strip() for value in paragraphs if str(value).strip()]
    starts = [index for index, value in enumerate(lines) if value.startswith(PROFILE_START)]
    profiles = []
    for number, start in enumerate(starts, 1):
        if start == 0:
            raise ValueError(f"Profile block {number} has no preceding profile heading.")
        end = starts[number] if number < len(starts) else len(lines)
        heading = lines[start - 1]
        body = lines[start:end]
        profile_id = slugify(heading) or f"profile-{number}"
        profiles.append({
            "number": number,
            "profile_id": f"{profile_id}-{number:03d}",
            "name": heading,
            "source_heading": heading,
            "source_text": body,
        })
    return profiles


class Command(BaseCommand):
    help = "Export the Master Exam Rulebook DOCX as a lossless JSON catalogue."

    def add_arguments(self, parser):
        parser.add_argument("docx_path", help="Path to Master_Exam_Rulebook_Typing_DEST.docx")
        parser.add_argument("--output", default="exam_rulebook_profiles.json")
        parser.add_argument("--expected-count", type=int, default=161)

    def handle(self, *args, **options):
        source_path = Path(options["docx_path"]).expanduser()
        if not source_path.is_file():
            raise CommandError(f"Rulebook file not found: {source_path}")
        try:
            from docx import Document
        except ImportError as exc:
            raise CommandError("python-docx is required to read the rulebook DOCX.") from exc

        document = Document(str(source_path))
        profiles = extract_profile_blocks(paragraph.text for paragraph in document.paragraphs)
        expected = options["expected_count"]
        if expected and len(profiles) != expected:
            raise CommandError(
                f"Expected {expected} profile blocks but extracted {len(profiles)}. "
                "No output was written; inspect the source structure before proceeding."
            )

        payload = {
            "schema_version": 1,
            "source_document": source_path.name,
            "source_consolidation_notice": (
                "Source-consolidation edition. This export preserves source wording; "
                "it does not certify current official recruitment-cycle rules."
            ),
            "profile_count": len(profiles),
            "profiles": profiles,
        }
        output_path = Path(options["output"]).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(
            f"Exported {len(profiles)} source profile blocks to {output_path}. "
            "No exam configuration was changed."
        ))
