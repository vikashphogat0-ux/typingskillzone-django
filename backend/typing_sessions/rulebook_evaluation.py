"""Safe evaluator for explicitly structured, versioned rulebook criteria.

Only criteria expressed as metric/operator/value are executable. Source prose,
examples and hedged statements are never interpreted as thresholds.
"""
from decimal import Decimal, InvalidOperation

ENGINE_VERSION = 1
METRICS = {
    "net_wpm", "gross_wpm", "correct_wpm", "accuracy_percent",
    "error_percent", "score", "correct_words", "word_errors",
    "keystrokes", "gross_words", "gross_kdph", "weighted_mistakes",
}
OPERATORS = {
    "gte": lambda a, b: a >= b,
    "gt": lambda a, b: a > b,
    "lte": lambda a, b: a <= b,
    "lt": lambda a, b: a < b,
    "eq": lambda a, b: a == b,
}


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def evaluate_rulebook_qualification(config, metrics, *, candidate_category=None, selectors=None):
    """Return a deterministic decision and auditable per-criterion checks.

    Supported config:
      {"engine_version": 1, "mode": "ALL",
       "criteria": [{"id": "...", "label": "...", "metric": "net_wpm",
                     "operator": "gte", "value": 35,
                     "category_values": {"UR": 7}}]}
    Category-specific thresholds use category_values; selector-specific
    profiles must be resolved before this function is called.
    """
    selectors = selectors if isinstance(selectors, dict) else {}
    if not isinstance(metrics, dict):
        metrics = {}
    if not isinstance(config, dict) or config.get("engine_version") != ENGINE_VERSION:
        return {
            "evaluation_status": "NOT_EVALUATED",
            "qualification": None,
            "qualification_status": "NOT EVALUATED",
            "qualification_note": "No supported versioned rulebook qualification criteria are configured.",
            "qualification_checks": [],
        }
    criteria = config.get("criteria")
    mode = config.get("mode", "ALL")
    if not isinstance(criteria, list) or not criteria or mode not in {"ALL", "ANY"}:
        return {
            "evaluation_status": "NOT_EVALUATED", "qualification": None,
            "qualification_status": "NOT EVALUATED",
            "qualification_note": "Rulebook criteria are empty or have an unsupported structure.",
            "qualification_checks": [],
        }

    checks = []
    for index, criterion in enumerate(criteria):
        if not isinstance(criterion, dict):
            return {
                "evaluation_status": "NOT_EVALUATED", "qualification": None,
                "qualification_status": "NOT EVALUATED",
                "qualification_note": "A rulebook criterion is malformed.",
                "qualification_checks": checks,
            }
        when_selectors = criterion.get("when_selectors") or {}
        if not isinstance(when_selectors, dict):
            return {
                "evaluation_status": "NOT_EVALUATED", "qualification": None,
                "qualification_status": "NOT EVALUATED",
                "qualification_note": "A selector condition is malformed.",
                "qualification_checks": checks,
            }
        missing_selector_keys = [key for key in when_selectors if key not in selectors]
        if missing_selector_keys:
            checks.append({
                "label": criterion.get("label") or criterion.get("id") or f"Criterion {index + 1}",
                "required": when_selectors, "achieved": selectors,
                "status": "UNRESOLVED",
                "reason": "A required candidate selector was not saved; this criterion cannot be classified as applicable or not applicable.",
            })
            continue
        if any(selectors.get(key) != value for key, value in when_selectors.items()):
            checks.append({
                "label": criterion.get("label") or criterion.get("id") or f"Criterion {index + 1}",
                "required": when_selectors, "achieved": selectors,
                "status": "NOT APPLICABLE",
                "reason": "This criterion does not apply to the selected candidate standard.",
            })
            continue
        metric = criterion.get("metric")
        operator = criterion.get("operator")
        expected = criterion.get("value")
        selector_values = criterion.get("selector_values")
        if "selector_values" in criterion:
            selector_key = criterion.get("selector")
            if not isinstance(selector_values, dict) or not selector_values or not isinstance(selector_key, str) or not selector_key:
                expected = None
                selected_value = None
            else:
                selected_value = selectors.get(selector_key)
            if not isinstance(selector_values, dict) or not selector_values or not isinstance(selector_key, str) or not selector_key or selected_value not in selector_values:
                expected = None
            else:
                expected = selector_values[selected_value]
        category_values = criterion.get("category_values")
        if isinstance(category_values, dict):
            if not candidate_category or candidate_category not in category_values:
                expected = None
            else:
                expected = category_values[candidate_category]
        actual_number, expected_number = _number(metrics.get(metric)), _number(expected)
        if metric not in METRICS or operator not in OPERATORS or actual_number is None or expected_number is None:
            checks.append({
                "label": criterion.get("label") or criterion.get("id") or f"Criterion {index + 1}",
                "required": expected, "achieved": metrics.get(metric),
                "status": "UNRESOLVED",
                "reason": "Required metric, category threshold or comparison value is unavailable.",
            })
            continue
        passed = OPERATORS[operator](actual_number, expected_number)
        checks.append({
            "label": criterion.get("label") or criterion.get("id") or f"Criterion {index + 1}",
            "required": f"{operator} {expected}",
            "achieved": metrics.get(metric),
            "status": "MET" if passed else "NOT MET",
            "reason": criterion.get("reason") or "",
        })

    if any(check["status"] == "UNRESOLVED" for check in checks):
        return {
            "evaluation_status": "NOT_EVALUATED", "qualification": None,
            "qualification_status": "NOT EVALUATED",
            "qualification_note": "At least one required rulebook criterion could not be evaluated; no pass/fail decision was made.",
            "qualification_checks": checks,
        }
    outcomes = [check["status"] == "MET" for check in checks if check["status"] != "NOT APPLICABLE"]
    if not outcomes:
        return {
            "evaluation_status": "NOT_EVALUATED", "qualification": None,
            "qualification_status": "NOT EVALUATED",
            "qualification_note": "No qualification criteria apply to the saved candidate selections.",
            "qualification_checks": checks,
        }
    qualified = all(outcomes) if mode == "ALL" else any(outcomes)
    return {
        "evaluation_status": "EVALUATED",
        "qualification": qualified,
        "qualification_status": "QUALIFIED" if qualified else "NOT QUALIFIED",
        "qualification_note": "All required rulebook criteria were met." if qualified and mode == "ALL" else (
            "At least one permitted rulebook criterion was met." if qualified else
            "The configured rulebook qualification criteria were not satisfied."
        ),
        "qualification_checks": checks,
    }
