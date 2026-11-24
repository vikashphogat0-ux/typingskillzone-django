"""Import rulebook entries as inactive, source-preserving draft exam profiles.

The importer deliberately does not translate prose into executable scoring or
qualification logic. Admin review is required before activation.
"""
import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from exams.catalogue import infer_metadata
from exams.models import ExamConfiguration


def _source_lines(profile, prefix):
    return [line for line in profile.get("source_text", []) if line.startswith(prefix)]


def _first_duration_seconds(lines):
    for line in lines:
        match = re.search(r"(\d+)\s*minutes?", line, re.IGNORECASE)
        if match:
            return int(match.group(1)) * 60
    return None


def _backspace_policy(lines):
    text = " ".join(lines).lower()
    if re.search(r"backspace\s+(?:is\s+)?disabled", text):
        return ExamConfiguration.BackspacePolicy.DISABLED
    if re.search(r"backspace\s+is\s+allowed", text):
        return ExamConfiguration.BackspacePolicy.FULL
    if "backspace behavior depends" in text or "backspace behaviour depends" in text:
        return ExamConfiguration.BackspacePolicy.NOT_SPECIFIED
    return ExamConfiguration.BackspacePolicy.NOT_SPECIFIED


def build_draft_defaults(profile):
    """Extract only safe identity/timing/input hints; preserve all rule prose."""
    name = profile.get("name") or profile.get("source_heading") or ""
    lines = profile.get("source_text") or []
    all_text = " ".join(lines)
    category, language, script, interface = infer_metadata(name)
    if "english" in name.lower():
        language = "ENGLISH"
    elif "hindi" in name.lower() or any(token in name.upper() for token in ("KURTIDEV", "KRUTIDEV", "MANGAL")):
        language = "HINDI"
    elif "marathi" in name.lower():
        language = "MARATHI"

    duration = _first_duration_seconds(_source_lines(profile, "Duration & Target:"))
    if duration is None:
        duration = _first_duration_seconds(lines)

    # Store source wording verbatim. It is intentionally not executable.
    scoring_source = [line for line in lines if "Formula:" in line or "Formula" in line or line.startswith('"')]
    qualification_source = [
        line for line in lines
        if line.startswith("Qualifying Criteria") or line.startswith("Qualifying Criteria &")
        or line.startswith("WPM & Error Formula") or line.startswith("Marks")
        or line.startswith("Accuracy %") or line.startswith("(Where a ")
    ]
    interaction_source = _source_lines(profile, "Interface, Passage & Keyboard Rules:")

    return {
        "name": name,
        "category": category,
        "language": language,
        "script": script,
        "interface_type": interface,
        "duration_seconds": duration,
        "backspace_policy": _backspace_policy(interaction_source),
        "allow_backspace": _backspace_policy(interaction_source) != ExamConfiguration.BackspacePolicy.DISABLED,
        "passage_source_mode": ExamConfiguration.PassageSourceMode.UNSPECIFIED,
        "passage_layout": ExamConfiguration.PassageLayout.UNCONFIGURED,
        "passage_format": ExamConfiguration.PassageFormat.CUSTOM,
        "scoring_mode": ExamConfiguration.ScoringMode.GENERIC,
        "error_rules": {
            "source_text": lines,
            "executable": False,
        },
        "scoring_rules": {
            "source_formula_text": scoring_source,
            "executable": False,
        },
        "qualification_rules": {
            "source_criteria_text": qualification_source,
            "executable": False,
        },
        "verification_status": ExamConfiguration.Verification.UNVERIFIED,
        "source_title": "Master Exam Rulebook — source-preserved draft",
        "rule_notes": (
            "Imported from source profile " + str(profile.get("number")) + " / "
            + str(profile.get("profile_id")) + ". Source text is preserved in error_rules, "
            "scoring_rules and qualification_rules. These values are NOT executable rules. "
            "Review notification-dependent wording, conflicts, and exact scoring before activation.\n\n"
            + "\n".join(lines)
        ),
        "is_active": False,
    }


class Command(BaseCommand):
    help = "Import rulebook entries as inactive draft profiles without overwriting existing settings."

    def add_arguments(self, parser):
        parser.add_argument("json_path", help="Path to exam_rulebook_profiles.json")
        parser.add_argument("--expected-count", type=int, default=161)

    def handle(self, *args, **options):
        path = Path(options["json_path"]).expanduser()
        if not path.is_file():
            raise CommandError(f"JSON file not found: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CommandError(f"Could not read valid UTF-8 JSON: {exc}") from exc

        profiles = payload.get("profiles")
        expected = options["expected_count"]
        if payload.get("schema_version") != 1 or not isinstance(profiles, list):
            raise CommandError("Unsupported rulebook JSON schema.")
        if expected and len(profiles) != expected:
            raise CommandError(f"Expected {expected} profiles; found {len(profiles)}. No rows imported.")
        ids = [item.get("profile_id") for item in profiles]
        if any(not value for value in ids) or len(set(ids)) != len(ids):
            raise CommandError("Every profile must have a unique, non-empty profile_id. No rows imported.")

        created = preserved = 0
        for profile in profiles:
            profile_id = profile["profile_id"]
            defaults = build_draft_defaults(profile)
            # The stable profile_id is the unique code. Existing rows are never overwritten.
            _, was_created = ExamConfiguration.objects.get_or_create(
                code=slugify(profile_id)[:180],
                defaults={"code": slugify(profile_id)[:180], **defaults},
            )
            created += int(was_created)
            preserved += int(not was_created)

        self.stdout.write(self.style.SUCCESS(
            f"Rulebook import complete: {created} inactive drafts created; "
            f"{preserved} existing profiles preserved; {len(profiles)} source entries processed."
        ))
        self.stdout.write(self.style.WARNING(
            "Imported drafts are inactive and use non-executable source text. "
            "Do not activate until each profile has been reviewed and mapped to its exact exam rules."
        ))
