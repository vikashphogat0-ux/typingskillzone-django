"""Delhi Police Head Constable (Ministerial) Examination 2025 rule reference.

Source: SSC Notice, Notice_of_DPHCM_2025.pdf, paragraphs 24.1 and 24.2,
printed pages 22-23 (PDF page numbering). This module is a pure evaluator;
it does not infer keystrokes from Unicode text or mutate exam profiles.
"""

PROFILE_ID = "DELHI_POLICE_HCM_2025"
SOURCE_URL = "https://ssc.gov.in/api/attachment/uploads/masterData/NoticeBoards/Notice_of_DPHCM_2025.pdf?mode=light"
SOURCE_TITLE = "SSC Notice: Head Constable (Ministerial) in Delhi Police Examination, 2025"
SOURCE_CHECKED_AT = "2026-11-05"

OFFICIAL_RULES = {
    "duration_seconds": 600,
    "maximum_marks": 25,
    "minimum_speed_wpm": {"ENGLISH": 30, "HINDI": 25},
    "minimum_printed_passage": {
        "ENGLISH": {"words": 400, "strokes": 2000},
        "HINDI": {"words": 350, "strokes": 1750},
    },
    "speed_formula": {
        "tentative_speed": "total_strokes / 5 / (duration_seconds / 60)",
        "actual_speed": "tentative_speed - one_word_per_mistake",
        "mistake_penalty_wpm": 1,
        "stroke_count_source": "MUST_BE_MEASURED_OR_SUPPLIED_BY_A_VERIFIED_STROKE_COUNTER",
    },
    "mistake_taxonomy": [
        "omission",
        "substitution",
        "addition_of_punctuation_marks",
        "capital_letter_instead_of_small_letter_or_vice_versa",
        "gap_inside_a_word",
        "excess_gap_between_two_words",
        "missing_paragraph",
    ],
    "marks_bands": {
        "ENGLISH": [
            {"minimum_wpm": 30, "maximum_wpm": 30, "marks": 10},
            {"minimum_wpm": 31, "maximum_wpm": 35, "marks": 12},
            {"minimum_wpm": 36, "maximum_wpm": 40, "marks": 15},
            {"minimum_wpm": 41, "maximum_wpm": 45, "marks": 18},
            {"minimum_wpm": 46, "maximum_wpm": 50, "marks": 21},
            {"minimum_wpm_exclusive": 50, "marks": 25},
        ],
        "HINDI": [
            {"minimum_wpm": 25, "maximum_wpm": 25, "marks": 10},
            {"minimum_wpm": 26, "maximum_wpm": 30, "marks": 12},
            {"minimum_wpm": 31, "maximum_wpm": 35, "marks": 15},
            {"minimum_wpm": 36, "maximum_wpm": 40, "marks": 18},
            {"minimum_wpm": 41, "maximum_wpm": 45, "marks": 21},
            {"minimum_wpm_exclusive": 45, "marks": 25},
        ],
    },
    "input_restrictions": {
        "backspace": "NOT_SPECIFIED",
        "delete": "NOT_SPECIFIED",
        "paste": "NOT_SPECIFIED",
        "copy": "NOT_SPECIFIED",
        "cut": "NOT_SPECIFIED",
        "arrow_navigation": "NOT_SPECIFIED",
    },
    "provenance": {
        "status": "PARTIAL",
        "references": [{
            "url": SOURCE_URL,
            "title": SOURCE_TITLE,
            "locator": "Paragraphs 24.1-24.2, printed pages 22-23",
            "checked_at": SOURCE_CHECKED_AT,
            "claims": [
                "timing.duration_seconds",
                "scoring.minimum_speed_wpm",
                "passage.minimum_printed_passage",
                "scoring.speed_formula",
                "scoring.mistake_taxonomy",
                "scoring.marks_bands",
            ],
        }],
        "unresolved": [
            "The notice does not state how fractional actual speeds between listed integer bands are rounded or scored.",
            "The notice does not define a machine-verifiable keystroke counting method for Hindi Unicode text.",
            "Backspace, Delete, paste, copy, cut and arrow-key restrictions are not specified in paragraphs 24.1-24.2.",
        ],
    },
}


def evaluate_dphcm_2025(*, language, total_strokes, mistake_count, duration_seconds=600):
    """Evaluate only supplied stroke/mistake counts; never infer them from text."""
    language = str(language or "").upper()
    if language not in OFFICIAL_RULES["minimum_speed_wpm"]:
        return {"status": "UNSUPPORTED_LANGUAGE", "score": None, "actual_speed_wpm": None}
    if isinstance(total_strokes, bool) or not isinstance(total_strokes, int) or total_strokes < 0:
        return {"status": "INVALID_STROKE_COUNT", "score": None, "actual_speed_wpm": None}
    if isinstance(mistake_count, bool) or not isinstance(mistake_count, int) or mistake_count < 0:
        return {"status": "INVALID_MISTAKE_COUNT", "score": None, "actual_speed_wpm": None}
    if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int) or duration_seconds != 600:
        return {"status": "UNSUPPORTED_DURATION", "score": None, "actual_speed_wpm": None}

    tentative_speed = total_strokes / 5 / 10
    actual_speed = tentative_speed - mistake_count
    minimum = OFFICIAL_RULES["minimum_speed_wpm"][language]
    if actual_speed < minimum:
        return {
            "status": "DISQUALIFIED",
            "tentative_speed_wpm": tentative_speed,
            "actual_speed_wpm": actual_speed,
            "minimum_speed_wpm": minimum,
            "score": 0,
            "score_unit": "marks",
            "reason": "Actual speed is below the language-specific minimum qualifying speed.",
        }

    if not float(actual_speed).is_integer():
        return {
            "status": "BAND_UNRESOLVED",
            "tentative_speed_wpm": tentative_speed,
            "actual_speed_wpm": actual_speed,
            "minimum_speed_wpm": minimum,
            "score": None,
            "score_unit": "marks",
            "reason": "The notice lists integer speed bands but does not specify rounding for fractional actual speed.",
        }

    integer_speed = int(actual_speed)
    for band in OFFICIAL_RULES["marks_bands"][language]:
        if "maximum_wpm" in band and band["minimum_wpm"] <= integer_speed <= band["maximum_wpm"]:
            marks = band["marks"]
            break
        if "minimum_wpm_exclusive" in band and integer_speed > band["minimum_wpm_exclusive"]:
            marks = band["marks"]
            break
    else:
        return {
            "status": "BAND_UNRESOLVED",
            "tentative_speed_wpm": tentative_speed,
            "actual_speed_wpm": actual_speed,
            "minimum_speed_wpm": minimum,
            "score": None,
            "score_unit": "marks",
            "reason": "No published marks band matches the supplied actual speed.",
        }

    return {
        "status": "SCORED",
        "tentative_speed_wpm": tentative_speed,
        "actual_speed_wpm": actual_speed,
        "minimum_speed_wpm": minimum,
        "score": marks,
        "score_unit": "marks",
        "reason": "Score matched an explicit integer speed band in SSC Notice paragraph 24.1.",
    }
