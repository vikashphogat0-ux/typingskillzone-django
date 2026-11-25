"""Profile-driven candidate selector validation and snapshot helpers.

Selector choices are read from the exam's existing JSON profile configuration.
No independent option catalogue or inferred eligibility rules are introduced.
"""
from django.core.exceptions import ValidationError


def selector_configuration(exam):
    scoring = exam.scoring_rules or {}
    profile = scoring.get("profile_configuration") or {}
    variants = profile.get("variants") or []
    caps = {}
    for key in ("category_error_caps", "normal_error_caps", "higher_error_caps"):
        values = scoring.get(key) or {}
        if isinstance(values, dict):
            caps.update(values)
    configured_limits = profile.get("category_limits") or {}
    if isinstance(configured_limits, dict):
        caps.update({key: value for key, value in configured_limits.items() if isinstance(value, (int, float))})
    categories = [key for key in caps if key not in {"OTHER", "OTHER_RESERVED"}]
    return {
        "categories": [{"id": key, "label": key} for key in categories],
        "variants": [item for item in variants if isinstance(item, dict) and item.get("id")],
        "post_presets": [item for item in (profile.get("post_presets") or []) if isinstance(item, dict) and item.get("id")],
    }


def validate_candidate_selections(exam, submitted):
    """Validate candidate input strictly against options stored in this exam profile."""
    config = selector_configuration(exam)
    scoring = exam.scoring_rules or {}
    formula = scoring.get("formula")
    selections = {}
    category_options = {item["id"] for item in config["categories"]}
    category_required = bool(category_options) and formula in {
        "SSC_CGL_2025_DEST", "SSC_CGL_2025_VH_DEST",
        "SSC_CHSL_2025_ENGLISH", "SSC_CHSL_2025_HINDI",
        "SSC_CHSL_2025_HINDI_KRUTIDEV", "SSC_CHSL_2025_HINDI_MANGAL",
    }
    raw_category = (submitted.get("candidate_category") or "").strip().upper()
    if category_required:
        if not raw_category:
            raise ValidationError("Select your candidate category before starting this examination.")
        if raw_category not in category_options:
            raise ValidationError("The selected candidate category is not configured for this examination.")
        selections["candidate_category"] = raw_category
    elif raw_category:
        if raw_category not in category_options:
            raise ValidationError("The selected candidate category is not configured for this examination.")
        selections["candidate_category"] = raw_category

    variants = config["variants"]
    raw_variant = (submitted.get("candidate_variant") or submitted.get("variant_id") or "").strip()
    selected_variant = None
    if variants:
        variant_map = {item["id"]: item for item in variants}
        if len(variants) == 1 and variants[0].get("locked"):
            selected_variant = variants[0]
            if raw_variant and raw_variant != selected_variant["id"]:
                raise ValidationError("This examination variant is fixed by the configured profile.")
        else:
            if not raw_variant:
                raise ValidationError("Select the applicable examination standard or variant.")
            selected_variant = variant_map.get(raw_variant)
            if selected_variant is None:
                raise ValidationError("The selected examination standard or variant is invalid.")
        selections["variant_id"] = selected_variant["id"]
        selections["variant_label"] = selected_variant.get("label") or selected_variant["id"]
        if selected_variant.get("standard_type"):
            selections["standard_type"] = str(selected_variant["standard_type"]).upper()
        if selected_variant.get("duration_seconds") is not None:
            try:
                duration = int(selected_variant["duration_seconds"])
            except (TypeError, ValueError):
                raise ValidationError("The configured variant has an invalid duration.")
            if duration <= 0:
                raise ValidationError("The configured variant has an invalid duration.")
            selections["duration_seconds"] = duration
        if selected_variant.get("requires_post_eligibility") or selected_variant.get("requires_eligibility"):
            attested = str(submitted.get("eligibility_confirmed") or submitted.get("eligibility_attested") or "").lower() in {"1", "true", "yes", "on"}
            if not attested:
                raise ValidationError("Confirm that you meet the eligibility requirement for the selected variant.")
            selections["eligibility_status"] = "CANDIDATE_ATTESTED"
            selections["eligibility_attested"] = True

    post_presets = config["post_presets"]
    raw_post = (submitted.get("candidate_post") or submitted.get("post_id") or "").strip()
    post_required = bool(selected_variant and (
        selected_variant.get("requires_post_eligibility")
        or str(selected_variant.get("standard_type") or "").upper() == "HIGHER"
    ))
    if raw_post or (post_presets and post_required):
        post_map = {item["id"]: item for item in post_presets}
        if not raw_post:
            raise ValidationError("Select the eligible post for the higher examination standard.")
        selected_post = post_map.get(raw_post)
        if selected_post is None:
            raise ValidationError("The selected post is not configured for this examination.")
        selections["post_id"] = selected_post["id"]
        selections["post_snapshot"] = selected_post
        if selected_post.get("requires_eligibility") and not selections.get("eligibility_attested"):
            attested = str(submitted.get("eligibility_confirmed") or "").lower() in {"1", "true", "yes", "on"}
            if not attested:
                raise ValidationError("Confirm that you meet the selected post's eligibility requirement.")
            selections["eligibility_status"] = "CANDIDATE_ATTESTED"
            selections["eligibility_attested"] = True
    elif post_presets and not post_required:
        # A post is optional for standards whose rulebook does not depend on post eligibility.
        pass

    return selections


def apply_candidate_selections(snapshot, selections):
    """Apply validated selections to the attempt's private, immutable rules snapshot."""
    snapshot = dict(snapshot)
    selections = dict(selections or {})
    snapshot["candidate_selector_configuration"] = selector_configuration_from_snapshot(snapshot)
    snapshot["candidate_selectors"] = selections
    if selections.get("candidate_category"):
        snapshot["candidate_category"] = selections["candidate_category"]
    scoring = dict(snapshot.get("scoring_rules") or {})
    if selections.get("standard_type"):
        scoring["standard_type"] = selections["standard_type"]
    if selections.get("duration_seconds"):
        snapshot["selected_variant_duration_seconds"] = selections["duration_seconds"]
    snapshot["scoring_rules"] = scoring
    return snapshot


def selector_configuration_from_snapshot(snapshot):
    """Capture the exact options used to validate this attempt, independent of later edits."""
    scoring = snapshot.get("scoring_rules") or {}
    profile = scoring.get("profile_configuration") or {}
    caps = {}
    for key in ("category_error_caps", "normal_error_caps", "higher_error_caps"):
        values = scoring.get(key) or {}
        if isinstance(values, dict):
            caps.update(values)
    limits = profile.get("category_limits") or {}
    if isinstance(limits, dict):
        caps.update({key: value for key, value in limits.items() if isinstance(value, (int, float))})
    return {
        "categories": [key for key in caps if key not in {"OTHER", "OTHER_RESERVED"}],
        "variants": [dict(item) for item in (profile.get("variants") or []) if isinstance(item, dict) and item.get("id")],
        "post_presets": [dict(item) for item in (profile.get("post_presets") or []) if isinstance(item, dict) and item.get("id")],
        "category_required": bool(caps) and scoring.get("formula") in {
            "SSC_CGL_2025_DEST", "SSC_CGL_2025_VH_DEST",
            "SSC_CHSL_2025_ENGLISH", "SSC_CHSL_2025_HINDI",
            "SSC_CHSL_2025_HINDI_KRUTIDEV", "SSC_CHSL_2025_HINDI_MANGAL",
        },
    }


def validate_candidate_snapshot(snapshot):
    """Reject missing or internally inconsistent selector state before official scoring."""
    config = snapshot.get("candidate_selector_configuration")
    if not isinstance(config, dict):
        return  # Legacy attempts predate persisted selector schemas.
    selected = snapshot.get("candidate_selectors")
    if not isinstance(selected, dict):
        raise ValidationError("Candidate selections are missing from this examination attempt.")
    if config.get("category_required"):
        category = selected.get("candidate_category")
        if not category or category not in set(config.get("categories") or []):
            raise ValidationError("Candidate category selection is missing or inconsistent; this attempt cannot be scored.")
    variants = config.get("variants") or []
    if variants:
        variant = next((item for item in variants if item.get("id") == selected.get("variant_id")), None)
        if variant is None:
            raise ValidationError("The saved examination standard is missing or inconsistent; this attempt cannot be scored.")
        if variant.get("requires_post_eligibility") or str(variant.get("standard_type") or "").upper() == "HIGHER":
            posts = config.get("post_presets") or []
            if posts and not any(item.get("id") == selected.get("post_id") for item in posts):
                raise ValidationError("The saved eligible post is missing or inconsistent; this attempt cannot be scored.")
        if variant.get("requires_post_eligibility") or variant.get("requires_eligibility"):
            if selected.get("eligibility_attested") is not True or selected.get("eligibility_status") != "CANDIDATE_ATTESTED":
                raise ValidationError("The required candidate eligibility attestation is missing; this attempt cannot be scored.")
    return selected
