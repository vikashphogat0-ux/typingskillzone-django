"""Audit legacy ExamConfiguration rows against exam-specific readiness rules.

This adapter is read-only and intentionally does not rewrite legacy records.
"""
from .models import ExamConfiguration


def audit_exam_configuration(exam):
    errors = []
    warnings = []
    if not exam.duration_seconds:
        errors.append("Test duration is not configured.")
    if exam.passage_layout == ExamConfiguration.PassageLayout.UNCONFIGURED:
        errors.append("Passage layout is not configured.")
    if exam.passage_source_mode == ExamConfiguration.PassageSourceMode.UNSPECIFIED:
        errors.append("Passage source mode is not configured.")
    if exam.backspace_policy == ExamConfiguration.BackspacePolicy.NOT_SPECIFIED:
        errors.append("Backspace policy is not specified.")
    if exam.enter_behavior == ExamConfiguration.EnterBehavior.UNSPECIFIED:
        errors.append("Enter-key behavior is not specified.")
    if exam.space_behavior == ExamConfiguration.SpaceBehavior.UNSPECIFIED:
        errors.append("Space-key behavior is not specified.")
    if exam.tab_behavior == ExamConfiguration.TabBehavior.UNSPECIFIED:
        errors.append("Tab-key behavior is not specified.")
    if not exam.keyboard_layout and exam.language.upper() not in ("ENGLISH",):
        errors.append("Keyboard layout is not configured for this language profile.")
    if exam.scoring_mode == ExamConfiguration.ScoringMode.GENERIC:
        errors.append("A generic scoring mode is selected; exam-specific scoring is not configured.")
    if not exam.scoring_rules:
        errors.append("Scoring formula/rules are not configured.")
    if not exam.error_rules:
        errors.append("Error classification rules are not configured.")
    if not exam.qualification_rules:
        errors.append("Qualification criteria are not configured.")
    if exam.verification_status != ExamConfiguration.Verification.VERIFIED:
        warnings.append("Rule profile is not verified against the controlling source.")
    if exam.presentation_reference_status == ExamConfiguration.PresentationReferenceStatus.PENDING:
        warnings.append("Typing interface/passage presentation reference has not been reviewed.")
    if exam.allow_backspace != (exam.backspace_policy != ExamConfiguration.BackspacePolicy.DISABLED):
        errors.append("Legacy allow_backspace flag conflicts with the selected backspace policy.")
    if exam.scoring_mode == ExamConfiguration.ScoringMode.ERROR_PERCENTAGE:
        if "error_denominator" not in exam.scoring_rules:
            errors.append("Error-percentage scoring requires an explicit denominator.")
    if exam.scoring_mode == ExamConfiguration.ScoringMode.STROKE_PENALTY:
        if not exam.mistake_penalty_strokes and "penalty_strokes_per_mistake" not in exam.scoring_rules:
            errors.append("Stroke-penalty scoring requires a penalty value.")
    if exam.scoring_mode == ExamConfiguration.ScoringMode.FULL_HALF_MISTAKES:
        classes = exam.error_rules.get("classes", {})
        if not {"full", "half"}.issubset(classes):
            errors.append("Full/half scoring requires explicit full and half error classes.")
    return {
        "status": "READY" if not errors else "DRAFT_INCOMPLETE",
        "ready": not errors,
        "errors": errors,
        "warnings": warnings,
        "profile": {
            "code": exam.code,
            "name": exam.name,
            "rule_config_version": exam.rule_config_version,
        },
    }
