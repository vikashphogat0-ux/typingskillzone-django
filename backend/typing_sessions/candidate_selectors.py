"""Profile-driven candidate selector validation and snapshot helpers.

Selector choices are read from the exam's existing JSON profile configuration.
No independent option catalogue or inferred eligibility rules are introduced.
"""
from django.core.exceptions import ValidationError


def _configured_category_values(exam):
    scoring = exam.scoring_rules or {}
    qualification = exam.qualification_rules or {}
    values = set()
    criteria = qualification.get("criteria", []) if isinstance(qualification, dict) else []
    for criterion in criteria:
        if isinstance(criterion, dict) and isinstance(criterion.get("category_values"), dict):
            values.update(
                key for key, value in criterion["category_values"].items()
                if isinstance(key, str) and key and isinstance(value, (int, float)) and not isinstance(value, bool)
            )
    for key in ("category_error_caps", "normal_error_caps", "higher_error_caps"):
        configured = scoring.get(key) or {}
        if isinstance(configured, dict):
            values.update(
                category for category, limit in configured.items()
                if isinstance(category, str) and category and isinstance(limit, (int, float)) and not isinstance(limit, bool)
            )
    profile = scoring.get("profile_configuration") or {}
    configured_limits = profile.get("category_limits") or {}
    if isinstance(configured_limits, dict):
        values.update(
            category for category, limit in configured_limits.items()
            if isinstance(category, str) and category and isinstance(limit, (int, float)) and not isinstance(limit, bool)
        )
    return values


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
    categories = sorted(_configured_category_values(exam) - {"OTHER", "OTHER_RESERVED"})
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
    qualification = exam.qualification_rules or {}
    has_category_threshold = any(
        isinstance(item, dict) and isinstance(item.get("category_values"), dict)
        for item in qualification.get("criteria", [])
    ) if isinstance(qualification, dict) else False
    category_required = bool(category_options) and (
        has_category_threshold or formula in {
            "SSC_CGL_2025_DEST", "SSC_CGL_2025_VH_DEST",
            "SSC_CHSL_2025_ENGLISH", "SSC_CHSL_2025_HINDI",
            "SSC_CHSL_2025_HINDI_KRUTIDEV", "SSC_CHSL_2025_HINDI_MANGAL",
        }
    )
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



def _deep_merge(base, override):
    """Merge trusted profile dictionaries without mutating either input."""
    result = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


_RUNTIME_ROOT_FIELDS = {
    "allow_backspace", "backspace_policy", "allow_delete",
    "allow_arrow_navigation", "allow_paste", "allow_copy", "allow_cut",
    "enter_behavior", "space_behavior", "tab_behavior", "keyboard_layout",
    "text_encoding", "passage_source_mode", "passage_layout", "passage_format",
    "passage_font_family", "passage_font_size_pt", "passage_line_height",
    "passage_alignment", "passage_preserve_tabs", "passage_tab_size",
    "minimum_wpm", "required_keystrokes", "strokes_per_word",
    "error_allowance_percent", "mistake_penalty_strokes", "trial_seconds",
    "review_seconds", "correction_seconds", "transcription_seconds",
    "allow_passage_repeat", "scoring_mode", "duration_seconds",
}
_PRESET_METADATA_FIELDS = {
    "id", "label", "name", "description", "standard_type",
    "requires_post_eligibility", "requires_eligibility",
    "eligibility_status", "eligibility_note", "locked",
}


def _apply_preset(snapshot, preset, *, kind):
    """Apply profile-owned preset values to the exact keys consumed at runtime."""
    if not isinstance(preset, dict):
        return {}, {}
    root_overrides = {}
    scoring_overrides = {}
    error_overrides = {}
    qualification_overrides = {}
    explicit = preset.get("runtime_overrides", preset.get("overrides", {})) or {}
    if not isinstance(explicit, dict):
        raise ValidationError(f"The configured {kind} preset has invalid runtime overrides.")

    for key, value in explicit.items():
        if key in _RUNTIME_ROOT_FIELDS:
            root_overrides[key] = value
        elif key == "scoring_rules" and isinstance(value, dict):
            scoring_overrides = _deep_merge(scoring_overrides, value)
        elif key == "error_rules" and isinstance(value, dict):
            error_overrides = _deep_merge(error_overrides, value)
        elif key == "qualification_rules" and isinstance(value, dict):
            qualification_overrides = _deep_merge(qualification_overrides, value)
        else:
            raise ValidationError(
                f"The configured {kind} preset contains an unsupported runtime override: {key}."
            )

    for key, target in (
        ("scoring_overrides", scoring_overrides),
        ("error_overrides", error_overrides),
        ("qualification_overrides", qualification_overrides),
    ):
        values = preset.get(key) or {}
        if values and not isinstance(values, dict):
            raise ValidationError(f"The configured {kind} preset has invalid {key.replace('_', ' ')}.")
        if values:
            target.update(_deep_merge(target, values))

    base_scoring = snapshot.get("scoring_rules") or {}
    for key, value in preset.items():
        if key in _RUNTIME_ROOT_FIELDS and key != "duration_seconds":
            root_overrides[key] = value
        elif key in base_scoring and key not in _PRESET_METADATA_FIELDS:
            scoring_overrides[key] = value

    if preset.get("duration_seconds") is not None:
        try:
            duration = int(preset["duration_seconds"])
        except (TypeError, ValueError):
            raise ValidationError(f"The configured {kind} preset has an invalid duration.")
        if duration <= 0:
            raise ValidationError(f"The configured {kind} preset has an invalid duration.")
        root_overrides["duration_seconds"] = duration

    for key, value in root_overrides.items():
        snapshot[key] = value
    if scoring_overrides:
        snapshot["scoring_rules"] = _deep_merge(snapshot.get("scoring_rules") or {}, scoring_overrides)
    if error_overrides:
        snapshot["error_rules"] = _deep_merge(snapshot.get("error_rules") or {}, error_overrides)
    if qualification_overrides:
        snapshot["qualification_rules"] = _deep_merge(
            snapshot.get("qualification_rules") or {}, qualification_overrides
        )
    return {
        "root": root_overrides,
        "scoring_rules": scoring_overrides,
        "error_rules": error_overrides,
        "qualification_rules": qualification_overrides,
    }, dict(preset)


def _runtime_contract(snapshot):
    """Return the immutable settings consumed by the live engine and scorer."""
    keys = sorted(_RUNTIME_ROOT_FIELDS - {"duration_seconds"})
    return {
        "root": {key: snapshot.get(key) for key in keys if key in snapshot},
        "duration_seconds": snapshot.get("duration_seconds"),
        "error_rules": snapshot.get("error_rules") or {},
        "scoring_rules": snapshot.get("scoring_rules") or {},
        "qualification_rules": snapshot.get("qualification_rules") or {},
    }


def _contract_digest(snapshot):
    import hashlib
    import json

    payload = json.dumps(_runtime_contract(snapshot), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def apply_candidate_selections(snapshot, selections):
    """Resolve validated category, variant and post choices into runtime rules."""
    snapshot = dict(snapshot)
    selections = dict(selections or {})
    snapshot["candidate_selector_configuration"] = selector_configuration_from_snapshot(snapshot)
    snapshot["candidate_selectors"] = selections

    if selections.get("candidate_category"):
        snapshot["candidate_category"] = selections["candidate_category"]

    scoring = dict(snapshot.get("scoring_rules") or {})
    if selections.get("standard_type"):
        scoring["standard_type"] = selections["standard_type"]
    snapshot["scoring_rules"] = scoring

    selector_config = snapshot["candidate_selector_configuration"]
    variant = next(
        (item for item in selector_config.get("variants", [])
         if item.get("id") == selections.get("variant_id")),
        None,
    )
    post = next(
        (item for item in selector_config.get("post_presets", [])
         if item.get("id") == selections.get("post_id")),
        None,
    )
    applied = {"variant": {}, "post": {}}
    if variant:
        applied["variant"], _ = _apply_preset(snapshot, variant, kind="variant")
    if post:
        applied["post"], _ = _apply_preset(snapshot, post, kind="post")

    scoring = dict(snapshot.get("scoring_rules") or {})
    if selections.get("standard_type"):
        scoring["standard_type"] = selections["standard_type"]
    snapshot["scoring_rules"] = scoring

    effective_duration = snapshot.get("duration_seconds")
    if effective_duration is None and selections.get("duration_seconds") is not None:
        effective_duration = int(selections["duration_seconds"])
    if effective_duration is not None:
        snapshot["duration_seconds"] = int(effective_duration)
        snapshot["selected_variant_duration_seconds"] = int(effective_duration)

    snapshot["resolved_candidate_configuration"] = {
        "schema_version": 1,
        "variant_id": selections.get("variant_id"),
        "post_id": selections.get("post_id"),
        "standard_type": scoring.get("standard_type"),
        "duration_seconds": snapshot.get("duration_seconds"),
        "variant_snapshot": dict(variant) if variant else None,
        "post_snapshot": dict(post) if post else None,
        "applied_overrides": applied,
    }
    snapshot["resolved_candidate_configuration"]["runtime_contract_sha256"] = _contract_digest(snapshot)
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
    category_values = set(
        key for criterion in (snapshot.get("qualification_rules") or {}).get("criteria", [])
        if isinstance(criterion, dict) and isinstance(criterion.get("category_values"), dict)
        for key, value in criterion["category_values"].items()
        if isinstance(key, str) and key and isinstance(value, (int, float)) and not isinstance(value, bool)
    )
    category_values.update(
        key for key, value in caps.items()
        if isinstance(key, str) and key and isinstance(value, (int, float)) and not isinstance(value, bool)
    )
    return {
        "categories": sorted(category_values - {"OTHER", "OTHER_RESERVED"}),
        "variants": [dict(item) for item in (profile.get("variants") or []) if isinstance(item, dict) and item.get("id")],
        "post_presets": [dict(item) for item in (profile.get("post_presets") or []) if isinstance(item, dict) and item.get("id")],
        "category_required": bool(category_values) and (
            any(
                isinstance(item, dict) and isinstance(item.get("category_values"), dict)
                for item in (snapshot.get("qualification_rules") or {}).get("criteria", [])
            ) or scoring.get("formula") in {
                "SSC_CGL_2025_DEST", "SSC_CGL_2025_VH_DEST",
                "SSC_CHSL_2025_ENGLISH", "SSC_CHSL_2025_HINDI",
                "SSC_CHSL_2025_HINDI_KRUTIDEV", "SSC_CHSL_2025_HINDI_MANGAL",
            }
        ),
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
    # Post-only selectors are also enforced when a profile has no variant list.
    posts = config.get("post_presets") or []
    selected_post = next((item for item in posts if item.get("id") == selected.get("post_id")), None)
    if selected.get("post_id") and selected_post is None:
        raise ValidationError("The saved post selection is missing or inconsistent; this attempt cannot be scored.")
    if selected_post and selected_post.get("requires_eligibility"):
        if selected.get("eligibility_attested") is not True or selected.get("eligibility_status") != "CANDIDATE_ATTESTED":
            raise ValidationError("The selected post's eligibility attestation is missing; this attempt cannot be scored.")

    resolved = snapshot.get("resolved_candidate_configuration")
    if resolved is not None:
        if not isinstance(resolved, dict) or resolved.get("schema_version") != 1:
            raise ValidationError("The resolved examination settings are invalid; this attempt cannot be scored.")
        if resolved.get("variant_id") != selected.get("variant_id") or resolved.get("post_id") != selected.get("post_id"):
            raise ValidationError("The resolved examination settings do not match the saved candidate selections.")
        scoring = snapshot.get("scoring_rules") or {}
        if resolved.get("standard_type") != scoring.get("standard_type"):
            raise ValidationError("The resolved examination standard does not match the scoring rules.")
        if resolved.get("duration_seconds") != snapshot.get("duration_seconds"):
            raise ValidationError("The resolved examination duration does not match the attempt snapshot.")
        expected_digest = resolved.get("runtime_contract_sha256")
        if not expected_digest or expected_digest != _contract_digest(snapshot):
            raise ValidationError("The examination runtime settings were changed after the attempt started.")
    return selected
