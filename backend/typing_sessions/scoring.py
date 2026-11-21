"""Deterministic server-side scoring for a single submitted typing attempt."""
from difflib import SequenceMatcher
import re
import unicodedata
from .mistake_classification import classify_typing_mistakes
SCORING_VERSION = "tsz-char-word-v2"



def _attempted_reference_prefix(reference, typed):
    """Limit comparison to the reference words the learner actually reached."""
    reference = reference or ""
    typed = typed or ""
    typed_words = re.findall(r"\S+", typed)
    reference_spans = list(re.finditer(r"\S+", reference))
    if not typed_words or not reference_spans:
        return ""
    reached = min(len(typed_words), len(reference_spans))
    end = reference_spans[reached - 1].end()
    if typed and typed[-1].isspace():
        trailing = re.match(r"\s*", reference[end:])
        if trailing:
            end += len(trailing.group(0))
    return reference[:end]


def _count_character_errors(reference, typed):
    attempted_reference = _attempted_reference_prefix(reference, typed)
    matcher = SequenceMatcher(a=attempted_reference, b=typed, autojunk=False)
    correct = substitutions = insertions = deletions = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            correct += i2 - i1
        elif tag == "replace":
            ref_len, typed_len = i2 - i1, j2 - j1
            substitutions += min(ref_len, typed_len)
            if typed_len > ref_len:
                insertions += typed_len - ref_len
            elif ref_len > typed_len:
                deletions += ref_len - typed_len
        elif tag == "insert":
            insertions += j2 - j1
        elif tag == "delete":
            deletions += i2 - i1
    return {
        "correct_characters": correct,
        "substitution_errors": substitutions,
        "insertion_errors": insertions,
        "deletion_errors": deletions,
        "character_errors": substitutions + insertions + deletions,
    }


def _count_word_errors(reference, typed):
    ref_words = re.findall(r"\S+", _attempted_reference_prefix(reference, typed))
    typed_words = re.findall(r"\S+", typed)
    matcher = SequenceMatcher(a=ref_words, b=typed_words, autojunk=False)
    errors = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        errors += max(i2 - i1, j2 - j1)
    return errors



def _count_correct_words(reference, typed):
    ref_words = re.findall(r"\S+", _attempted_reference_prefix(reference, typed))
    typed_words = re.findall(r"\S+", typed)
    matcher = SequenceMatcher(a=ref_words, b=typed_words, autojunk=False)
    return sum(i2 - i1 for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag == "equal")


def _evaluate_qualification_rules(config, metrics):
    """Evaluate explicit threshold conditions; unsupported conditions remain pending."""
    if not isinstance(config, dict) or not config:
        return None, "Qualification is pending: no qualification conditions are configured."
    allowed_metrics = {"net_wpm", "gross_wpm", "accuracy_percent", "error_percent", "score", "correct_words", "word_errors"}
    operators = {
        "gte": lambda a, b: a >= b, "gt": lambda a, b: a > b,
        "lte": lambda a, b: a <= b, "lt": lambda a, b: a < b,
        "eq": lambda a, b: a == b,
    }
    def evaluate(condition):
        if not isinstance(condition, dict):
            return None
        metric, operator, expected = condition.get("metric"), condition.get("operator"), condition.get("value")
        if metric not in allowed_metrics or operator not in operators or expected is None or isinstance(expected, bool):
            return None
        actual = metrics.get(metric)
        if actual is None:
            return None
        try:
            return operators[operator](float(actual), float(expected))
        except (TypeError, ValueError):
            return None
    all_conditions, any_conditions = config.get("all", []), config.get("any", [])
    if not isinstance(all_conditions, list) or not isinstance(any_conditions, list):
        return None, "Qualification is pending: qualification conditions have an invalid format."
    if not all_conditions and not any_conditions:
        return None, "Qualification is pending: no supported conditions are configured."
    results = [evaluate(c) for c in all_conditions + any_conditions]
    if not results or any(value is None for value in results):
        return None, "Qualification is pending: one or more conditions are unsupported or cannot be measured."
    passed = all(results[:len(all_conditions)]) and (
        not any_conditions or any(results[len(all_conditions):])
    )
    return passed, "Qualification conditions satisfied." if passed else "One or more qualification conditions were not satisfied."


def calculate_result(*, reference, typed, duration_seconds, rules, reported_keystrokes=None):
    """Calculate metrics exclusively from persisted source text and submitted text."""
    # Hindi text can arrive in composed (NFC) or decomposed (NFD) form. Compare both in NFC so
    # equivalent characters are never scored as errors.
    reference = unicodedata.normalize("NFC", reference or "")
    typed = unicodedata.normalize("NFC", typed or "")
    duration = max(1, int(duration_seconds))
    minutes = duration / 60
    chars = _count_character_errors(reference, typed)
    denominator = max(len(typed), 1)
    accuracy = round(chars["correct_characters"] * 100 / denominator, 2)
    gross_wpm = round(len(typed) / 5 / minutes, 2)
    correct_wpm = round(chars["correct_characters"] / 5 / minutes, 2)
    word_errors = _count_word_errors(reference, typed)
    error_rules = rules.get("error_rules") or {}
    scoring_rules = rules.get("scoring_rules") or {}
    scoring_mode = rules.get("scoring_mode", "GENERIC")

    mistake_analysis = None

    if (
        scoring_mode == "CUSTOM"
        and scoring_rules.get("formula") == "STROKE_NET_WPM"
    ):
        mistake_analysis = classify_typing_mistakes(reference, typed)
        error_count = mistake_analysis["total_detected_errors"]
        count_word_errors = True
    else:
        count_word_errors = bool(error_rules.get("count_word_errors", False))
        error_count = word_errors if count_word_errors else chars["character_errors"]
    penalty_per_error = error_rules.get("penalty_wpm_per_error", 0)
    try:
        penalty_per_error = max(0, float(penalty_per_error))
    except (TypeError, ValueError):
        penalty_per_error = 0
    net_wpm = round(max(0, correct_wpm - error_count * penalty_per_error), 2)

    required_keystrokes = rules.get("required_keystrokes")
    try:
        required_keystrokes = int(required_keystrokes) if required_keystrokes is not None else None
    except (TypeError, ValueError):
        required_keystrokes = None
    if reported_keystrokes is not None:
        reported_keystrokes = max(0, min(1000000, int(reported_keystrokes)))
    # Browser-reported key depressions are untrusted. Do not use them to
    # declare that a verified examination's required-stroke threshold was met.
    required_keystrokes_met = (
        reported_keystrokes >= required_keystrokes
        if (
            rules.get("verification_status") != "VERIFIED"
            and reported_keystrokes is not None
            and required_keystrokes is not None
        )
        else None
    )
    stroke_count_for_speed = (
        reported_keystrokes
        if reported_keystrokes is not None
        else len(typed)
    )
    stroke_count_source = (
        "client_reported"
        if reported_keystrokes is not None
        else "typed_character_fallback"
    )
    # Untrusted client telemetry must never influence an official
    # qualifying result. When the exam rules are verified, derive the
    # stroke count server-side from the persisted submitted text so a
    # manipulated client keystroke count cannot inflate speed or marks.
    # Practice (unverified) attempts keep the client-reported value as a
    # separate, clearly-labelled provisional metric.
    if rules.get("verification_status") == "VERIFIED":
        stroke_count_for_speed = len(typed)
        stroke_count_source = "server_derived"
    tentative_wpm = None
    
    correct_words = _count_correct_words(reference, typed)
    gross_words = len(re.findall(r"\S+", typed))
    strokes_per_word = rules.get("strokes_per_word") or scoring_rules.get("strokes_per_word") or 5
    try:
        strokes_per_word = max(1, int(strokes_per_word))
    except (TypeError, ValueError):
        strokes_per_word = 5
    score = None
    qualification = None
    qualification_note = "Qualification is not configured."
    permitted_error_count = excess_error_count = net_words = None
    marks_minimum = None
    if scoring_mode == "CORRECT_WORDS":
        net_wpm = round(correct_words / minutes, 2)
    elif scoring_mode == "NET_WPM":
        error_strokes = scoring_rules.get("error_unit_strokes", strokes_per_word)
        try:
            error_strokes = max(0, int(error_strokes))
        except (TypeError, ValueError):
            error_strokes = strokes_per_word
        net_wpm = round(max(0, (len(typed) - error_count * error_strokes) / strokes_per_word / minutes), 2)
    elif scoring_mode == "STROKE_PENALTY":
        penalty_strokes = rules.get("mistake_penalty_strokes") or scoring_rules.get("mistake_penalty_strokes") or 0
        try:
            penalty_strokes = max(0, int(penalty_strokes))
        except (TypeError, ValueError):
            penalty_strokes = 0
        net_wpm = round(max(0, (len(typed) - error_count * penalty_strokes) / strokes_per_word / minutes), 2)
    elif scoring_mode == "CORRECT_WORD_MARKS":
        marks_per_word = scoring_rules.get("marks_per_correct_word", 0)
        try:
            score = round(correct_words * max(0, float(marks_per_word)), 2)
        except (TypeError, ValueError):
            score = 0
        # Marks cannot exceed the configured maximum, whatever the passage length.
        try:
            if scoring_rules.get("maximum_marks") is not None:
                score = min(score, round(float(scoring_rules["maximum_marks"]), 2))
        except (TypeError, ValueError):
            pass
        try:
            if scoring_rules.get("minimum_marks") is not None:
                marks_minimum = float(scoring_rules["minimum_marks"])
        except (TypeError, ValueError):
            marks_minimum = None
    elif scoring_mode in {"ERROR_PERCENTAGE", "QUALIFYING_ONLY"}:
        try:
            allowance = float(rules.get("error_allowance_percent"))
        except (TypeError, ValueError):
            allowance = None
        error_percent = round(error_count * 100 / max(1, gross_words), 2)
        permitted_error_count = max(0, int(gross_words * allowance / 100)) if allowance is not None else None
        excess_error_count = max(0, error_count - permitted_error_count) if permitted_error_count is not None else 0
        deduction_words = scoring_rules.get("excess_mistake_deduction_words", 0)
        try:
            deduction_words = max(0, int(deduction_words))
        except (TypeError, ValueError):
            deduction_words = 0
        net_words = max(0, gross_words - excess_error_count * deduction_words)
        if deduction_words:
            net_wpm = round(net_words / minutes, 2)
        try:
            minimum_wpm = float(rules.get("minimum_wpm"))
        except (TypeError, ValueError):
            minimum_wpm = None
        checks = []
        if allowance is not None:
            checks.append(error_percent <= allowance)
        if minimum_wpm is not None:
            checks.append(net_wpm >= minimum_wpm)
        if rules.get("verification_status") == "VERIFIED" and checks:
            qualification = all(checks)
            qualification_note = "Qualification calculated from the configured speed and error thresholds."
        else:
            qualification_note = "Qualification remains pending: verified source and at least one configured threshold are required."
    elif scoring_mode == "CUSTOM":
        formula = scoring_rules.get("formula")

        if formula == "STROKE_NET_WPM":
            try:
                mistake_penalty_wpm = max(
                    0,
                    float(scoring_rules.get("mistake_penalty_wpm", 1)),
                )
            except (TypeError, ValueError):
                mistake_penalty_wpm = 1

            tentative_wpm = round(
                stroke_count_for_speed / strokes_per_word / minutes,
                2,
            )

            net_wpm = round(
                max(0, tentative_wpm - error_count * mistake_penalty_wpm),
                2,
            )
        else:
            penalty_words = scoring_rules.get("mistake_penalty_words", 0)
            try:
                penalty_words = max(0, int(penalty_words))
            except (TypeError, ValueError):
                penalty_words = 0

            if penalty_words:
                net_words = max(0, gross_words - error_count * penalty_words)
                net_wpm = round(net_words / minutes, 2)

        disqualify_at = scoring_rules.get("disqualify_at_mistakes")
        try:
            disqualify_at = int(disqualify_at) if disqualify_at is not None else None
        except (TypeError, ValueError):
            # A malformed admin value must not crash submission; it disables the rule instead.
            disqualify_at = None
        if disqualify_at is not None and error_count >= disqualify_at:
            score = 0
            qualification = (
                False if rules.get("verification_status") == "VERIFIED" else None
            )
            qualification_note = (
                "Disqualification threshold reached."
                if qualification is not None
                else "Disqualification threshold reached in practice; official qualification is not claimed."
            )

        bands = scoring_rules.get("score_bands") or []
        if bands:
            eligible = []
            for band in bands:
                try:
                    threshold, marks = float(band[0]), float(band[1])
                except (TypeError, ValueError, IndexError):
                    continue

                if net_wpm >= threshold:
                    eligible.append(marks)

            if eligible and score is None:
                score = max(eligible)

        if not bands and score is None:
            qualification_note = (
                "Custom scoring data is stored, but no executable score formula is configured."
            )
    elif scoring_mode == "FULL_HALF_MISTAKES":
        qualification_note = "Full/half mistake classification requires exam-specific categories in scoring_rules; no generic classification was assumed."

    error_percent_for_qualification = round(error_count * 100 / max(1, gross_words), 2)
    qualification_metrics = {
        "net_wpm": net_wpm, "gross_wpm": gross_wpm,
        "accuracy_percent": accuracy, "error_percent": error_percent_for_qualification,
        "score": score, "correct_words": correct_words, "word_errors": word_errors,
    }
    qualification_status = "PENDING"
    configured_qualification = rules.get("qualification_rules") or {}
    if rules.get("verification_status") == "VERIFIED" and configured_qualification:
        evaluated, qualification_note = _evaluate_qualification_rules(configured_qualification, qualification_metrics)
        qualification = evaluated
        if evaluated is not None:
            qualification_status = "QUALIFIED" if evaluated else "NOT_QUALIFIED"
    elif rules.get("verification_status") != "VERIFIED":
        qualification = None
        qualification_note = "Qualification is pending because the exam rules are not verified."
    elif qualification is not None:
        qualification_status = "QUALIFIED" if qualification else "NOT_QUALIFIED"

    # Minimum marks qualify a verified CORRECT_WORD_MARKS attempt when no explicit
    # qualification rules are configured. Unverified attempts never receive a claim.
    if (
        rules.get("verification_status") == "VERIFIED"
        and not configured_qualification
        and marks_minimum is not None
        and score is not None
    ):
        qualification = score >= marks_minimum
        qualification_status = "QUALIFIED" if qualification else "NOT_QUALIFIED"
        qualification_note = "Qualification calculated from the configured minimum marks."

    return {
        "scoring_version": SCORING_VERSION,
        "duration_seconds": duration,
        "typed_characters": len(typed),
        "reported_keystrokes": reported_keystrokes,
                "stroke_count_for_speed": stroke_count_for_speed,
        "stroke_count_source": stroke_count_source,
        "tentative_wpm": tentative_wpm,
        "keystroke_count_source": "client_reported" if reported_keystrokes is not None else None,
        "required_keystrokes": required_keystrokes,
        "required_keystrokes_met": required_keystrokes_met,
        "reference_characters": len(reference),
        **chars,
        "word_errors": word_errors,
        "correct_words": correct_words,
        "gross_words": gross_words,
        "scoring_mode": scoring_mode,
        "score": score,
        "permitted_error_count": permitted_error_count,
        "excess_error_count": excess_error_count,
        "net_words": net_words,
        "error_count": error_count,
        "mistake_analysis": mistake_analysis,
        "mistake_categories": (
            mistake_analysis["categories"]
            if mistake_analysis is not None
            else None
),
        "error_count_method": "word" if count_word_errors else "character",
        "accuracy_percent": accuracy,
        "gross_wpm": gross_wpm,
        "correct_wpm": correct_wpm,
        "net_wpm": net_wpm,
        "qualification": qualification,
        "qualification_status": qualification_status,
        "qualification_note": (
            "Qualification is not calculated because exam rules are not verified."
            if rules.get("verification_status") != "VERIFIED" and qualification is None
            else qualification_note
        ),
    }
