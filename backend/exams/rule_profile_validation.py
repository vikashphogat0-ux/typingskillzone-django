"""Strict validation for exam-specific rule profiles.

Missing rules are never inferred. Incomplete profiles remain drafts and
cannot be marked ready for live simulation.
"""
from copy import deepcopy

PROFILE_SCHEMA_VERSION = 1
REQUIRED_SECTIONS = ("identity", "timing", "interaction", "passage", "scoring", "qualification", "provenance")
UNSPECIFIED = "UNSPECIFIED"


def _present(value):
    return value is not None and value != "" and value != UNSPECIFIED


def validate_rule_profile(profile):
    """Return a deterministic audit without mutating or completing the profile."""
    source = deepcopy(profile or {})
    errors, warnings = [], []
    if source.get("schema_version") != PROFILE_SCHEMA_VERSION:
        errors.append("schema_version must be 1")
    for section in REQUIRED_SECTIONS:
        if not isinstance(source.get(section), dict):
            errors.append(f"{section} must be an object")
    if errors:
        return {"ready": False, "errors": errors, "warnings": warnings}

    identity = source["identity"]
    for field in ("profile_id", "exam_name", "language", "script"):
        if not _present(identity.get(field)):
            errors.append(f"identity.{field} is required")

    duration = source["timing"].get("duration_seconds")
    if not isinstance(duration, int) or isinstance(duration, bool) or duration <= 0:
        errors.append("timing.duration_seconds must be a positive integer")

    interaction = source["interaction"]
    for field in ("backspace", "delete", "paste", "copy", "cut", "arrow_navigation", "enter", "space", "tab"):
        if not _present(interaction.get(field)):
            errors.append(f"interaction.{field} must be explicitly configured")

    passage = source["passage"]
    for field in ("source_mode", "format", "layout", "font_family", "font_size_pt", "alignment"):
        if not _present(passage.get(field)):
            errors.append(f"passage.{field} must be explicitly configured")

    scoring = source["scoring"]
    mode = scoring.get("mode")
    if not _present(mode):
        errors.append("scoring.mode is required")
    if not isinstance(scoring.get("error_rules"), dict):
        errors.append("scoring.error_rules must be an object")
    if not isinstance(scoring.get("formula"), dict) or not scoring.get("formula"):
        errors.append("scoring.formula must explicitly define the scoring method")

    qualification = source["qualification"]
    if not isinstance(qualification.get("criteria"), list) or not qualification["criteria"]:
        errors.append("qualification.criteria must contain at least one explicit criterion")
    if not _present(qualification.get("outcome_labels")):
        errors.append("qualification.outcome_labels must define qualified and not-qualified outcomes")

    provenance = source["provenance"]
    if not _present(provenance.get("source_document")):
        errors.append("provenance.source_document is required")
    if provenance.get("notification_dependent") is True:
        warnings.append("Rules depend on the recruitment-cycle notification; verify the active cycle before enabling.")
    if provenance.get("conflict_notes"):
        warnings.append("Source contains a recorded conflict or alternate rule; human resolution is required.")
    if provenance.get("officially_verified") is not True:
        warnings.append("Profile is not marked as verified against the controlling official source.")

    backspace = interaction.get("backspace")
    if backspace == "DISABLED" and interaction.get("allow_backspace") is True:
        errors.append("interaction.allow_backspace conflicts with backspace=DISABLED")
    if backspace in ("FULL", "WORD_ONLY", "WORD_LOCK_AFTER_SEPARATOR") and interaction.get("allow_backspace") is False:
        errors.append("interaction.allow_backspace conflicts with the selected backspace policy")
    if mode == "ERROR_PERCENTAGE" and not _present(scoring.get("error_denominator")):
        errors.append("scoring.error_denominator is required for ERROR_PERCENTAGE")
    if mode == "STROKE_PENALTY" and not _present(scoring.get("penalty_strokes_per_mistake")):
        errors.append("scoring.penalty_strokes_per_mistake is required for STROKE_PENALTY")
    if mode == "FULL_HALF_MISTAKES":
        classes = scoring.get("error_rules", {}).get("classes")
        if not isinstance(classes, dict) or not {"full", "half"}.issubset(classes):
            errors.append("FULL_HALF_MISTAKES requires explicit full and half error classes")

    return {"ready": not errors, "errors": errors, "warnings": warnings}


def profile_readiness(profile):
    audit = validate_rule_profile(profile)
    return {
        "status": "READY" if audit["ready"] else "DRAFT_INCOMPLETE",
        "ready": audit["ready"],
        "error_count": len(audit["errors"]),
        "warning_count": len(audit["warnings"]),
        "errors": audit["errors"],
        "warnings": audit["warnings"],
    }
