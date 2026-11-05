"""Canonical, read-only scoring specification registry.

This registry describes the formula selected by an exam profile. It does not
invent missing official parameters and does not replace legacy scoring
execution until a profile has an explicit, reviewed mapping.
"""

SCORING_REGISTRY_SCHEMA_VERSION = 1

_MODE_FORMULAS = {
    "GENERIC": "PRACTICE_CHARACTER_METRICS",
    "CORRECT_WORDS": "CORRECT_WORDS_PER_MINUTE",
    "NET_WPM": "NET_WPM_STROKE_ADJUSTED",
    "ERROR_PERCENTAGE": "WORD_ERROR_ALLOWANCE",
    "STROKE_PENALTY": "STROKE_PENALTY_NET_SPEED",
    "FULL_HALF_MISTAKES": "EXACT_WORD_PAIR_CLASSIFICATION",
    "CORRECT_WORD_MARKS": "MARKS_PER_CORRECT_WORD",
    "QUALIFYING_ONLY": "WORD_ERROR_ALLOWANCE_QUALIFICATION",
    "CUSTOM": "CUSTOM_VERSIONED_FORMULA",
}


def _positive_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number > 0


def resolve_scoring_specification(rules):
    """Return a JSON-safe scoring descriptor with explicit unresolved fields."""
    rules = rules if isinstance(rules, dict) else {}
    mode = rules.get("scoring_mode") or "GENERIC"
    scoring_rules = rules.get("scoring_rules")
    scoring_rules = scoring_rules if isinstance(scoring_rules, dict) else {}
    error_rules = rules.get("error_rules")
    error_rules = error_rules if isinstance(error_rules, dict) else {}

    descriptor = {
        "schema_version": SCORING_REGISTRY_SCHEMA_VERSION,
        "mode": mode,
        "formula_id": _MODE_FORMULAS.get(mode),
        "status": "READY",
        "execution_compatibility": "LEGACY_ENGINE_ADAPTER",
        "parameters": {},
        "unresolved": [],
        "qualification_eligible": False,
    }

    def require(condition, field, reason):
        if not condition:
            descriptor["unresolved"].append({"field": field, "reason": reason})

    if mode not in _MODE_FORMULAS:
        descriptor["formula_id"] = None
        descriptor["status"] = "UNSUPPORTED"
        descriptor["unresolved"].append({
            "field": "scoring_mode",
            "reason": "No registered formula exists for this scoring mode.",
        })
    elif mode == "GENERIC":
        descriptor["status"] = "PRACTICE_ONLY"
        descriptor["unresolved"].append({
            "field": "official_formula",
            "reason": "Generic character metrics are practice analytics, not an exam-specific official formula.",
        })
    elif mode == "NET_WPM":
        strokes = rules.get("strokes_per_word")
        error_unit_strokes = scoring_rules.get("error_unit_strokes")
        count_word_errors = error_rules.get("count_word_errors")
        require(_positive_number(strokes), "strokes_per_word", "An explicit positive strokes-per-word convention is required.")
        require(count_word_errors is not None, "error_rules.count_word_errors", "The error unit must be explicitly declared as word- or character-based.")
        require(error_unit_strokes is not None or _positive_number(strokes), "scoring_rules.error_unit_strokes", "The error penalty unit must be explicit.")
        descriptor["parameters"] = {
            "strokes_per_word": strokes,
            "error_unit_strokes": error_unit_strokes,
            "error_unit": "word" if count_word_errors is True else "character" if count_word_errors is False else None,
        }
    elif mode == "STROKE_PENALTY":
        strokes = rules.get("strokes_per_word")
        penalty = rules.get("mistake_penalty_strokes") or scoring_rules.get("mistake_penalty_strokes")
        require(_positive_number(strokes), "strokes_per_word", "An explicit positive strokes-per-word convention is required.")
        require(penalty is not None, "mistake_penalty_strokes", "An explicit mistake penalty in strokes is required.")
        require(error_rules.get("count_word_errors") is not None, "error_rules.count_word_errors", "The mistake counting unit must be explicit.")
        descriptor["parameters"] = {
            "strokes_per_word": strokes,
            "mistake_penalty_strokes": penalty,
            "error_unit": "word" if error_rules.get("count_word_errors") is True else "character" if error_rules.get("count_word_errors") is False else None,
        }
    elif mode in {"ERROR_PERCENTAGE", "QUALIFYING_ONLY"}:
        allowance = rules.get("error_allowance_percent")
        word_errors = error_rules.get("count_word_errors") is True
        require(allowance is not None, "error_allowance_percent", "An explicit error allowance percentage is required.")
        require(word_errors, "error_rules.count_word_errors", "The current percentage formula requires explicitly configured word-based errors.")
        if scoring_rules.get("excess_mistake_deduction_words") is not None:
            require(_positive_number(rules.get("strokes_per_word")), "strokes_per_word", "An explicit strokes-per-word convention is required when converting deducted words to speed.")
        descriptor["parameters"] = {
            "error_allowance_percent": allowance,
            "error_unit": "word" if word_errors else None,
            "excess_mistake_deduction_words": scoring_rules.get("excess_mistake_deduction_words", 0),
            "minimum_wpm": rules.get("minimum_wpm"),
        }
    elif mode == "FULL_HALF_MISTAKES":
        config = scoring_rules.get("mistake_classification")
        valid = isinstance(config, dict) and config.get("version") == 1 and config.get("unit") == "word" and isinstance(config.get("overrides"), list)
        require(valid, "scoring_rules.mistake_classification", "A supported version-1 exact word-pair classification table is required.")
        descriptor["parameters"] = {"classification_version": config.get("version") if isinstance(config, dict) else None}
    elif mode == "CORRECT_WORD_MARKS":
        require(scoring_rules.get("marks_per_correct_word") is not None, "scoring_rules.marks_per_correct_word", "Marks per correct word must be explicitly configured.")
        descriptor["parameters"] = {"marks_per_correct_word": scoring_rules.get("marks_per_correct_word")}
    elif mode == "CUSTOM":
        require(scoring_rules.get("formula_version") is not None, "scoring_rules.formula_version", "Custom scoring requires an explicit formula version.")
        descriptor["parameters"] = {
            "formula_version": scoring_rules.get("formula_version"),
            "score_bands": scoring_rules.get("score_bands"),
            "mistake_penalty_words": scoring_rules.get("mistake_penalty_words"),
            "disqualify_at_mistakes": scoring_rules.get("disqualify_at_mistakes"),
        }
        if not scoring_rules.get("score_bands") and not scoring_rules.get("mistake_penalty_words") and scoring_rules.get("disqualify_at_mistakes") is None:
            require(False, "scoring_rules", "At least one executable custom scoring rule is required.")

    if descriptor["unresolved"] and descriptor["status"] == "READY":
        descriptor["status"] = "PARTIAL"
    evidence = rules.get("domain_evidence_snapshot") or {}
    domains = evidence.get("domains") if isinstance(evidence, dict) else None
    if isinstance(domains, dict):
        scoring_status = (domains.get("scoring") or {}).get("status", "UNVERIFIED")
        qualification_status = (domains.get("qualification") or {}).get("status", "UNVERIFIED")
        descriptor["provenance"] = {
            "scoring": scoring_status,
            "qualification": qualification_status,
        }
        descriptor["qualification_eligible"] = (
            descriptor["status"] == "READY"
            and scoring_status == "VERIFIED"
            and (mode not in {"ERROR_PERCENTAGE", "QUALIFYING_ONLY", "CUSTOM"} or qualification_status == "VERIFIED")
        )
    else:
        descriptor["provenance"] = {
            "scoring": "LEGACY_PROFILE_STATUS_ONLY",
            "qualification": "LEGACY_PROFILE_STATUS_ONLY",
        }
        descriptor["qualification_eligible"] = (
            descriptor["status"] == "READY"
            and rules.get("verification_status") == "VERIFIED"
        )
    return descriptor
