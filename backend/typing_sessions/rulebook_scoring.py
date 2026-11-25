"""Versioned, declarative rulebook scoring formulas.

This module executes only explicitly configured formula identifiers and parameters.
It never infers an exam formula from a profile name or legacy compatibility fields.
"""
from decimal import Decimal, InvalidOperation

ENGINE_VERSION = 1

FORMULAS = {
    "GROSS_WPM_CHARACTERS_5",
    "GROSS_WPM_STROKES_5",
    "CORRECT_WORDS_PER_MINUTE",
    "NET_WPM_WEIGHTED_MISTAKES",
    "NET_WPM_CORRECT_WORDS",
    "NET_WPM_FORGIVENESS_EXCESS_PENALTY",
    "AIIMS_STROKE_DEDUCTION",
    "KDPH",
    "ERROR_PERCENT_WEIGHTED",
    "MARKS_PER_CORRECT_WORD",
    "SPEED_BANDS",
}


def _decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _round(value, places=2):
    return round(float(value), places)


def evaluate_rulebook_scoring(config, metrics, *, duration_seconds):
    """Return formula outputs and audit details, or NOT_EVALUATED without fallback.

    Config shape:
      {"engine_version": 1, "formula": "NET_WPM_WEIGHTED_MISTAKES",
       "parameters": {"mistake_weight": 1, "denominator": "reference_words"}}
    """
    unresolved = {
        "evaluation_status": "NOT_EVALUATED",
        "formula_status": "NOT_EVALUATED",
        "formula_id": None,
        "formula_note": "No supported versioned rulebook scoring formula is configured.",
        "formula_checks": [],
        "metrics": {},
    }
    if not isinstance(config, dict) or config.get("engine_version") != ENGINE_VERSION:
        return unresolved
    formula = config.get("formula")
    params = config.get("parameters") or {}
    if formula not in FORMULAS or not isinstance(params, dict):
        return {**unresolved, "formula_id": formula, "formula_note": "The configured rulebook scoring formula is unsupported or malformed."}

    duration = _decimal(duration_seconds)
    if duration is None or duration <= 0:
        return {**unresolved, "formula_id": formula, "formula_note": "A valid test duration is required."}
    minutes = duration / Decimal(60)
    typed_chars = _decimal(metrics.get("typed_characters"))
    correct_chars = _decimal(metrics.get("correct_characters"))
    strokes = _decimal(metrics.get("server_strokes"))
    correct_words = _decimal(metrics.get("correct_words"))
    gross_words = _decimal(metrics.get("gross_words"))
    weighted = _decimal(metrics.get("weighted_mistakes"))
    full = _decimal(metrics.get("full_mistakes"))
    half = _decimal(metrics.get("half_mistakes"))
    categories = metrics.get("mistake_categories") or {}
    classification = params.get("mistake_classification") or {}
    if isinstance(classification, dict) and isinstance(categories, dict):
        full_keys = classification.get("full") or []
        half_keys = classification.get("half") or []
        if isinstance(full_keys, list) and isinstance(half_keys, list):
            full = sum((_decimal(categories.get(key)) or Decimal(0) for key in full_keys), Decimal(0))
            half = sum((_decimal(categories.get(key)) or Decimal(0) for key in half_keys), Decimal(0))
    full_weight = _decimal(params.get("full_mistake_weight", 1))
    half_weight = _decimal(params.get("half_mistake_weight", 0.5))
    if full is not None and half is not None and full_weight is not None and half_weight is not None:
        weighted = full * full_weight + half * half_weight
    reference_words = _decimal(metrics.get("reference_words"))
    outputs = {}
    checks = []

    def require(name, value):
        if value is None:
            checks.append({"label": name, "status": "UNRESOLVED", "reason": "Required source metric is unavailable."})
            return False
        return True

    if formula == "GROSS_WPM_CHARACTERS_5":
        if not require("typed_characters", typed_chars): pass
        else: outputs["gross_wpm"] = _round(typed_chars / Decimal(5) / minutes)
    elif formula == "GROSS_WPM_STROKES_5":
        if not require("server_strokes", strokes): pass
        else: outputs["gross_wpm"] = _round(strokes / Decimal(5) / minutes)
    elif formula == "CORRECT_WORDS_PER_MINUTE":
        if not require("correct_words", correct_words): pass
        else: outputs["net_wpm"] = _round(correct_words / minutes)
    elif formula == "NET_WPM_WEIGHTED_MISTAKES":
        if not all((require("gross_words", gross_words), require("weighted_mistakes", weighted))): pass
        else:
            unit = _decimal(params.get("mistake_penalty_words", 1))
            if unit is None or unit < 0:
                return {**unresolved, "formula_id": formula, "formula_note": "mistake_penalty_words must be a non-negative number."}
            outputs["net_words"] = max(Decimal(0), gross_words - weighted * unit)
            outputs["net_wpm"] = _round(outputs["net_words"] / minutes)
    elif formula == "NET_WPM_CORRECT_WORDS":
        if not require("correct_words", correct_words): pass
        else: outputs["net_wpm"] = _round(correct_words / minutes)
    elif formula == "NET_WPM_FORGIVENESS_EXCESS_PENALTY":
        if not all((require("gross_words", gross_words), require("weighted_mistakes", weighted))): pass
        else:
            rate = _decimal(params.get("forgiveness_rate"))
            penalty = _decimal(params.get("excess_mistake_penalty_words"))
            if rate is None or penalty is None or rate < 0 or penalty < 0:
                return {**unresolved, "formula_id": formula, "formula_note": "forgiveness_rate and excess_mistake_penalty_words must be configured as non-negative numbers."}
            forgiven = gross_words * rate
            excess = max(Decimal(0), weighted - forgiven)
            outputs["forgiven_mistakes"] = _round(forgiven)
            outputs["excess_mistakes"] = _round(excess)
            outputs["net_words"] = max(Decimal(0), gross_words - excess * penalty)
            outputs["net_wpm"] = _round(outputs["net_words"] / minutes)
    elif formula == "AIIMS_STROKE_DEDUCTION":
        if not all((require("server_strokes", strokes), require("full_mistakes", full), require("half_mistakes", half))): pass
        else:
            full_deduction = _decimal(params.get("full_mistake_strokes"))
            half_deduction = _decimal(params.get("half_mistake_strokes"))
            if full_deduction is None or half_deduction is None or full_deduction < 0 or half_deduction < 0:
                return {**unresolved, "formula_id": formula, "formula_note": "Full- and half-mistake stroke deductions must be explicitly configured."}
            outputs["net_wpm"] = _round(max(Decimal(0), strokes - full * full_deduction - half * half_deduction) / Decimal(5) / minutes)
    elif formula == "KDPH":
        if not require("server_strokes", strokes): pass
        else: outputs["gross_kdph"] = _round(strokes * Decimal(3600) / duration)
    elif formula == "ERROR_PERCENT_WEIGHTED":
        if not all((require("weighted_mistakes", weighted), require("reference_words", reference_words))): pass
        else:
            denominator = params.get("denominator", "reference_words")
            if denominator != "reference_words":
                return {**unresolved, "formula_id": formula, "formula_note": "Only the explicitly supported reference_words denominator is currently available."}
            outputs["error_percent"] = _round(weighted * Decimal(100) / max(Decimal(1), reference_words))
    elif formula == "MARKS_PER_CORRECT_WORD":
        if not require("correct_words", correct_words): pass
        else:
            rate = _decimal(params.get("marks_per_correct_word"))
            maximum = _decimal(params.get("maximum_marks"))
            if rate is None or rate < 0:
                return {**unresolved, "formula_id": formula, "formula_note": "marks_per_correct_word must be explicitly configured."}
            marks = correct_words * rate
            outputs["score"] = _round(min(marks, maximum) if maximum is not None and maximum >= 0 else marks)
    elif formula == "SPEED_BANDS":
        speed_metric = params.get("speed_metric", "net_wpm")
        speed = _decimal(metrics.get(speed_metric))
        bands = params.get("bands")
        if speed is None or not isinstance(bands, list) or not bands:
            return {**unresolved, "formula_id": formula, "formula_note": "A measurable speed metric and explicit marks bands are required."}
        eligible = []
        for band in bands:
            if not isinstance(band, dict):
                continue
            threshold, marks = _decimal(band.get("minimum")), _decimal(band.get("marks"))
            if threshold is None or marks is None or marks < 0:
                continue
            if speed >= threshold:
                eligible.append(marks)
        if not eligible:
            outputs["score"] = _round(_decimal(params.get("below_band_marks")) or Decimal(0))
        else:
            outputs["score"] = _round(max(eligible))

    if any(row.get("status") == "UNRESOLVED" for row in checks):
        return {
            "evaluation_status": "NOT_EVALUATED", "formula_status": "NOT_EVALUATED",
            "formula_id": formula, "formula_note": "Required formula inputs could not be measured.",
            "formula_checks": checks, "metrics": {},
        }
    return {
        "evaluation_status": "EVALUATED", "formula_status": "EVALUATED",
        "formula_id": formula, "formula_note": "Calculated using the configured versioned rulebook formula.",
        "formula_checks": checks, "metrics": {key: _round(value) for key, value in outputs.items()},
    }
