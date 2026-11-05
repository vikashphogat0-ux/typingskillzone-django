"""Unified Delhi Police HCM 2025 practice report.

This report combines generic text metrics with the conservative HCM error
analyzer. It never promotes candidate detections to an official mistake
count, nor practice telemetry to an official SSC marks decision.
"""
from .dphcm_error_analysis import analyze_dphcm_text_errors


REPORT_VERSION = "dphcm-attempt-report-v1"
PROFILE_CODE = "delhi-police-hcm-2025-en"


def build_dphcm_attempt_report(*, reference, typed, practice_metrics, language):
    analysis = analyze_dphcm_text_errors(reference=reference, typed=typed)
    return {
        "report_version": REPORT_VERSION,
        "profile": "DELHI_POLICE_HCM_2025",
        "language": str(language or "").upper(),
        "practice_metrics": {
            "gross_wpm": practice_metrics.get("gross_wpm"),
            "correct_wpm": practice_metrics.get("correct_wpm"),
            "net_wpm": practice_metrics.get("net_wpm"),
            "accuracy_percent": practice_metrics.get("accuracy_percent"),
            "character_errors": practice_metrics.get("character_errors"),
            "word_errors": practice_metrics.get("word_errors"),
            "metric_status": "PRACTICE_ONLY",
        },
        "mistake_analysis": analysis,
        "marks_eligibility": {
            "status": "PENDING_VERIFIED_INPUTS",
            "marks": None,
            "official_mistake_count": None,
            "required_inputs": [
                "Verified total stroke count for the candidate's actual keyboard/input method",
                "Officially adjudicated mistake count under the SSC error instructions",
            ],
            "reason": (
                "Text-based candidate categories are not an official mistake count, "
                "and the current stroke telemetry is not independently verified."
            ),
        },
        "official_result_claimed": False,
    }
