"""Deterministic server-side scoring for a single submitted typing attempt."""
from difflib import SequenceMatcher

from .word_grading import grade_words
import re
import unicodedata
from .mistake_classification import classify_typing_mistakes
SCORING_VERSION = "tsz-char-word-v3"



def _attempted_reference_prefix(reference, typed):
    """Ignore only the untyped trailing suffix, retaining omissions inside typed work."""
    reference = reference or ""
    typed = typed or ""
    typed_words = re.findall(r"\S+", typed)
    reference_spans = list(re.finditer(r"\S+", reference))
    if not typed_words or not reference_spans:
        return ""

    reference_words = [match.group(0) for match in reference_spans]
    matcher = SequenceMatcher(a=reference_words, b=typed_words, autojunk=False)
    # SequenceMatcher can group a final typo and all later reference words
    # into one replace opcode. Use matching blocks plus the number of typed
    # words after the last match so only actually attempted words are included.
    blocks = [block for block in matcher.get_matching_blocks() if block.size]
    if blocks:
        last_block = max(blocks, key=lambda block: block.b + block.size)
        matched_reference_end = max(block.a + block.size for block in blocks)
        matched_typed_end = last_block.b + last_block.size
        trailing_typed_words = len(typed_words) - matched_typed_end
        reached_reference_words = min(
            len(reference_words),
            matched_reference_end + trailing_typed_words,
        )
    else:
        reached_reference_words = min(len(reference_words), len(typed_words))
    if reached_reference_words <= 0:
        return ""
    end = reference_spans[reached_reference_words - 1].end()
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
    """Word errors in the typed text only (see word_grading.grade_words)."""
    return grade_words(reference, typed)["errors"]


def _count_correct_words(reference, typed):
    ref_words = re.findall(r"\S+", _attempted_reference_prefix(reference, typed))
    typed_words = re.findall(r"\S+", typed)
    matcher = SequenceMatcher(a=ref_words, b=typed_words, autojunk=False)
    return sum(i2 - i1 for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag == "equal")


def _classify_dpa_mistakes(reference, typed):
    """DPA-specific weighted mistake profile layered over the shared classifier."""
    analysis = classify_typing_mistakes(reference, typed)
    categories = dict(analysis["categories"])
    categories.setdefault("transposition", 0)
    categories.setdefault("paragraph_indentation", 0)
    reference_words = re.findall(r"\S+", reference or "")
    typed_words = re.findall(r"\S+", typed or "")
    matcher = SequenceMatcher(None, reference_words, typed_words, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        expected, actual = reference_words[i1:i2], typed_words[j1:j2]
        if tag == "replace" and len(expected) > 1 and len(actual) == 1:
            clean_expected = "".join(re.sub(r"[^\w]", "", word).casefold() for word in expected)
            clean_actual = re.sub(r"[^\w]", "", actual[0]).casefold()
            if clean_expected == clean_actual:
                categories["substitution"] = max(0, categories.get("substitution", 0) - len(expected))
                categories["word_spacing"] = categories.get("word_spacing", 0) + 1
    swaps = 0
    for index in range(min(len(reference_words), len(typed_words)) - 1):
        if reference_words[index] == typed_words[index + 1] and reference_words[index + 1] == typed_words[index]:
            if categories.get("omission", 0) and categories.get("addition", 0):
                categories["omission"] -= 1
                categories["addition"] -= 1
            elif categories.get("substitution", 0) >= 2:
                categories["substitution"] -= 2
            swaps += 1
    # A swap the shared classifier already counted is not counted again.
    categories["transposition"] = max(categories.get("transposition", 0), swaps)
    for expected, actual in zip((reference or "").splitlines(), (typed or "").splitlines()):
        if expected.startswith("\t") and actual.startswith(" ") and not actual.startswith("\t"):
            if categories.get("word_spacing", 0):
                categories["word_spacing"] -= 1
            elif categories.get("paragraph_breaks", 0):
                categories["paragraph_breaks"] -= 1
            categories["paragraph_indentation"] += 1
    analysis["categories"] = categories
    analysis["total_detected_errors"] = sum(categories.values())
    return analysis


def _evaluate_qualification_rules(config, metrics):
    """Evaluate explicit threshold conditions; unsupported conditions remain pending."""
    if not isinstance(config, dict) or not config:
        return None, "Qualification is pending: no qualification conditions are configured."
    allowed_metrics = {"net_wpm", "gross_wpm", "accuracy_percent", "error_percent", "score", "correct_words", "word_errors", "keystrokes", "gross_words"}
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

    # Always retain the same RKC-style diagnostic classification for every display mode.
    # The configured exam scoring formula below remains authoritative for the numeric result.
    mistake_analysis = (
        _classify_dpa_mistakes(reference, typed)
        if scoring_mode == "CUSTOM" and scoring_rules.get("formula") == "SSC_DPA_GRADE_A"
        else classify_typing_mistakes(reference, typed)
    )

    if scoring_mode == "CUSTOM" and scoring_rules.get("formula") in {"DELHI_POLICE_MODEL_D", "SSC_DPA_GRADE_A"}:
        categories = mistake_analysis["categories"]
        full_mistakes = sum(categories.get(key, 0) for key in ("omission", "substitution", "addition"))
        half_mistakes = sum(categories.get(key, 0) for key in ("capitalization", "punctuation", "internal_spacing", "word_spacing", "paragraph_breaks", "transposition"))
        error_count = full_mistakes + (half_mistakes / 2)
        count_word_errors = True
    elif scoring_mode == "CUSTOM" and scoring_rules.get("formula") == "STROKE_NET_WPM":
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
    score_note = None
    full_mistakes = half_mistakes = None
    qualification = None
    qualification_note = "Qualification is not configured."
    permitted_error_count = excess_error_count = net_words = None
    marks_minimum = None
    gross_kdph = error_percent = candidate_category = error_cap = None
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

        if formula == "DELHI_POLICE_HCM_2025":
            categories = mistake_analysis["categories"]
            # SSC Notice 2025, para 24.2: one word is deducted per mistake.
            # The listed error types are charged as whole mistakes, not half mistakes.
            full_mistakes = sum(categories.get(key, 0) for key in (
                "omission", "substitution", "addition", "capitalization",
                "punctuation", "internal_spacing", "word_spacing", "paragraph_breaks"
            )) + (2 * categories.get("transposition", 0))
            half_mistakes = 0
            error_count = full_mistakes
            count_word_errors = True
            gross_strokes = max(0, int(stroke_count_for_speed or 0))
            gross_words = gross_strokes / 5
            gross_wpm = gross_words / minutes
            tentative_wpm = gross_wpm
            net_wpm = max(0, gross_wpm - (error_count / minutes))
            # Compare unrounded speed directly to the published integer band boundaries.
            # The notice does not specify a separate rounding rule.
            band_speed = net_wpm
            language = str(rules.get("language") or rules.get("language_code") or "").upper()
            minimum_wpm = float(scoring_rules.get("minimum_wpm", 25 if language in {"HINDI", "HI"} else 30))
            default_bands = (
                [{"minimum_wpm": 45, "marks": 25}, {"minimum_wpm": 41, "marks": 21},
                 {"minimum_wpm": 36, "marks": 18}, {"minimum_wpm": 31, "marks": 15},
                 {"minimum_wpm": 26, "marks": 12}, {"minimum_wpm": 25, "marks": 10}]
                if minimum_wpm == 25 else
                [{"minimum_wpm": 51, "marks": 25}, {"minimum_wpm": 46, "marks": 21},
                 {"minimum_wpm": 41, "marks": 18}, {"minimum_wpm": 36, "marks": 15},
                 {"minimum_wpm": 31, "marks": 12}, {"minimum_wpm": 30, "marks": 10}]
            )
            score = 0
            for band in scoring_rules.get("marks_bands") or default_bands:
                try:
                    if band_speed >= float(band["minimum_wpm"]):
                        score = max(score, float(band["marks"]))
                except (TypeError, ValueError, KeyError):
                    continue
            qualification = net_wpm >= minimum_wpm
            if not qualification:
                score = 0
            provisional_label = "Provisional " if rules.get("verification_status") != "VERIFIED" else ""
            qualification_note = (
                f"{provisional_label}{'qualified' if qualification else 'disqualified'}: "
                f"actual speed {net_wpm:.2f} WPM; minimum required {minimum_wpm:g} WPM."
            )
            score_note = (
                f"Delhi Police HCM 2025: {gross_strokes} strokes / 5 = {gross_words:.2f} words; "
                f"tentative speed {gross_wpm:.2f} WPM; {error_count} mistakes deducted; "
                f"actual speed {net_wpm:.2f} WPM; marks {score:g}/25."
            )
            error_percent = None
        if formula == "RRB_CBTST_5_PERCENT":
            categories = mistake_analysis["categories"]
            full_mistakes = sum(categories.get(key, 0) for key in ("omission", "substitution", "addition"))
            half_mistakes = sum(categories.get(key, 0) for key in (
                "capitalization", "punctuation", "internal_spacing",
                "word_spacing", "paragraph_breaks", "transposition"
            ))
            error_count = full_mistakes + (half_mistakes / 2)
            count_word_errors = True
            gross_words = len(re.findall(r"\S+", typed))
            ignored_mistakes = gross_words * float(scoring_rules.get("mistake_allowance_percent", 5)) / 100
            excess_error_count = max(0, error_count - ignored_mistakes)
            permitted_error_count = ignored_mistakes
            deduction_words = int(scoring_rules.get("excess_mistake_deduction_words", 10))
            net_words = max(0, gross_words - excess_error_count * deduction_words)
            net_wpm = round(net_words / minutes, 2)
            error_percent = round(error_count * 100 / max(1, gross_words), 2)
            score_note = (
                "RRB CBTST: "
                + f"{ignored_mistakes:.2f} mistakes forgiven (5% of {gross_words} words); "
                + f"{excess_error_count:.2f} excess weighted mistakes deducted at {deduction_words} words each."
            )
        # Rulebook-wide scoring models. Each profile supplies its own thresholds,
        # duration, stroke floor, and optional merit conversion in scoring_rules.
        if formula in {"MODEL_A", "MODEL_B", "MODEL_C1", "MODEL_C2", "MODEL_D"}:
            categories = mistake_analysis["categories"]
            full_mistakes = sum(categories.get(key, 0) for key in (
                "omission", "substitution", "addition"
            ))
            half_mistakes = sum(categories.get(key, 0) for key in (
                "capitalization", "punctuation", "internal_spacing",
                "word_spacing", "paragraph_breaks", "transposition"
            ))
            error_count = full_mistakes + half_mistakes / 2
            count_word_errors = True
            reference_word_count = len(re.findall(r"\S+", reference))
            # Provisional profiles use browser telemetry for actual key depressions;
            # verified profiles use the server-derived fallback, never client input.
            gross_strokes = stroke_count_for_speed
            gross_words_from_strokes = gross_strokes / strokes_per_word
            error_percent = round(error_count * 100 / max(1, reference_word_count), 2)
            permitted_error_count = max(0, int(reference_word_count * float(rules.get("error_allowance_percent") or 0) / 100))
            minimum_strokes = scoring_rules.get("minimum_strokes")
            try:
                minimum_strokes = int(minimum_strokes) if minimum_strokes is not None else None
            except (TypeError, ValueError):
                minimum_strokes = None
            stroke_floor_met = minimum_strokes is None or gross_strokes >= minimum_strokes

            if formula == "MODEL_A":
                net_wpm = round(gross_words_from_strokes / minutes, 2)
                score_note = "Model A: qualification depends on the configured minimum stroke floor and category-specific weighted error cap."
                if not stroke_floor_met:
                    score = 0
                    score_note = "Disqualified: minimum gross keystroke floor not met."
            elif formula == "MODEL_B":
                ignored_mistakes = 0.05 * gross_words_from_strokes
                chargeable_mistakes = max(0, error_count - ignored_mistakes)
                net_words = max(0, gross_words_from_strokes - chargeable_mistakes * 10)
                net_wpm = round(net_words / minutes, 2)
                permitted_error_count = round(ignored_mistakes, 2)
                excess_error_count = round(chargeable_mistakes, 2)
                score_note = "Model B: first 5% weighted mistakes are ignored; each excess mistake deducts 10 words."
            elif formula == "MODEL_C1":
                net_words = max(0, gross_words_from_strokes - error_count)
                net_wpm = round(net_words / minutes, 2)
                score_note = "Model C1: each full mistake deducts one word and each half mistake deducts half a word."
            elif formula == "MODEL_C2":
                penalty_strokes = error_count * 50
                net_wpm = round(max(0, gross_strokes - penalty_strokes) / (strokes_per_word * minutes), 2)
                score_note = "Model C2: each full mistake deducts 50 strokes and each half mistake deducts 25 strokes."
            else:  # MODEL_D
                net_wpm = round(gross_words_from_strokes / minutes, 2)
                bands = scoring_rules.get("score_bands") or []
                eligible_marks = []
                for band in bands:
                    try:
                        threshold, marks = float(band[0]), float(band[1])
                    except (TypeError, ValueError, IndexError):
                        continue
                    if net_wpm >= threshold:
                        eligible_marks.append(marks)
                if eligible_marks:
                    maximum = float(scoring_rules.get("maximum_marks", 100))
                    score = min(maximum, max(0.0, max(eligible_marks)))
                score_note = (
                    "Model D: merit conversion bands are not configured; numeric marks are pending."
                    if not bands else "Model D: marks calculated from the configured speed/merit bands."
                )
            qualification_rules = rules.get("qualification_rules") or {}
            if isinstance(qualification_rules, dict):
                qualification = None
                qualification_note = score_note
        if formula in {"SSC_CGL_2025_DEST", "SSC_CGL_2025_VH_DEST"}:
            categories = mistake_analysis["categories"]
            full_mistakes = sum(categories.get(key, 0) for key in (
                "omission", "substitution", "addition", "spelling", "incomplete_word", "repeated_word"
            ))
            half_mistakes = sum(categories.get(key, 0) for key in (
                "capitalization", "punctuation", "internal_spacing", "word_spacing",
                "paragraph_breaks", "paragraph_indentation", "transposition"
            ))
            error_count = full_mistakes + (half_mistakes * 0.5)
            count_word_errors = True
            gross_strokes = max(0, int(stroke_count_for_speed or 0))
            gross_kdph = round(gross_strokes * 3600 / duration, 2)
            gross_wpm = round(gross_strokes / 5 / minutes, 2)
            gross_words = len(re.findall(r"\S+", typed))
            reference_word_count = len(re.findall(r"\S+", reference))
            denominator_words = max(1, len(re.findall(r"\S+", typed)))
            error_percent = round(error_count * 100 / denominator_words, 2)
            candidate_category = str(
                rules.get("candidate_category")
                or scoring_rules.get("candidate_category_default")
                or "UR"
            ).upper()
            standard = str(scoring_rules.get("standard_type") or "NORMAL").upper()
            caps_key = "higher_error_caps" if standard == "HIGHER" else "normal_error_caps"
            caps = scoring_rules.get(caps_key) or (
                {"UR": 5, "OBC": 7, "EWS": 7, "SC": 7, "ST": 7, "ESM": 7, "OH": 10, "HH": 10, "VH": 10, "PWD": 10}
                if standard == "HIGHER"
                else {"UR": 20, "OBC": 25, "EWS": 25, "SC": 30, "ST": 30, "ESM": 30, "OH": 30, "HH": 30, "VH": 30, "PWD": 30}
            )
            error_cap = float(caps.get(candidate_category, caps.get("OTHER", 30)))
            qualification = error_percent <= error_cap
            net_wpm = gross_wpm
            permitted_error_count = denominator_words * error_cap / 100
            excess_error_count = max(0, error_count - permitted_error_count)
            required_keystrokes = None
            required_keystrokes_met = None
            qualification_note = (
                f"SSC CGL DEST {standard.lower()} standard: {error_percent:.2f}% weighted mistakes "
                f"(maximum {error_cap:g}%, {candidate_category}); approximately {gross_strokes} strokes "
                f"at {gross_kdph:.0f} KDPH. The ~2,000-stroke passage size is not treated as a candidate minimum."
            )
            score = None
        elif formula == "SSC_DPA_GRADE_A":
            categories = mistake_analysis["categories"]
            full_mistakes = sum(categories.get(key, 0) for key in ("omission", "substitution", "addition", "spelling", "incomplete_word", "repeated_word"))
            half_mistakes = sum(categories.get(key, 0) for key in ("capitalization", "punctuation", "internal_spacing", "word_spacing", "paragraph_breaks", "paragraph_indentation", "transposition"))
            error_count = full_mistakes + (half_mistakes * 0.5)
            count_word_errors = True
            gross_strokes = max(0, int(stroke_count_for_speed or 0))
            gross_words_from_strokes = gross_strokes / strokes_per_word
            gross_kdph = round(gross_strokes * 3600 / duration, 2)
            gross_wpm = round(gross_words_from_strokes / minutes, 2)
            gross_words = gross_words_from_strokes
            reference_word_count = len(re.findall(r"\S+", reference))
            error_percent = round(error_count * 100 / max(1, reference_word_count), 2)
            minimum_kdph = int(scoring_rules.get("minimum_kdph", 15000))
            minimum_strokes = (minimum_kdph * duration + 3599) // 3600
            required_keystrokes = minimum_strokes
            required_keystrokes_met = gross_strokes >= minimum_strokes
            candidate_category = str(rules.get("candidate_category") or scoring_rules.get("candidate_category_default") or "UR").upper()
            caps = scoring_rules.get("category_error_caps") or {"UR": 5, "OBC": 7, "EWS": 7, "SC": 10, "ST": 10, "PWD": 10, "OTHER_RESERVED": 10}
            error_cap = float(caps.get(candidate_category, caps.get("OTHER_RESERVED", 10)))
            net_words = max(0, gross_words_from_strokes - error_count)
            net_wpm = round(net_words / minutes, 2)
            permitted_error_count = reference_word_count * error_cap / 100
            excess_error_count = max(0, error_count - permitted_error_count)
            qualification = bool(required_keystrokes_met and error_percent <= error_cap)
            qualification_note = f"DPA Grade-A: {gross_kdph:.0f} KDPH; weighted errors {error_percent:.2f}% / {error_cap:g}% ({candidate_category})."
            score = None
        elif formula == "SSC_CHSL_2025_ENGLISH":
            categories = mistake_analysis["categories"]
            full_mistakes = sum(categories.get(key, 0) for key in (
                "omission", "substitution", "addition"
            ))
            half_mistakes = sum(categories.get(key, 0) for key in (
                "capitalization", "punctuation", "internal_spacing",
                "word_spacing", "paragraph_breaks", "transposition"
            ))
            weighted_mistakes = full_mistakes + (0.5 * half_mistakes)
            error_count = weighted_mistakes
            count_word_errors = True
            reference_word_count = len(re.findall(r"\S+", reference))
            error_percent = round(
                weighted_mistakes * 100 / max(1, reference_word_count), 2
            )
            gross_strokes = max(0, int(stroke_count_for_speed or 0))
            gross_wpm = round(gross_strokes / 5 / minutes, 2)
            gross_kdph = round(gross_strokes * 60 / minutes, 2)
            net_wpm = gross_wpm
            candidate_category = str(
                rules.get("candidate_category")
                or scoring_rules.get("candidate_category_default")
                or "UR"
            ).upper()
            caps = scoring_rules.get("category_error_caps") or {
                "UR": 7, "OBC": 10, "EWS": 10, "SC": 10,
                "ST": 10, "PWD": 10, "OTHER_RESERVED": 10,
            }
            error_cap = float(caps.get(candidate_category, caps.get("OTHER_RESERVED", 10)))
            minimum_wpm = float(scoring_rules.get("minimum_wpm", 35))
            minimum_kdph = float(scoring_rules.get("minimum_kdph", 10500))
            minimum_strokes = int((minimum_kdph * duration + 3599) // 3600)
            required_keystrokes = minimum_strokes
            speed_met = gross_wpm >= minimum_wpm
            stroke_floor_met = gross_strokes >= minimum_strokes
            required_keystrokes_met = stroke_floor_met
            error_cap_met = error_percent <= error_cap
            qualification = bool(speed_met and stroke_floor_met and error_cap_met)
            qualification_note = (
                f"{'Meets' if qualification else 'Does not meet'} the configured CHSL 2025 English "
                f"criteria: {gross_wpm:.2f} WPM (minimum {minimum_wpm:g}), "
                f"{error_percent:.2f}% weighted errors (maximum {error_cap:g}%), "
                f"{gross_strokes}/{minimum_strokes} keystrokes."
            )
            score = None
        elif formula == "SSC_CHSL_2025_VH_ENGLISH":
            categories = mistake_analysis["categories"]
            full_mistakes = sum(categories.get(key, 0) for key in (
                "omission", "substitution", "addition"
            ))
            half_mistakes = sum(categories.get(key, 0) for key in (
                "capitalization", "punctuation", "internal_spacing",
                "word_spacing", "paragraph_breaks", "transposition",
            ))
            weighted_mistakes = full_mistakes + (0.5 * half_mistakes)
            error_count = weighted_mistakes
            count_word_errors = True
            reference_word_count = len(re.findall(r"\S+", reference))
            error_percent = round(weighted_mistakes * 100 / max(1, reference_word_count), 2)
            gross_strokes = max(0, int(stroke_count_for_speed or 0))
            # Use the actual configured duration, including only authorized compensatory time.
            # A 15-minute attempt must not be scored against the standard 10-minute denominator.
            scoring_duration = max(1, int(duration))
            scoring_minutes = scoring_duration / 60
            gross_wpm = round(gross_strokes / 5 / scoring_minutes, 2)
            gross_kdph = round(gross_strokes * 3600 / scoring_duration, 2)
            net_wpm = gross_wpm
            candidate_category = "PWD"
            error_cap = float(scoring_rules.get("category_error_caps", {}).get("PWD", 10))
            minimum_wpm = float(scoring_rules.get("minimum_wpm", 35))
            minimum_kdph = float(scoring_rules.get("minimum_kdph", 10500))
            minimum_strokes = int((minimum_kdph * scoring_duration + 3599) // 3600)
            required_keystrokes = minimum_strokes
            speed_met = gross_wpm >= minimum_wpm
            stroke_floor_met = gross_strokes >= minimum_strokes
            required_keystrokes_met = stroke_floor_met
            error_cap_met = error_percent <= error_cap
            qualification = bool(speed_met and stroke_floor_met and error_cap_met)
            qualification_note = (
                f"{'QUALIFIED' if qualification else 'NOT QUALIFIED'} — VH English: "
                f"{gross_wpm:.2f} WPM (minimum {minimum_wpm:g}), "
                f"{error_percent:.2f}% weighted errors (maximum {error_cap:g}%), "
                f"{gross_strokes}/{minimum_strokes} keystrokes."
            )
            score = None
        elif formula in {"SSC_CHSL_2025_HINDI", "SSC_CHSL_2025_HINDI_KRUTIDEV", "SSC_CHSL_2025_HINDI_MANGAL"}:
            categories = mistake_analysis["categories"]
            full_mistakes = sum(categories.get(key, 0) for key in ("omission", "substitution", "addition"))
            # Hindi typewriting has no capitalization distinction; count spelling/spacing/punctuation/transposition per SSC evaluation categories.
            half_mistakes = sum(categories.get(key, 0) for key in (
                "punctuation", "internal_spacing", "word_spacing", "paragraph_breaks", "transposition"
            ))
            weighted_mistakes = full_mistakes + (0.5 * half_mistakes)
            error_count = weighted_mistakes
            count_word_errors = True
            reference_word_count = len(re.findall(r"\S+", reference))
            error_percent = round(weighted_mistakes * 100 / max(1, reference_word_count), 2)
            gross_strokes = max(0, int(stroke_count_for_speed or 0))
            scoring_duration = max(1, int(duration))
            scoring_minutes = scoring_duration / 60
            gross_wpm = round(gross_strokes / 5 / scoring_minutes, 2)
            gross_kdph = round(gross_strokes * 3600 / scoring_duration, 2)
            net_wpm = gross_wpm
            candidate_category = str(rules.get("candidate_category") or scoring_rules.get("candidate_category_default") or "UR").upper()
            caps = scoring_rules.get("category_error_caps") or {"UR": 7, "OBC": 10, "EWS": 10, "SC": 10, "ST": 10, "ESM": 10, "OH": 10, "HH": 10, "VH": 10, "PWD": 10}
            error_cap = float(caps.get(candidate_category, caps.get("OTHER_RESERVED", 10)))
            minimum_wpm = float(scoring_rules.get("minimum_wpm", 30))
            minimum_kdph = float(scoring_rules.get("minimum_kdph", 9000))
            minimum_strokes = int((minimum_kdph * scoring_duration + 3599) // 3600)
            required_keystrokes = minimum_strokes
            speed_met = gross_wpm >= minimum_wpm
            stroke_floor_met = gross_strokes >= minimum_strokes
            required_keystrokes_met = stroke_floor_met
            error_cap_met = error_percent <= error_cap
            qualification = bool(speed_met and stroke_floor_met and error_cap_met)
            qualification_note = (
                f"{'QUALIFIED' if qualification else 'NOT QUALIFIED'} — CHSL Hindi: {gross_wpm:.2f} WPM / {gross_kdph:.0f} KDPH; "
                f"{error_percent:.2f}% weighted errors (maximum {error_cap:g}%); {gross_strokes}/{minimum_strokes} strokes."
            )
            score = None

        elif formula == "DELHI_POLICE_MODEL_D":
            # Rulebook Model D: speed-graded merit marks (0-25) with a 5% weighted
            # mistake cap. The supplied rulebook does not publish mark conversion
            # bands, so score remains unassigned until an administrator configures them.
            error_percent = round(error_count * 100 / max(1, len(re.findall(r"\S+", reference))), 2)
            net_wpm = gross_wpm
            bands = scoring_rules.get("score_bands") or []
            eligible_marks = []
            for band in bands:
                try:
                    threshold, marks = float(band[0]), float(band[1])
                except (TypeError, ValueError, IndexError):
                    continue
                if net_wpm >= threshold:
                    eligible_marks.append(marks)
            if eligible_marks:
                score = min(25.0, max(0.0, max(eligible_marks)))
            if error_percent > float(rules.get("error_allowance_percent") or 5):
                score = 0
            score_note = (
                "Marks pending: the master rulebook specifies 0-25 speed-graded marks but does not provide the official speed-to-marks bands."
                if not bands else "Speed-graded marks calculated from configured bands."
            )
            if error_percent > float(rules.get("error_allowance_percent") or 5):
                score_note = "Zero marks: weighted mistake percentage exceeds the configured 5% allowance."
        elif formula == "STROKE_NET_WPM":
            try:
                mistake_penalty_wpm = max(
                    0,
                    float(scoring_rules.get("mistake_penalty_wpm", 1)),
                )
            except (TypeError, ValueError):
                mistake_penalty_wpm = 1

            scoring_duration = scoring_rules.get("scoring_duration_seconds", duration)
            try:
                scoring_duration = max(1, int(scoring_duration))
            except (TypeError, ValueError):
                scoring_duration = duration
            scoring_minutes = scoring_duration / 60
            # HCM's notified formula uses a fixed 10-minute denominator.
            # For this internally verified profile, submitted text length is
            # the server-derived stroke count; browser telemetry is not trusted.
            tentative_wpm = round(
                stroke_count_for_speed / strokes_per_word / scoring_minutes,
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

            # HCM qualifying speed is a hard gate: below it means disqualified
            # and zero marks, not merely an ungraded score.
            try:
                qualifying_speed = float(rules.get("minimum_wpm"))
            except (TypeError, ValueError):
                qualifying_speed = None
            if qualifying_speed is not None and net_wpm < qualifying_speed:
                score = 0

        if not bands and score is None:
            qualification_note = (
                "Custom scoring data is stored, but no executable score formula is configured."
            )
    elif scoring_mode == "FULL_HALF_MISTAKES":
        qualification_note = "Full/half mistake classification requires exam-specific categories in scoring_rules; no generic classification was assumed."

    error_denominator = (
        len(re.findall(r"\S+", reference))
        if scoring_mode == "CUSTOM" and scoring_rules.get("formula") in {"MODEL_A", "MODEL_D", "DELHI_POLICE_MODEL_D", "SSC_CHSL_2025_VH_ENGLISH", "SSC_CHSL_2025_ENGLISH", "SSC_CHSL_2025_HINDI", "SSC_CHSL_2025_HINDI_KRUTIDEV", "SSC_CHSL_2025_HINDI_MANGAL", "SSC_DPA_GRADE_A"}
        else gross_words
    )
    error_percent_for_qualification = round(error_count * 100 / max(1, error_denominator), 2)
    if scoring_mode == "CUSTOM" and scoring_rules.get("formula") == "DELHI_POLICE_HCM_2025":
        qualification_status = "PROVISIONAL_QUALIFIED" if qualification else "PROVISIONAL_NOT_QUALIFIED"
    if scoring_mode == "CUSTOM" and scoring_rules.get("formula") == "SSC_DPA_GRADE_A":
        qualification_status = "PROVISIONAL_QUALIFIED" if qualification else "PROVISIONAL_NOT_QUALIFIED"
    elif scoring_mode == "CUSTOM" and scoring_rules.get("formula") == "SSC_CHSL_2025_ENGLISH":
        qualification_status = "PROVISIONAL_QUALIFIED" if qualification else "PROVISIONAL_NOT_QUALIFIED"
        qualification_note = (
            f"{'Meets' if qualification else 'Does not meet'} the configured CHSL 2025 English criteria: "
            f"{gross_wpm:.2f} WPM (minimum {minimum_wpm:g}), "
            f"{error_percent:.2f}% weighted errors (maximum {error_cap:g}%), "
            f"{gross_strokes}/{minimum_strokes} keystrokes."
        )
    qualification_metrics = {
        "net_wpm": net_wpm, "gross_wpm": gross_wpm,
        "accuracy_percent": accuracy, "error_percent": error_percent_for_qualification,
        "score": score, "correct_words": correct_words, "word_errors": word_errors,
        "keystrokes": stroke_count_for_speed,
        "gross_words": gross_words,
    }
    qualification_status = "PENDING"
    if scoring_mode == "CUSTOM" and scoring_rules.get("formula") == "SSC_DPA_GRADE_A":
        qualification_status = "PROVISIONAL_QUALIFIED" if qualification else "PROVISIONAL_NOT_QUALIFIED"
    elif scoring_mode == "CUSTOM" and scoring_rules.get("formula") == "SSC_CHSL_2025_ENGLISH":
        qualification_status = "PROVISIONAL_QUALIFIED" if qualification else "PROVISIONAL_NOT_QUALIFIED"
    configured_qualification = rules.get("qualification_rules") or {}
    qualification_uses_partial = bool(configured_qualification.get("allow_partial_verification")) if isinstance(configured_qualification, dict) else False
    can_evaluate_qualification = (
        rules.get("verification_status") == "VERIFIED"
        or (qualification_uses_partial and rules.get("verification_status") == "PARTIAL")
    )
    if can_evaluate_qualification and configured_qualification and scoring_rules.get("formula") != "SSC_DPA_GRADE_A":
        evaluated, qualification_note = _evaluate_qualification_rules(configured_qualification, qualification_metrics)
        qualification = evaluated
        if evaluated is not None:
            qualification_status = (
                ("PROVISIONAL_" if rules.get("verification_status") == "PARTIAL" else "")
                + ("QUALIFIED" if evaluated else "NOT_QUALIFIED")
            )
    elif (
        rules.get("verification_status") != "VERIFIED"
        and not (
            scoring_mode == "CUSTOM"
            and scoring_rules.get("formula") in {"SSC_CGL_2025_DEST", "SSC_CGL_2025_VH_DEST", "SSC_CHSL_2025_ENGLISH", "SSC_CHSL_2025_VH_ENGLISH", "SSC_CHSL_2025_HINDI", "SSC_CHSL_2025_HINDI_KRUTIDEV", "SSC_CHSL_2025_HINDI_MANGAL", "SSC_DPA_GRADE_A", "DELHI_POLICE_HCM_2025"}
        )
    ):
        qualification = None
        qualification_note = "Qualification is provisional/pending because the configured profile is not officially verified."
    elif qualification is not None:
        provisional_prefix = "PROVISIONAL_" if rules.get("verification_status") != "VERIFIED" else ""
        qualification_status = provisional_prefix + ("QUALIFIED" if qualification else "NOT_QUALIFIED")

    if scoring_mode == "CUSTOM" and scoring_rules.get("formula") == "DELHI_POLICE_HCM_2025" and qualification is not None:
        provisional_prefix = "PROVISIONAL_" if rules.get("verification_status") != "VERIFIED" else ""
        qualification_status = provisional_prefix + ("QUALIFIED" if qualification else "DISQUALIFIED")

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

    rulebook_evaluation = None
    if scoring_rules.get("rulebook_verification") == "internal":
        from .rulebook_evaluation import evaluate_rulebook_qualification

        rulebook_evaluation = evaluate_rulebook_qualification(
            configured_qualification,
            qualification_metrics,
            candidate_category=rules.get("candidate_category"),
            selectors=rules.get("candidate_selectors"),
        )
        # Internally approved rulebook profiles are evaluated only by the
        # versioned structured criteria. Legacy thresholds/formula branches
        # remain available for historical compatibility, but cannot decide
        # a new internal-rulebook attempt.
        qualification = rulebook_evaluation["qualification"]
        qualification_status = rulebook_evaluation["qualification_status"]
        qualification_note = rulebook_evaluation["qualification_note"]

    return {
        "scoring_version": SCORING_VERSION,
        "duration_seconds": duration,
        "typed_characters": len(typed),
        "reported_keystrokes": reported_keystrokes,
                "stroke_count_for_speed": stroke_count_for_speed,
        "gross_strokes": stroke_count_for_speed if scoring_mode == "CUSTOM" and scoring_rules.get("formula") in {"DELHI_POLICE_HCM_2025", "SSC_CGL_2025_DEST", "SSC_CGL_2025_VH_DEST", "SSC_CHSL_2025_ENGLISH", "SSC_CHSL_2025_VH_ENGLISH", "SSC_CHSL_2025_HINDI", "SSC_CHSL_2025_HINDI_KRUTIDEV", "SSC_CHSL_2025_HINDI_MANGAL"} else None,
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
        "score_note": score_note,
        "full_mistakes": full_mistakes,
        "half_mistakes": half_mistakes,
        "weighted_mistakes": error_count if scoring_mode == "CUSTOM" and scoring_rules.get("formula") in {"DELHI_POLICE_MODEL_D", "SSC_CGL_2025_DEST", "SSC_CGL_2025_VH_DEST", "SSC_CHSL_2025_VH_ENGLISH", "SSC_CHSL_2025_ENGLISH", "SSC_CHSL_2025_HINDI", "SSC_CHSL_2025_HINDI_KRUTIDEV", "SSC_CHSL_2025_HINDI_MANGAL", "SSC_DPA_GRADE_A"} else None,
        "error_percent": error_percent_for_qualification,
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
        "error_count_method": "one_word_deducted_per_mistake" if scoring_mode == "CUSTOM" and scoring_rules.get("formula") == "DELHI_POLICE_HCM_2025" else ("full_half_weighted" if scoring_mode == "CUSTOM" and scoring_rules.get("formula") == "SSC_DPA_GRADE_A" else ("word" if count_word_errors else "character")),
        "accuracy_percent": accuracy,
        "gross_wpm": gross_wpm,
        "gross_kdph": gross_kdph,
        "gross_kdph": gross_kdph if scoring_mode == "CUSTOM" and scoring_rules.get("formula") in {"SSC_CGL_2025_DEST", "SSC_CGL_2025_VH_DEST", "SSC_CHSL_2025_VH_ENGLISH", "SSC_CHSL_2025_ENGLISH", "SSC_CHSL_2025_HINDI", "SSC_CHSL_2025_HINDI_KRUTIDEV", "SSC_CHSL_2025_HINDI_MANGAL", "SSC_DPA_GRADE_A"} else None,
        "candidate_category": candidate_category if scoring_mode == "CUSTOM" and scoring_rules.get("formula") in {"SSC_CGL_2025_DEST", "SSC_CGL_2025_VH_DEST", "SSC_CHSL_2025_ENGLISH", "SSC_CHSL_2025_VH_ENGLISH", "SSC_CHSL_2025_HINDI", "SSC_CHSL_2025_HINDI_KRUTIDEV", "SSC_CHSL_2025_HINDI_MANGAL", "SSC_DPA_GRADE_A"} else None,
        "category_error_cap": error_cap if scoring_mode == "CUSTOM" and scoring_rules.get("formula") in {"SSC_CGL_2025_DEST", "SSC_CGL_2025_VH_DEST", "SSC_CHSL_2025_ENGLISH", "SSC_CHSL_2025_VH_ENGLISH", "SSC_CHSL_2025_HINDI", "SSC_CHSL_2025_HINDI_KRUTIDEV", "SSC_CHSL_2025_HINDI_MANGAL", "SSC_DPA_GRADE_A"} else None,
        "reference_word_count": reference_word_count if scoring_mode == "CUSTOM" and scoring_rules.get("formula") in {"SSC_CGL_2025_DEST", "SSC_CGL_2025_VH_DEST", "SSC_CHSL_2025_VH_ENGLISH", "SSC_CHSL_2025_ENGLISH"} else None,
        "speed_requirement_met": speed_met if scoring_mode == "CUSTOM" and scoring_rules.get("formula") in {"SSC_CHSL_2025_ENGLISH", "SSC_CHSL_2025_VH_ENGLISH", "SSC_CHSL_2025_HINDI", "SSC_CHSL_2025_HINDI_KRUTIDEV", "SSC_CHSL_2025_HINDI_MANGAL"} else None,
        "correct_wpm": correct_wpm,
        "net_wpm": net_wpm,
        "qualification": qualification,
        "qualification_status": qualification_status,
        "evaluation_status": rulebook_evaluation["evaluation_status"] if rulebook_evaluation else ("EVALUATED" if qualification is not None else "NOT_EVALUATED"),
        "qualification_checks": rulebook_evaluation["qualification_checks"] if rulebook_evaluation else [],

        "disqualified": qualification_status.endswith("NOT_QUALIFIED") or qualification_status.endswith("DISQUALIFIED"),
        "disqualification_reason": (
            f"Net speed below the minimum qualifying speed of {scoring_rules.get('minimum_wpm', rules.get('minimum_wpm'))} WPM."
            if (qualification_status.endswith("NOT_QUALIFIED") or qualification_status.endswith("DISQUALIFIED"))
            and (rules.get("minimum_wpm") is not None or scoring_rules.get("minimum_wpm") is not None)
            else None
        ),
        "qualification_note": (
            "Qualification is not calculated because exam rules are not verified."
            if rules.get("verification_status") != "VERIFIED" and qualification is None
            else qualification_note
        ),
    }
