"""Import rulebook entries as inactive, source-preserving draft exam profiles.

Only literal, unambiguous source statements are mapped to structured fields.
Ambiguous, typical, cycle-dependent, or conditional rules remain unresolved.
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


def _explicit_number(pattern, text, cast=int):
    match = re.search(pattern, text, re.IGNORECASE)
    return cast(match.group(1)) if match else None


def _backspace_policy(lines):
    text = " ".join(lines).lower()
    if re.search(r"backspace\s+(?:is\s+)?disabled", text):
        return ExamConfiguration.BackspacePolicy.DISABLED
    if re.search(r"backspace\s+is\s+allowed", text):
        return ExamConfiguration.BackspacePolicy.FULL
    if "backspace behavior depends" in text or "backspace behaviour depends" in text:
        return ExamConfiguration.BackspacePolicy.NOT_SPECIFIED
    return ExamConfiguration.BackspacePolicy.NOT_SPECIFIED


def _explicit_interaction_defaults(text):
    """Return only interaction settings directly stated in source wording."""
    values = {}
    lower = text.lower()
    if re.search(r"copy\s*/\s* paste.*disabled|copy/paste disabled|copy and paste.*disabled", lower):
        values.update(allow_copy=False, allow_paste=False)
    elif re.search(r"copy\s*/\s* paste.*allowed|copy/paste allowed|copy and paste.*allowed", lower):
        values.update(allow_copy=True, allow_paste=True)
    if re.search(r"delete key.*disabled|deletion.*disabled", lower):
        values["allow_delete"] = False
    elif re.search(r"delete key.*allowed|deletion.*allowed", lower):
        values["allow_delete"] = True
    if re.search(r"arrow keys?.*disabled|arrow navigation.*disabled", lower):
        values["allow_arrow_navigation"] = False
    elif re.search(r"arrow keys?.*allowed|arrow navigation.*allowed", lower):
        values["allow_arrow_navigation"] = True
    return values


def _explicit_keyboard_layout(name, text):
    combined = (name + " " + text).lower()
    if "kruti dev 010" in combined or "krutidev 010" in combined:
        return "Kruti Dev 010 Remington"
    if "remington gail" in combined or "mangal-gail" in combined or "mangal gail" in combined:
        return "Remington Gail"
    if "inscript" in combined:
        return "Inscript"
    if "qwerty" in combined:
        return "QWERTY"
    return ""


def build_draft_defaults(profile):
    """Extract safe explicit hints while preserving the complete source prose."""
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

    interaction_lines = _source_lines(profile, "Interface, Passage & Keyboard Rules:")
    interaction_text = " ".join(interaction_lines)
    backspace = _backspace_policy(interaction_lines)
    keyboard_layout = _explicit_keyboard_layout(name, interaction_text)

    # Extract a speed only when the source gives one single explicit WPM value.
    wpm_values = set(re.findall(r"(\d+(?:\.\d+)?)\s*WPM", " ".join(_source_lines(profile, "Duration & Target:")), re.IGNORECASE))
    minimum_wpm = float(next(iter(wpm_values))) if len(wpm_values) == 1 else None
    required_keystrokes = _explicit_number(r"(\d[\d,]*)\s*key\s*depressions", " ".join(_source_lines(profile, "Duration & Target:")), cast=lambda value: int(value.replace(",", "")))
    if required_keystrokes is not None:
        required_keystrokes = int(str(required_keystrokes).replace(",", ""))

    is_tcs = "tcs ion" in interaction_text.lower() or "tcs-style" in interaction_text.lower()
    passage_layout = ExamConfiguration.PassageLayout.TCS if is_tcs else ExamConfiguration.PassageLayout.UNCONFIGURED
    passage_format = ExamConfiguration.PassageFormat.TCS if is_tcs else ExamConfiguration.PassageFormat.CUSTOM
    source_mode = ExamConfiguration.PassageSourceMode.SCREEN if is_tcs else ExamConfiguration.PassageSourceMode.UNSPECIFIED

    scoring_source = [line for line in lines if "Formula:" in line or "Formula" in line or line.startswith('"')]
    qualification_source = [
        line for line in lines
        if line.startswith("Qualifying Criteria") or line.startswith("Qualifying Criteria &")
        or line.startswith("WPM & Error Formula") or line.startswith("Marks")
        or line.startswith("Accuracy %") or line.startswith("(Where a ")
    ]

    defaults = {
        "name": name,
        "category": category,
        "language": language,
        "script": script,
        "interface_type": interface,
        "duration_seconds": duration,
        "minimum_wpm": minimum_wpm,
        "required_keystrokes": required_keystrokes,
        "keyboard_layout": keyboard_layout,
        "backspace_policy": backspace,
        "allow_backspace": backspace != ExamConfiguration.BackspacePolicy.DISABLED,
        "passage_source_mode": source_mode,
        "passage_layout": passage_layout,
        "passage_format": passage_format,
        "scoring_mode": ExamConfiguration.ScoringMode.GENERIC,
        "error_rules": {"source_text": lines, "executable": False},
        "scoring_rules": {"source_formula_text": scoring_source, "executable": False},
        "qualification_rules": {"source_criteria_text": qualification_source, "executable": False},
        "verification_status": ExamConfiguration.Verification.UNVERIFIED,
        "source_title": "Master Exam Rulebook — source-preserved draft",
        "rule_notes": (
            "Imported from source profile " + str(profile.get("number")) + " / "
            + str(profile.get("profile_id")) + ". Extracted values are source hints only; "
            "scoring, error classification and qualification remain non-executable until reviewed.\n\n"
            + "\n".join(lines)
        ),
        "is_active": False,
    }
    defaults.update(_explicit_interaction_defaults(interaction_text))
    return defaults


class Command(BaseCommand):
    help = "Import rulebook entries as inactive draft profiles without overwriting existing settings."

    def add_arguments(self, parser):
        parser.add_argument("json_path", help="Path to exam_rulebook_profiles.json")
        parser.add_argument("--expected-count", type=int, default=161)
        parser.add_argument("--refresh-existing-drafts", action="store_true", help="Refresh only inactive rows previously imported from this rulebook; never touch active or manually sourced profiles.")

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
            code = slugify(profile["profile_id"])[:180]
            defaults = {"code": code, **build_draft_defaults(profile)}
            exam, was_created = ExamConfiguration.objects.get_or_create(code=code, defaults=defaults)
            if was_created:
                created += 1
            elif options["refresh_existing_drafts"] and not exam.is_active and exam.source_title == "Master Exam Rulebook — source-preserved draft":
                for field, value in defaults.items():
                    setattr(exam, field, value)
                exam.save()
                preserved += 1
            else:
                preserved += 1

        self.stdout.write(self.style.SUCCESS(
            f"Rulebook import complete: {created} inactive drafts created; "
            f"{preserved} existing profiles preserved; {len(profiles)} source entries processed."
        ))
        self.stdout.write(self.style.WARNING(
            "Imported drafts remain inactive. Extracted hints are not official verification or executable scoring. "
            "Existing rows are only refreshed when --refresh-existing-drafts is supplied and the row is inactive with the exact importer source marker."
        ))
