"""Deterministic server-side scoring for a single submitted typing attempt."""
from difflib import SequenceMatcher
import re

SCORING_VERSION = "tsz-char-word-v1"


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
    ref_words = re.findall(r"\\S+", reference)
    typed_words = re.findall(r"\\S+", typed)
    matcher = SequenceMatcher(a=ref_words, b=typed_words, autojunk=False)
    errors = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        errors += max(i2 - i1, j2 - j1)
    return errors


def calculate_result(*, reference, typed, duration_seconds, rules):
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
    return {
        "scoring_version": SCORING_VERSION,
        "duration_seconds": duration,
        "typed_characters": len(typed),
        "reference_characters": len(reference),
        **chars,
        "word_errors": word_errors,
        "error_count": error_count,
        "error_count_method": "word" if count_word_errors else "character",
        "accuracy_percent": accuracy,
        "gross_wpm": gross_wpm,
        "correct_wpm": correct_wpm,
        "net_wpm": net_wpm,
        "qualification": None,
        "qualification_note": (
            "Qualification is not calculated because exam rules are not verified."
            if rules.get("verification_status") != "VERIFIED"
            else "Qualification thresholds must be explicitly configured and validated."
        ),
    }
