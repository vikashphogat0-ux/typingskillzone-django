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
    "UPSSSC_FIVE_EXEMPT_SIXFOLD",
    "SPMCIL_STROKE_ERROR_WORDS",
    "MP_CPCT_NET_WPM_SLABS",
    "MPHC_MARKS_BACKSPACE_DEDUCTION",
}


FORMULA_INPUTS = {
    "GROSS_WPM_CHARACTERS_5": {"typed_characters"},
    "GROSS_WPM_STROKES_5": {"server_strokes"},
    "CORRECT_WORDS_PER_MINUTE": {"correct_words"},
    "NET_WPM_WEIGHTED_MISTAKES": {"gross_words", "weighted_mistakes"},
    "NET_WPM_CORRECT_WORDS": {"correct_words"},
    "NET_WPM_FORGIVENESS_EXCESS_PENALTY": {"gross_words", "weighted_mistakes"},
    "AIIMS_STROKE_DEDUCTION": {"server_strokes", "weighted_mistakes"},
    "KDPH": {"server_strokes"},
    "ERROR_PERCENT_WEIGHTED": {"weighted_mistakes", "reference_words"},
    "MARKS_PER_CORRECT_WORD": {"correct_words"},
    "UPSSSC_FIVE_EXEMPT_SIXFOLD": {"gross_words", "wrong_words"},
    "SPMCIL_STROKE_ERROR_WORDS": {"server_strokes", "weighted_mistakes"},
    "MP_CPCT_NET_WPM_SLABS": {"gross_words", "weighted_mistakes"},
    "MPHC_MARKS_BACKSPACE_DEDUCTION": {"wrong_words", "backspace_presses"},
}


# Metrics whose official values must come from the selected formula, never a
# legacy compatibility calculation. The audit and runtime use this same map.
FORMULA_OUTPUTS = {
    "GROSS_WPM_CHARACTERS_5": {"gross_wpm"},
    "GROSS_WPM_STROKES_5": {"gross_wpm"},
    "CORRECT_WORDS_PER_MINUTE": {"net_wpm"},
    "NET_WPM_WEIGHTED_MISTAKES": {"net_words", "net_wpm"},
    "NET_WPM_CORRECT_WORDS": {"net_wpm"},
    "NET_WPM_FORGIVENESS_EXCESS_PENALTY": {"net_words", "net_wpm"},
    "AIIMS_STROKE_DEDUCTION": {"gross_wpm", "net_wpm", "accuracy_percent", "weighted_mistakes"},
    "KDPH": {"gross_kdph"},
    "ERROR_PERCENT_WEIGHTED": {"error_percent"},
    "MARKS_PER_CORRECT_WORD": {"score"},
    "SPEED_BANDS": {"score"},
    "UPSSSC_FIVE_EXEMPT_SIXFOLD": {"net_words", "net_wpm"},
    "SPMCIL_STROKE_ERROR_WORDS": {"net_words", "net_wpm"},
    "MP_CPCT_NET_WPM_SLABS": {"net_words", "net_wpm", "score_percent"},
    "MPHC_MARKS_BACKSPACE_DEDUCTION": {"score"},
}

# gross_wpm is independently measured from server-side strokes by the
# submission pipeline. A formula may refine it, but qualification can use the
# raw measurement even when a selected formula does not calculate gross speed.
FORMULA_DERIVED_METRICS = {
    "net_wpm", "gross_kdph", "error_percent",
    "score", "net_words",
}


def required_formula_outputs(config):
    """Return formula-owned metrics that qualification criteria may consume."""
    if not isinstance(config, dict):
        return set()
    formula = config.get("formula")
    if formula == "SPEED_BANDS":
        return {"score"}
    return set(FORMULA_OUTPUTS.get(formula, set()))


def required_formula_inputs(config):
    """Return source metrics the selected formula actually consumes."""
    if not isinstance(config, dict):
        return set()
    formula = config.get("formula")
    if formula == "SPEED_BANDS":
        params = config.get("parameters") or {}
        metric = params.get("speed_metric", "net_wpm") if isinstance(params, dict) else None
        return {metric} if isinstance(metric, str) and metric else set()
    required = set(FORMULA_INPUTS.get(formula, set()))
    if formula == "ERROR_PERCENT_WEIGHTED":
        params = config.get("parameters") or {}
        denominator = params.get("denominator", "reference_words") if isinstance(params, dict) else None
        if denominator == "typed_words":
            required.add("typed_words")
        elif denominator != "reference_words":
            required.add(f"unsupported_denominator:{denominator}")
    if formula == "AIIMS_STROKE_DEDUCTION":
        params = config.get("parameters") or {}
        if isinstance(params, dict) and (
            "full_mistake_strokes" in params or "half_mistake_strokes" in params
        ):
            required.update({"mistake_categories"})
    return required


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
    wrong_words = _decimal(metrics.get("wrong_words", metrics.get("word_errors")))
    backspace_presses = _decimal(metrics.get("backspace_presses"))
    gross_words = _decimal(metrics.get("gross_words"))
    weighted = _decimal(metrics.get("weighted_mistakes"))
    full = _decimal(metrics.get("full_mistakes"))
    half = _decimal(metrics.get("half_mistakes"))
    categories = metrics.get("mistake_categories") or {}
    classification = params.get("mistake_classification") or {}
    if isinstance(classification, dict) and isinstance(categories, dict):
        full_keys = classification.get("full") or []
        half_keys = classification.get("half") or []
        if (
            isinstance(full_keys, list) and isinstance(half_keys, list)
            and (full_keys or half_keys)
        ):
            full = sum((_decimal(categories.get(key)) or Decimal(0) for key in full_keys), Decimal(0))
            half = sum((_decimal(categories.get(key)) or Decimal(0) for key in half_keys), Decimal(0))
    full_weight = _decimal(params.get("full_mistake_weight", 1))
    half_weight = _decimal(params.get("half_mistake_weight", 0.5))
    if full is not None and half is not None and full_weight is not None and half_weight is not None:
        weighted = full * full_weight + half * half_weight
    reference_words = _decimal(metrics.get("reference_words"))
    typed_words = _decimal(metrics.get("typed_words", metrics.get("gross_words")))
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
        if not require("server_strokes", strokes):
            pass
        else:
            minimum_strokes = _decimal(params.get("minimum_strokes"))
            penalty_per_mistake = _decimal(params.get("penalty_strokes_per_mistake", 50))
            full_stroke_penalty = _decimal(params.get("full_mistake_strokes"))
            half_stroke_penalty = _decimal(params.get("half_mistake_strokes"))
            if (
                (minimum_strokes is not None and minimum_strokes <= 0)
                or penalty_per_mistake is None or penalty_per_mistake < 0
                or (full_stroke_penalty is not None and full_stroke_penalty < 0)
                or (half_stroke_penalty is not None and half_stroke_penalty < 0)
            ):
                return {**unresolved, "formula_id": formula, "formula_note": "AIIMS stroke thresholds and deduction values must be non-negative, with a positive minimum_strokes when supplied."}
            uses_full_half = full_stroke_penalty is not None or half_stroke_penalty is not None
            if uses_full_half and (full_stroke_penalty is None or half_stroke_penalty is None or full is None or half is None):
                return {**unresolved, "formula_id": formula, "formula_note": "AIIMS full/half deduction requires both stroke rates and measured full_mistakes and half_mistakes."}
            penalty_strokes = (
                full * full_stroke_penalty + half * half_stroke_penalty
                if uses_full_half else weighted * penalty_per_mistake
            )
            gross_wpm = strokes / Decimal(5) / minutes
            outputs["gross_wpm"] = _round(gross_wpm)
            outputs["penalty_strokes"] = _round(penalty_strokes)
            outputs["weighted_mistakes"] = _round(weighted) if weighted is not None else _round(full + half)
            if minimum_strokes is not None:
                sufficient = strokes >= minimum_strokes
                outputs["minimum_strokes"] = _round(minimum_strokes)
                outputs["attempt_status"] = "SUFFICIENT_ATTEMPT" if sufficient else "INSUFFICIENT_ATTEMPT"
            else:
                sufficient = True
            if not sufficient:
                outputs["net_wpm"] = None
                outputs["accuracy_percent"] = None
            else:
                net_wpm = max(Decimal(0), strokes - penalty_strokes) / Decimal(5) / minutes
                outputs["net_wpm"] = _round(net_wpm)
                outputs["accuracy_percent"] = _round(net_wpm * Decimal(100) / gross_wpm) if gross_wpm else 0.0
    elif formula == "KDPH":
        if not require("server_strokes", strokes): pass
        else: outputs["gross_kdph"] = _round(strokes * Decimal(3600) / duration)
    elif formula == "ERROR_PERCENT_WEIGHTED":
        if not all((require("weighted_mistakes", weighted), require("reference_words", reference_words))): pass
        else:
            denominator = params.get("denominator", "reference_words")
            denominator_metrics = {
                "reference_words": reference_words,
                "typed_words": typed_words,
            }
            denominator_value = denominator_metrics.get(denominator)
            if denominator_value is None:
                return {
                    **unresolved,
                    "formula_id": formula,
                    "formula_note": (
                        "ERROR_PERCENT_WEIGHTED denominator must be reference_words "
                        "or typed_words, and its source metric must be available."
                    ),
                }
            if denominator_value < 0:
                return {**unresolved, "formula_id": formula, "formula_note": "Error denominator cannot be negative."}
            outputs["error_percent"] = _round(weighted * Decimal(100) / max(Decimal(1), denominator_value))
            outputs["error_denominator"] = _round(denominator_value)
            outputs["error_denominator_type"] = denominator
    elif formula == "MARKS_PER_CORRECT_WORD":
        if not require("correct_words", correct_words): pass
        else:
            rate = _decimal(params.get("marks_per_correct_word"))
            maximum = _decimal(params.get("maximum_marks"))
            if rate is None or rate < 0:
                return {**unresolved, "formula_id": formula, "formula_note": "marks_per_correct_word must be explicitly configured."}
            marks = correct_words * rate
            outputs["score"] = _round(min(marks, maximum) if maximum is not None and maximum >= 0 else marks)
    elif formula == "UPSSSC_FIVE_EXEMPT_SIXFOLD":
        if not all((require("gross_words", gross_words), require("wrong_words", wrong_words))): pass
        else:
            exempt = _decimal(params.get("exempt_wrong_words", 5))
            multiplier = _decimal(params.get("penalty_multiplier", 6))
            if exempt is None or multiplier is None or exempt < 0 or multiplier < 1:
                return {**unresolved, "formula_id": formula, "formula_note": "UPSSSC exemption and penalty multiplier must be valid."}
            chargeable = max(Decimal(0), wrong_words - exempt)
            outputs["exempt_wrong_words"] = _round(min(wrong_words, exempt))
            outputs["chargeable_wrong_words"] = _round(chargeable)
            outputs["penalty_words"] = _round(chargeable * multiplier)
            outputs["net_words"] = max(Decimal(0), gross_words - chargeable * multiplier)
            outputs["net_wpm"] = _round(outputs["net_words"] / minutes)
    elif formula == "SPMCIL_STROKE_ERROR_WORDS":
        if not all((require("server_strokes", strokes), require("weighted_mistakes", weighted))): pass
        else:
            divisor = _decimal(params.get("strokes_per_word", 5))
            if divisor is None or divisor <= 0:
                return {**unresolved, "formula_id": formula, "formula_note": "strokes_per_word must be positive."}
            gross_equivalent = strokes / divisor
            error_words = weighted / divisor
            outputs["gross_word_equivalents"] = _round(gross_equivalent)
            outputs["error_words"] = _round(error_words)
            outputs["net_words"] = max(Decimal(0), gross_equivalent - error_words)
            outputs["net_wpm"] = _round(outputs["net_words"] / minutes)
    elif formula == "MP_CPCT_NET_WPM_SLABS":
        if not all((require("gross_words", gross_words), require("weighted_mistakes", weighted))): pass
        else:
            deduction = _decimal(params.get("words_per_error", 1))
            bands = params.get("bands")
            if deduction is None or deduction < 0 or not isinstance(bands, list) or not bands:
                return {**unresolved, "formula_id": formula, "formula_note": "MP-CPCT deduction and score bands must be configured."}
            outputs["net_words"] = max(Decimal(0), gross_words - weighted * deduction)
            outputs["net_wpm"] = _round(outputs["net_words"] / minutes)
            eligible = []
            for band in bands:
                if isinstance(band, dict):
                    threshold = _decimal(band.get("minimum_net_wpm"))
                    percentage = _decimal(band.get("percentage"))
                    if threshold is not None and percentage is not None and outputs["net_wpm"] >= threshold:
                        eligible.append(percentage)
            outputs["score_percent"] = _round(max(eligible)) if eligible else 0.0
    elif formula == "MPHC_MARKS_BACKSPACE_DEDUCTION":
        if not all((require("wrong_words", wrong_words), require("backspace_presses", backspace_presses))): pass
        else:
            maximum = _decimal(params.get("maximum_marks"))
            wrong_rate = _decimal(params.get("wrong_word_deduction", 0.5))
            backspace_rate = _decimal(params.get("backspace_deduction", 0.1))
            if maximum is None or wrong_rate is None or backspace_rate is None or min(maximum, wrong_rate, backspace_rate) < 0:
                return {**unresolved, "formula_id": formula, "formula_note": "MPHC marks and deduction parameters must be configured."}
            outputs["wrong_word_deduction_marks"] = _round(wrong_words * wrong_rate)
            outputs["backspace_deduction_marks"] = _round(backspace_presses * backspace_rate)
            outputs["score"] = _round(max(Decimal(0), maximum - wrong_words * wrong_rate - backspace_presses * backspace_rate))
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
        "formula_checks": checks,
        "metrics": {
            key: value if value is None or isinstance(value, str) else _round(value)
            for key, value in outputs.items()
        },
    }
