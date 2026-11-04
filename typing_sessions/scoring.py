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
    ref_words = re.findall(r"\\S+", reference)
    typed_words = re.findall(r"\\S+", typed)
    matcher = SequenceMatcher(a=ref_words, b=typed_words, autojunk=False)
    return sum(i2 - i1 for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag == "equal")


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

    scoring_mode = rules.get("scoring_mode", "GENERIC")
    scoring_rules = rules.get("scoring_rules") or {}
    correct_words = _count_correct_words(reference, typed)
    gross_words = len(re.findall(r"\\S+", typed))
    strokes_per_word = rules.get("strokes_per_word") or scoring_rules.get("strokes_per_word") or 5
    try:
        strokes_per_word = max(1, int(strokes_per_word))
    except (TypeError, ValueError):
        strokes_per_word = 5
    score = None
    qualification = None
    qualification_note = "Qualification is not configured."
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
        error_percent = round(error_count * 100 / max(1, gross_words), 2)
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
    elif scoring_mode == "FULL_HALF_MISTAKES":
        qualification_note = "Full/half mistake classification requires exam-specific categories in scoring_rules; no generic classification was assumed."
    elif scoring_mode == "QUALIFYING_ONLY":
        score = None

    return {
        "scoring_version": SCORING_VERSION,
        "duration_seconds": duration,
        "typed_characters": len(typed),
        "reference_characters": len(reference),
        **chars,
        "word_errors": word_errors,
        "correct_words": correct_words,
        "gross_words": gross_words,
        "scoring_mode": scoring_mode,
        "score": score,
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
