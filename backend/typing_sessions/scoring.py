"""Deterministic server-side scoring for a single submitted typing attempt."""
from difflib import SequenceMatcher
import hashlib
import json
import re

from exams.scoring_registry import resolve_scoring_specification

SCORING_VERSION = "tsz-char-word-v3"


def _count_character_errors(reference, typed):
    matcher = SequenceMatcher(a=reference, b=typed, autojunk=False)
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
    ref_words = re.findall(r"\S+", reference)
    typed_words = re.findall(r"\S+", typed)
    matcher = SequenceMatcher(a=ref_words, b=typed_words, autojunk=False)
    errors = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        errors += max(i2 - i1, j2 - j1)
    return errors



def _count_correct_words(reference, typed):
    ref_words = re.findall(r"\S+", reference)
    typed_words = re.findall(r"\S+", typed)
    matcher = SequenceMatcher(a=ref_words, b=typed_words, autojunk=False)
    return sum(i2 - i1 for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag == "equal")




def _classify_full_half_mistakes(reference, typed, config):
    """Apply only exact, explicitly configured word-pair classifications.

    Config contract:
      {"version": 1, "unit": "word", "overrides": [
        {"reference": "word", "typed": "typed-word", "classification": "FULL"}
      ]}
    Empty strings represent an inserted or deleted word. No fuzzy matching,
    defaults, or inferred classifications are applied.
    """
    unresolved = {
        "status": "UNRESOLVED",
        "full_mistakes": None,
        "half_mistakes": None,
        "ignored_mistakes": None,
        "weighted_mistakes": None,
        "classified_error_cases": 0,
        "unclassified_error_cases": None,
        "error_cases": [],
        "reason": "A supported version-1 word classification configuration is required.",
    }
    if not isinstance(config, dict) or config.get("version") != 1 or config.get("unit") != "word":
        return unresolved

    overrides = config.get("overrides")
    if not isinstance(overrides, list):
        return unresolved

    source_reference = config.get("source_reference")
    if not isinstance(source_reference, dict):
        source_reference = {}
    source_audit = {
        "status": "VERIFIED" if all(source_reference.get(key) for key in ("url", "title", "locator", "checked_at")) else "PENDING",
        "url": source_reference.get("url"),
        "title": source_reference.get("title"),
        "locator": source_reference.get("locator"),
        "checked_at": source_reference.get("checked_at"),
    }
    lookup = {}
    for item in overrides:
        if not isinstance(item, dict):
            return unresolved
        if not isinstance(item.get("reference"), str) or not isinstance(item.get("typed"), str):
            return unresolved
        classification = item.get("classification")
        if classification not in {"FULL", "HALF", "IGNORED"}:
            return unresolved
        key = (item["reference"], item["typed"])
        if key in lookup:
            return unresolved
        lookup[key] = classification

    reference_words = re.findall(r"\S+", reference)
    typed_words = re.findall(r"\S+", typed)
    matcher = SequenceMatcher(a=reference_words, b=typed_words, autojunk=False)
    cases = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        ref_segment = reference_words[i1:i2]
        typed_segment = typed_words[j1:j2]
        pairs = []
        paired = min(len(ref_segment), len(typed_segment))
        pairs.extend(zip(ref_segment[:paired], typed_segment[:paired]))
        pairs.extend((word, "") for word in ref_segment[paired:])
        pairs.extend(("", word) for word in typed_segment[paired:])
        cases.extend(pairs)

    counts = {"FULL": 0, "HALF": 0, "IGNORED": 0}
    classified_cases = []
    for reference_word, typed_word in cases:
        classification = lookup.get((reference_word, typed_word))
        if classification is None:
            result = dict(unresolved)
            result["unclassified_error_cases"] = len(cases) - len(classified_cases)
            result["classified_error_cases"] = len(classified_cases)
            result["error_cases"] = classified_cases + [{
                "reference": reference_word,
                "typed": typed_word,
                "classification": "UNCLASSIFIED",
            }]
            result["rule_source"] = source_audit
            result["classification_config_version"] = config.get("version")
            result["reason"] = "At least one error case has no exact configured classification."
            return result
        counts[classification] += 1
        classified_cases.append({
            "reference": reference_word,
            "typed": typed_word,
            "classification": classification,
            "rule_source": source_audit,
        })

    return {
        "status": "CLASSIFIED",
        "classification_config_version": config.get("version"),
        "rule_source": source_audit,
        "full_mistakes": counts["FULL"],
        "half_mistakes": counts["HALF"],
        "ignored_mistakes": counts["IGNORED"],
        "weighted_mistakes": round(counts["FULL"] + counts["HALF"] * 0.5, 2),
        "classified_error_cases": len(classified_cases),
        "unclassified_error_cases": 0,
        "error_cases": classified_cases,
        "reason": "All word-level error cases matched exact configured classifications.",
    }

def calculate_result(*, reference, typed, duration_seconds, rules, reported_keystrokes=None):
    """Calculate metrics exclusively from persisted source text and submitted text."""
    duration = max(1, int(duration_seconds))
    minutes = duration / 60
    chars = _count_character_errors(reference, typed)
    denominator = max(len(reference), len(typed), 1)
    accuracy = round(chars["correct_characters"] * 100 / denominator, 2)
    gross_wpm = round(len(typed) / 5 / minutes, 2)
    correct_wpm = round(chars["correct_characters"] / 5 / minutes, 2)
    word_errors = _count_word_errors(reference, typed)
    error_rules = rules.get("error_rules") or {}
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
    required_keystrokes_met = (
        reported_keystrokes >= required_keystrokes
        if reported_keystrokes is not None and required_keystrokes is not None
        else None
    )
    scoring_mode = rules.get("scoring_mode", "GENERIC")
    scoring_specification = resolve_scoring_specification(rules)
    scoring_rules = rules.get("scoring_rules") or {}
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
    error_percent = None
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
    elif scoring_mode in {"ERROR_PERCENTAGE", "QUALIFYING_ONLY"}:
        try:
            allowance = float(rules.get("error_allowance_percent"))
        except (TypeError, ValueError):
            allowance = None
        # A word-based allowance must use word-based errors. Character
        # errors divided by a word count mixes units and can produce invalid
        # qualification decisions, so legacy ambiguous configurations remain
        # pending until their error unit is explicitly configured.
        error_percent = (
            round(word_errors * 100 / max(1, gross_words), 2)
            if count_word_errors else None
        )
        permitted_error_count = (
            max(0, int(gross_words * allowance / 100))
            if allowance is not None and count_word_errors else None
        )
        excess_error_count = (
            max(0, error_count - permitted_error_count)
            if permitted_error_count is not None else None
        )
        deduction_words = scoring_rules.get("excess_mistake_deduction_words", 0)
        try:
            deduction_words = max(0, int(deduction_words))
        except (TypeError, ValueError):
            deduction_words = 0
        net_words = (
            max(0, gross_words - excess_error_count * deduction_words)
            if excess_error_count is not None else None
        )
        if deduction_words and net_words is not None:
            net_wpm = round(net_words / minutes, 2)
        try:
            minimum_wpm = float(rules.get("minimum_wpm"))
        except (TypeError, ValueError):
            minimum_wpm = None
        checks = []
        if allowance is not None and error_percent is not None:
            checks.append(error_percent <= allowance)
        if minimum_wpm is not None:
            checks.append(net_wpm >= minimum_wpm)
        allowance_unresolved = allowance is not None and error_percent is None
        if rules.get("verification_status") == "VERIFIED" and checks and not allowance_unresolved:
            qualification = all(checks)
            qualification_note = "Qualification calculated from the configured speed and error thresholds."
        elif allowance_unresolved:
            qualification_note = "Qualification remains pending: the configured error allowance cannot be evaluated because its error unit is unresolved."
        else:
            qualification_note = "Qualification remains pending: verified source and at least one configured threshold are required."
    elif scoring_mode == "CUSTOM":
        penalty_words = scoring_rules.get("mistake_penalty_words", 0)
        try:
            penalty_words = max(0, int(penalty_words))
        except (TypeError, ValueError):
            penalty_words = 0
        if penalty_words:
            net_words = max(0, gross_words - error_count * penalty_words)
            net_wpm = round(net_words / minutes, 2)
        disqualify_at = scoring_rules.get("disqualify_at_mistakes")
        if disqualify_at is not None and error_count >= int(disqualify_at):
            score = 0
            qualification = False if rules.get("verification_status") == "VERIFIED" else None
            qualification_note = "Disqualification threshold reached." if qualification is not None else "Disqualification threshold reached in practice; official qualification is not claimed."
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
            qualification_note = "Custom scoring data is stored, but no executable score formula is configured."
    elif scoring_mode == "FULL_HALF_MISTAKES":
        classification = _classify_full_half_mistakes(
            reference, typed, scoring_rules.get("mistake_classification")
        )
        qualification_note = (
            "Mistake categories were classified from exact configured word pairs; "
            "an official score formula and qualification rule are not configured."
            if classification["status"] == "CLASSIFIED"
            else "Full/half mistake result remains pending: " + classification["reason"]
        )

    if qualification is not None and not scoring_specification["qualification_eligible"]:
        qualification = None
        qualification_note = "Qualification remains pending: the registered scoring formula is incomplete or its scoring/qualification evidence is not verified."

    return {
        "scoring_version": SCORING_VERSION,
        "scoring_specification": scoring_specification,
        "scoring_audit": {
            "engine_version": SCORING_VERSION,
            "rule_config_version": rules.get("rule_config_version"),
            "verification_status": rules.get("verification_status", "UNVERIFIED"),
            "official_source_url": rules.get("official_source_url"),
            "source_title": rules.get("canonical_specification", {}).get("provenance", {}).get("source_title"),
            "source_checked_at": rules.get("canonical_specification", {}).get("provenance", {}).get("source_checked_at"),
            "scoring_rules_sha256": hashlib.sha256(json.dumps(
                scoring_rules, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")).hexdigest(),
        },
        "duration_seconds": duration,
        "typed_characters": len(typed),
        "reported_keystrokes": reported_keystrokes,
        "keystroke_count_source": "client_reported" if reported_keystrokes is not None else None,
        "required_keystrokes": required_keystrokes,
        "required_keystrokes_met": required_keystrokes_met,
        "keystroke_verification": (
            "UNVERIFIED_CLIENT_TELEMETRY" if reported_keystrokes is not None else "NOT_REPORTED"
        ),
        "reference_characters": len(reference),
        **chars,
        "word_errors": word_errors,
        "correct_words": correct_words,
        "gross_words": gross_words,
        "scoring_mode": scoring_mode,
        "mistake_classification": classification if scoring_mode == "FULL_HALF_MISTAKES" else None,
        "score": score,
        "error_percent": error_percent,
        "error_percentage_unit": (
            "WORDS" if error_percent is not None
            else "UNRESOLVED" if scoring_mode in {"ERROR_PERCENTAGE", "QUALIFYING_ONLY"}
            else "NOT_APPLICABLE"
        ),
        "permitted_error_count": permitted_error_count,
        "excess_error_count": excess_error_count,
        "net_words": net_words,
        "error_count": error_count,
        "error_count_method": "word" if count_word_errors else "character",
        "accuracy_percent": accuracy,
        "gross_wpm": gross_wpm,
        "correct_wpm": correct_wpm,
        "net_wpm": net_wpm,
        "qualification": qualification,
        "qualification_note": (
            "Qualification is not calculated because exam rules are not verified."
            if rules.get("verification_status") != "VERIFIED" and qualification is None
            else qualification_note
        ),
    }
