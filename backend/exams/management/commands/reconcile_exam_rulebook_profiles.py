"""Safely reconcile the active rulebook catalogue without deleting profile history.

Default mode is a dry run. --execute is required to write. Rows are refreshed
only when they are owned by the Master Exam Rulebook importer. Superseded
importer-owned rows are deactivated, never deleted.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from exams.models import ExamConfiguration
from exams.rulebook_canonical import canonicalize, with_internal_rulebook_basis
from exams.management.commands.import_exam_rulebook_profiles import build_draft_defaults

SOURCE_PREFIX = "Internal rule profile: Master Exam Rulebook"


def _source_profile_id(exam):
    scoring = exam.scoring_rules or {}
    configuration = scoring.get("profile_configuration") or {}
    return configuration.get("source_profile_id") or scoring.get("source_profile_id")


class Command(BaseCommand):
    help = "Dry-run or explicitly execute safe reconciliation of the 161 independent rulebook profiles."

    def add_arguments(self, parser):
        parser.add_argument("json_path", help="Path to exam_rulebook_profiles.json")
        parser.add_argument("--expected-count", type=int, default=161)
        parser.add_argument("--execute", action="store_true", help="Apply the preflighted plan; without this flag no rows are changed.")

    def handle(self, *args, **options):
        path = Path(options["json_path"]).expanduser()
        if not path.is_file():
            raise CommandError(f"Rulebook JSON file not found: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CommandError(f"Could not read valid UTF-8 rulebook JSON: {exc}") from exc

        raw_profiles = payload.get("profiles")
        if payload.get("schema_version") != 1 or not isinstance(raw_profiles, list):
            raise CommandError("Unsupported rulebook JSON schema.")
        if len(raw_profiles) != options["expected_count"]:
            raise CommandError(
                f"Expected {options['expected_count']} source profiles; found {len(raw_profiles)}. No changes made."
            )

        profiles = canonicalize(raw_profiles)
        if len(profiles) != options["expected_count"]:
            raise CommandError("Independent source profile count does not match expected count.")
        ids = [profile["profile_id"] for profile in profiles]
        if len(set(ids)) != len(ids):
            raise CommandError("Source profile IDs must be unique.")

        prepared = []
        codes = set()
        errors = []
        for profile in profiles:
            code = slugify(profile["profile_id"])[:180]
            if not code or code in codes:
                errors.append(f"Invalid or duplicate generated profile code: {code!r}")
                continue
            codes.add(code)
            defaults = {"code": code, **build_draft_defaults(profile)}
            defaults["scoring_rules"] = with_internal_rulebook_basis(defaults.get("scoring_rules"))
            try:
                ExamConfiguration(**defaults).full_clean(validate_unique=False)
            except Exception as exc:
                errors.append(f"{profile['profile_id']}: {exc}")
            prepared.append((profile, code, defaults))
        if errors:
            raise CommandError("Preflight failed; no changes made:\n" + "\n".join(errors))

        owned = list(ExamConfiguration.objects.filter(source_title__startswith=SOURCE_PREFIX))
        owned_by_code = {exam.code: exam for exam in owned}
        for _, code, _ in prepared:
            existing = ExamConfiguration.objects.filter(code=code).first()
            if existing and code not in owned_by_code:
                raise CommandError(
                    f"Profile code {code!r} is already owned by a non-rulebook record. No changes made."
                )

        current_codes = {code for _, code, _ in prepared}
        stale = [exam for exam in owned if exam.code not in current_codes]
        create_count = sum(code not in owned_by_code for code in current_codes)
        refresh_count = len(current_codes) - create_count
        deactivate_count = sum(exam.is_active for exam in stale)
        self.stdout.write(
            f"Preflight OK: source_profiles={len(profiles)}, create={create_count}, "
            f"refresh={refresh_count}, activate_or_keep={len(profiles)}, "
            f"deactivate_superseded={deactivate_count}, delete=0."
        )
        if not options["execute"]:
            self.stdout.write(self.style.WARNING("DRY RUN ONLY. No database changes made. Add --execute to apply this exact plan."))
            return

        created = refreshed = deactivated = 0
        with transaction.atomic():
            # Recheck ownership and codes inside the write transaction.
            for profile, code, defaults in prepared:
                exam = ExamConfiguration.objects.filter(code=code).first()
                if exam is None:
                    ExamConfiguration.objects.create(**defaults)
                    created += 1
                else:
                    if not (exam.source_title or "").startswith(SOURCE_PREFIX):
                        raise CommandError(f"Ownership changed for {code}; transaction rolled back.")
                    for field, value in defaults.items():
                        setattr(exam, field, value)
                    exam.save()
                    refreshed += 1
            for exam in stale:
                current = ExamConfiguration.objects.select_for_update().get(pk=exam.pk)
                if (current.source_title or "").startswith(SOURCE_PREFIX) and current.is_active:
                    current.is_active = False
                    current.save(update_fields=["is_active", "updated_at"])
                    deactivated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Reconciliation complete: created={created}, refreshed={refreshed}, "
            f"deactivated={deactivated}, deleted=0. Learner attempts and historical snapshots were not modified."
        ))
