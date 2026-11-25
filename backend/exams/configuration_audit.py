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
    scoring = exam.scoring_rules or {}
    formula_config = scoring.get("rulebook_scoring") or {}
    formula_id = formula_config.get("formula")
    supported_formulas = {
        "GROSS_WPM_CHARACTERS_5", "GROSS_WPM_STROKES_5",
        "CORRECT_WORDS_PER_MINUTE", "NET_WPM_WEIGHTED_MISTAKES",
        "NET_WPM_CORRECT_WORDS", "NET_WPM_FORGIVENESS_EXCESS_PENALTY",
        "AIIMS_STROKE_DEDUCTION", "KDPH", "ERROR_PERCENT_WEIGHTED",
        "MARKS_PER_CORRECT_WORD", "SPEED_BANDS",
        "UPSSSC_FIVE_EXEMPT_SIXFOLD", "SPMCIL_STROKE_ERROR_WORDS",
        "MP_CPCT_NET_WPM_SLABS", "MPHC_MARKS_BACKSPACE_DEDUCTION",
    }
    parameters = formula_config.get("parameters") or {}
    formula_errors = []
    if formula_config:
        if formula_config.get("engine_version") != 1:
            formula_errors.append("Versioned scoring engine version is missing or unsupported.")
        if formula_id not in supported_formulas:
            formula_errors.append("Scoring formula ID is not supported by the versioned engine.")
        required_parameters = {
            "NET_WPM_WEIGHTED_MISTAKES": ("mistake_penalty_words",),
            "NET_WPM_FORGIVENESS_EXCESS_PENALTY": ("forgiveness_rate", "excess_mistake_penalty_words"),
            "AIIMS_STROKE_DEDUCTION": ("minimum_strokes", "penalty_strokes_per_mistake"),
            "ERROR_PERCENT_WEIGHTED": ("denominator",),
            "MARKS_PER_CORRECT_WORD": ("marks_per_correct_word",),
            "UPSSSC_FIVE_EXEMPT_SIXFOLD": ("exempt_wrong_words", "penalty_multiplier"),
            "SPMCIL_STROKE_ERROR_WORDS": ("strokes_per_word",),
            "MP_CPCT_NET_WPM_SLABS": ("words_per_error", "bands"),
            "MPHC_MARKS_BACKSPACE_DEDUCTION": ("maximum_marks", "wrong_word_deduction", "backspace_deduction"),
            "SPEED_BANDS": ("bands",),
        }.get(formula_id, ())
        for parameter in required_parameters:
            if parameter not in parameters or parameters.get(parameter) is None:
                formula_errors.append(f"Scoring formula parameter '{parameter}' is missing.")
    elif scoring.get("rulebook_verification") == "internal":
        formula_errors.append("Internal rulebook profile has no versioned scoring formula configuration.")
    errors.extend(formula_errors)

    qualification = exam.qualification_rules or {}
    qualification_errors = []
    if scoring.get("rulebook_verification") == "internal":
        if qualification.get("engine_version") != 1 or not isinstance(qualification.get("criteria"), list) or not qualification.get("criteria"):
            qualification_errors.append("Versioned qualification criteria are not configured.")
        else:
            for index, criterion in enumerate(qualification["criteria"], start=1):
                if not isinstance(criterion, dict) or criterion.get("metric") not in {
                    "net_wpm", "gross_wpm", "correct_wpm", "accuracy_percent",
                    "error_percent", "score", "correct_words", "word_errors",
                    "keystrokes", "gross_words", "gross_kdph", "weighted_mistakes",
                }:
                    qualification_errors.append(f"Qualification criterion {index} has an unsupported metric.")
                elif criterion.get("operator") not in {"gte", "gt", "lte", "lt", "eq"}:
                    qualification_errors.append(f"Qualification criterion {index} has an unsupported operator.")
                elif criterion.get("value") is None and not isinstance(criterion.get("category_values"), dict):
                    qualification_errors.append(f"Qualification criterion {index} has no explicit threshold.")
                elif isinstance(criterion.get("category_values"), dict) and not (
                    (scoring.get("profile_configuration") or {}).get("category_selector")
                ):
                    qualification_errors.append(
                        f"Qualification criterion {index} needs a server-validated candidate-category selector."
                    )
    errors.extend(qualification_errors)

    launch_checks = {
        "duration": bool(exam.duration_seconds),
        "passage_source": exam.passage_source_mode != ExamConfiguration.PassageSourceMode.UNSPECIFIED,
        "passage_layout": exam.passage_layout != ExamConfiguration.PassageLayout.UNCONFIGURED,
        "keyboard": bool(exam.keyboard_layout) or exam.language.upper() == "ENGLISH",
        "backspace_policy": exam.backspace_policy != ExamConfiguration.BackspacePolicy.NOT_SPECIFIED,
        "key_behaviors": all(value != ExamConfiguration.EnterBehavior.UNSPECIFIED for value in [exam.enter_behavior])
            and exam.space_behavior != ExamConfiguration.SpaceBehavior.UNSPECIFIED
            and exam.tab_behavior != ExamConfiguration.TabBehavior.UNSPECIFIED,
    }
    scoring_checks = {
        "versioned_formula": bool(formula_config and formula_id in supported_formulas and not formula_errors),
        "qualification_criteria": bool(qualification.get("engine_version") == 1 and qualification.get("criteria") and not qualification_errors),
    }
    stage_checks = {
        "launch": {"status": "READY" if all(launch_checks.values()) else "BLOCKED", "checks": launch_checks},
        "capture": {"status": "READY" if exam.duration_seconds and exam.passage_source_mode != ExamConfiguration.PassageSourceMode.UNSPECIFIED else "BLOCKED",
                    "checks": {"duration_snapshot": bool(exam.duration_seconds), "reference_passage_source": exam.passage_source_mode != ExamConfiguration.PassageSourceMode.UNSPECIFIED}},
        "scoring": {"status": "READY" if scoring_checks["versioned_formula"] else "BLOCKED", "checks": scoring_checks},
        "qualification": {"status": "READY" if scoring_checks["qualification_criteria"] else "BLOCKED", "checks": {"structured_criteria": scoring_checks["qualification_criteria"]}},
        "result": {"status": "READY" if scoring_checks["versioned_formula"] and scoring_checks["qualification_criteria"] else "BLOCKED",
                   "checks": {"formula_metrics_available": scoring_checks["versioned_formula"], "qualification_decision_available": scoring_checks["qualification_criteria"]}},
    }
    pipeline_ready = all(stage["status"] == "READY" for stage in stage_checks.values())
    if not pipeline_ready:
        errors.append("End-to-end exam pipeline is incomplete; one or more launch-to-result stages are blocked.")
    return {
        "status": "READY" if not errors else "DRAFT_INCOMPLETE",
        "ready": not errors,
        "errors": errors,
        "warnings": warnings,
        "stage_checks": stage_checks,
        "profile": {
            "code": exam.code,
            "name": exam.name,
            "rule_config_version": exam.rule_config_version,
            "formula_id": formula_id,
            "formula_engine_version": formula_config.get("engine_version"),
        },
    }
