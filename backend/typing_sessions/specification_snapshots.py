"""Immutable-at-session-start exam specification snapshot construction.

The legacy top-level keys are intentionally retained because the current
scoring engine consumes them. The canonical resolver output is additive.
"""
from exams.specifications import resolve_exam_specification


SESSION_SNAPSHOT_FORMAT_VERSION = 1


def build_exam_specification_snapshot(*, exam, publication, captured_at):
    """Build the persisted rules snapshot without changing scoring semantics."""
    snapshot = {
        "exam_code": exam.code,
        "exam_name": exam.name,
        "passage_id": publication.passage_id,
        "language": exam.language,
        "script": exam.script,
        "allow_backspace": exam.allow_backspace,
        "backspace_policy": exam.backspace_policy,
        "allow_delete": exam.allow_delete,
        "allow_arrow_navigation": exam.allow_arrow_navigation,
        "allow_paste": exam.allow_paste,
        "allow_copy": exam.allow_copy,
        "allow_cut": exam.allow_cut,
        "enter_behavior": exam.enter_behavior,
        "space_behavior": exam.space_behavior,
        "tab_behavior": exam.tab_behavior,
        "keyboard_layout": exam.keyboard_layout,
        "text_encoding": exam.text_encoding,
        "passage_source_mode": exam.passage_source_mode,
        "minimum_wpm": str(exam.minimum_wpm) if exam.minimum_wpm is not None else None,
        "required_keystrokes": exam.required_keystrokes,
        "strokes_per_word": exam.strokes_per_word,
        "error_allowance_percent": str(exam.error_allowance_percent) if exam.error_allowance_percent is not None else None,
        "mistake_penalty_strokes": exam.mistake_penalty_strokes,
        "trial_seconds": exam.trial_seconds,
        "review_seconds": exam.review_seconds,
        "correction_seconds": exam.correction_seconds,
        "transcription_seconds": exam.transcription_seconds,
        "allow_passage_repeat": exam.allow_passage_repeat,
        "scoring_mode": exam.scoring_mode,
        "rule_config_version": exam.rule_config_version,
        "verification_status": exam.verification_status,
        "official_source_url": exam.official_source_url,
        "error_rules": exam.error_rules,
        "scoring_rules": exam.scoring_rules,
        "qualification_rules": exam.qualification_rules,
        "passage_layout": exam.passage_layout,
        "passage_format": exam.passage_format,
        "passage_font_family": exam.passage_font_family,
        "passage_font_size_pt": exam.passage_font_size_pt,
        "passage_line_height": str(exam.passage_line_height),
        "passage_alignment": exam.passage_alignment,
        "passage_preserve_tabs": exam.passage_preserve_tabs,
        "passage_tab_size": exam.passage_tab_size,
        "snapshot_metadata": {
            "format_version": SESSION_SNAPSHOT_FORMAT_VERSION,
            "captured_at": captured_at.isoformat(),
            "publication_id": str(publication.pk),
            "passage_source_id": str(publication.source_id),
        },
        "canonical_specification": resolve_exam_specification(exam),
    }
    return snapshot
