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
    if post_presets:
        post_map = {item["id"]: item for item in post_presets}
        if not raw_post:
            raise ValidationError("Select the applicable post for this examination.")
        selected_post = post_map.get(raw_post)
        if selected_post is None:
            raise ValidationError("The selected post is not configured for this examination.")
        selections["post_id"] = selected_post["id"]
        selections["post_snapshot"] = selected_post
        if selected_post.get("requires_eligibility"):
            attested = str(submitted.get("eligibility_confirmed") or "").lower() in {"1", "true", "yes", "on"}
            if not attested:
                raise ValidationError("Confirm that you meet the selected post's eligibility requirement.")
            selections["eligibility_status"] = "CANDIDATE_ATTESTED"
            selections["eligibility_attested"] = True

    return selections


def apply_candidate_selections(snapshot, selections):
    """Apply validated selections to the attempt's private, immutable rules snapshot."""
    snapshot = dict(snapshot)
    selections = dict(selections or {})
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
