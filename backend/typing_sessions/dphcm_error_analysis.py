"""Conservative text-difference analysis for Delhi Police HCM 2025.

SSC Notice 2025 paragraph 24.2 names mistake types but does not provide a
complete machine-readable decision procedure for every overlap. This module
therefore reports observable candidates and marks ambiguous cases unresolved.
It does not claim to reproduce the examiner's official adjudication.
"""
from difflib import SequenceMatcher
import re


DPHCM_ERROR_ANALYZER_VERSION = "dphcm-text-audit-v1"
DPHCM_ERROR_CATEGORIES = (
    "OMISSION",
    "SUBSTITUTION",
    "ADDITION_OF_PUNCTUATION",
    "CAPITALIZATION",
    "GAP_INSIDE_WORD",
    "EXCESS_GAP_BETWEEN_WORDS",
    "MISSING_PARAGRAPH",
)


def analyze_dphcm_text_errors(*, reference, typed):
    """Return conservative candidate error cases without inventing a total.

    Exact matching words are ignored. A single reference/typed token pair can
    be categorized only when a narrow rule is unambiguous. Multi-token
    replacements, insertions/deletions, whitespace and paragraph differences
    are reported separately. The result is practice analysis, not official
    mistake adjudication or a certified mistake count.
    """
    if not isinstance(reference, str) or not isinstance(typed, str):
        return _unresolved("INVALID_TEXT", "Reference and typed values must be strings.")

    if len(reference) > 100000 or len(typed) > 100000:
        return _unresolved("TEXT_LIMIT_EXCEEDED", "Text exceeds the analysis limit.")

    if reference == typed:
        return {
            "status": "ANALYZED",
            "analyzer_version": DPHCM_ERROR_ANALYZER_VERSION,
            "candidate_errors": [],
            "unresolved_cases": [],
            "candidate_error_count": 0,
            "official_mistake_count": None,
            "official_scoring_eligible": False,
        }

    candidates = []
    unresolved = []

    # Paragraph boundaries are meaningful under the notice's explicit
    # "not making paragraph(s)" category. We do not infer where an omitted
    # paragraph ought to be when the source has no paragraph markers.
    ref_paragraphs = reference.splitlines()
    typed_paragraphs = typed.splitlines()
    if len(ref_paragraphs) != len(typed_paragraphs):
        matcher = SequenceMatcher(a=ref_paragraphs, b=typed_paragraphs, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            if tag == "delete":
                candidates.append({
                    "category": "MISSING_PARAGRAPH",
                    "reference": ref_paragraphs[i1:i2],
                    "typed": [],
                    "basis": "One or more reference paragraph lines are absent.",
                })
            elif tag == "insert":
                unresolved.append({
                    "reference": ref_paragraphs[i1:i2],
                    "typed": typed_paragraphs[j1:j2],
                    "reason": "Additional paragraph/line: the notice does not specify its mistake treatment.",
                })
            else:
                unresolved.append({
                    "reference": ref_paragraphs[i1:i2],
                    "typed": typed_paragraphs[j1:j2],
                    "reason": "Paragraph boundary replacement cannot be safely decomposed into word mistakes.",
                })

    # Detect exact whitespace variants before normalizing words.
    ref_words = re.findall(r"\S+", reference)
    typed_words = re.findall(r"\S+", typed)
    if ref_words == typed_words and reference != typed:
        if re.search(r"\S\s{2,}\S", typed):
            candidates.append({
                "category": "EXCESS_GAP_BETWEEN_WORDS",
                "reference": reference,
                "typed": typed,
                "basis": "Typed text contains multiple whitespace characters between non-space text.",
            })
        elif re.search(r"\S\s+\S", reference) and not re.search(r"\S\s{2,}\S", typed):
            unresolved.append({
                "reference": reference,
                "typed": typed,
                "reason": "Whitespace differs, but the notice does not define exact spacing thresholds.",
            })
        else:
            unresolved.append({
                "reference": reference,
                "typed": typed,
                "reason": "Whitespace-only difference requires examiner-specific interpretation.",
            })

    matcher = SequenceMatcher(a=ref_words, b=typed_words, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        ref_segment = ref_words[i1:i2]
        typed_segment = typed_words[j1:j2]

        if tag == "delete":
            candidates.extend({
                "category": "OMISSION",
                "reference": word,
                "typed": "",
                "basis": "Reference token has no aligned typed token.",
            } for word in ref_segment)
            continue

        if tag == "insert":
            unresolved.append({
                "reference": [],
                "typed": typed_segment,
                "reason": "Added word/token: paragraph 24.2 does not explicitly define an added-word category.",
            })
            continue

        if len(ref_segment) == len(typed_segment) == 1:
            original, entered = ref_segment[0], typed_segment[0]
            if original.casefold() == entered.casefold() and original != entered:
                candidates.append({
                    "category": "CAPITALIZATION",
                    "reference": original,
                    "typed": entered,
                    "basis": "Only letter case differs.",
                })
            elif _punctuation_only_difference(original, entered):
                candidates.append({
                    "category": "ADDITION_OF_PUNCTUATION",
                    "reference": original,
                    "typed": entered,
                    "basis": "Difference is limited to punctuation characters.",
                })
            elif _single_internal_gap_difference(original, entered):
                candidates.append({
                    "category": "GAP_INSIDE_WORD",
                    "reference": original,
                    "typed": entered,
                    "basis": "One token is split by an internal whitespace gap.",
                })
            elif original != entered:
                candidates.append({
                    "category": "SUBSTITUTION",
                    "reference": original,
                    "typed": entered,
                    "basis": "One reference token is replaced by one different typed token.",
                })
            continue

        unresolved.append({
            "reference": ref_segment,
            "typed": typed_segment,
            "reason": "Multi-token replacement is ambiguous; no official alignment/weighting rule is specified here.",
        })

    # Avoid pretending candidate categories constitute the official total.
    return {
        "status": "ANALYZED_WITH_UNRESOLVED_CASES" if unresolved else "ANALYZED",
        "analyzer_version": DPHCM_ERROR_ANALYZER_VERSION,
        "candidate_errors": candidates,
        "unresolved_cases": unresolved,
        "candidate_error_count": len(candidates),
        "official_mistake_count": None,
        "official_scoring_eligible": False,
        "notice_categories": list(DPHCM_ERROR_CATEGORIES),
        "reason": "Candidates are explanatory text comparisons only; official mistake adjudication remains unverified.",
    }


def _punctuation_only_difference(reference, typed):
    strip = lambda value: re.sub(r"[^\w\s]", "", value, flags=re.UNICODE)
    return reference != typed and strip(reference) == strip(typed)


def _single_internal_gap_difference(reference, typed):
    compact_ref = re.sub(r"\s+", "", reference)
    compact_typed = re.sub(r"\s+", "", typed)
    return (
        compact_ref == compact_typed
        and bool(re.search(r"\s", typed))
        and not bool(re.search(r"\s", reference))
    )


def _unresolved(status, reason):
    return {
        "status": status,
        "analyzer_version": DPHCM_ERROR_ANALYZER_VERSION,
        "candidate_errors": [],
        "unresolved_cases": [],
        "candidate_error_count": None,
        "official_mistake_count": None,
        "official_scoring_eligible": False,
        "reason": reason,
    }
