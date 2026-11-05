"""Pure compatibility resolver for legacy ExamConfiguration records.

The resolver is deliberately read-only: it performs no database access,
validation side effects, writes, or rule inference. Ambiguous legacy fields
are retained with an explicit unresolved interpretation.
"""

SPECIFICATION_SCHEMA_VERSION = 1


def _value(instance, field):
    value = getattr(instance, field, None)
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "as_tuple"):  # Decimal
        return str(value)
    return value


def resolve_exam_specification(exam):
    """Return a JSON-serializable canonical view of a legacy exam profile.

    This is a compatibility projection, not an official-rule verifier.
    Existing profile values are preserved; no defaults are invented beyond
    the values already present on the model instance.
    """
    identity = {
        "code": _value(exam, "code"),
        "name": _value(exam, "name"),
        "category": _value(exam, "category"),
        "language": _value(exam, "language"),
        "script": _value(exam, "script"),
        "interface_type": _value(exam, "interface_type"),
    }

    timing = {
        "duration_seconds": _value(exam, "duration_seconds"),
        "trial_seconds": _value(exam, "trial_seconds"),
        "review_seconds": _value(exam, "review_seconds"),
        "correction_seconds": _value(exam, "correction_seconds"),
        "transcription_seconds": _value(exam, "transcription_seconds"),
    }

    passage = {
        "format": _value(exam, "passage_format"),
        "layout": _value(exam, "passage_layout"),
        "source_mode": _value(exam, "passage_source_mode"),
        "quantity": {
            "legacy_word_limit": _value(exam, "passage_word_limit"),
            "unit": "words" if _value(exam, "passage_word_limit") is not None else None,
            "constraint": "UNSPECIFIED",
        },
        "typography": {
            "font_family": _value(exam, "passage_font_family"),
            "font_size_pt": _value(exam, "passage_font_size_pt"),
            "line_height": _value(exam, "passage_line_height"),
            "paragraph_spacing_pt": _value(exam, "passage_paragraph_spacing_pt"),
            "alignment": _value(exam, "passage_alignment"),
            "first_line_indent_em": _value(exam, "passage_first_line_indent_em"),
            "preserve_tabs": _value(exam, "passage_preserve_tabs"),
            "tab_size": _value(exam, "passage_tab_size"),
        },
        "allow_repeat": _value(exam, "allow_passage_repeat"),
    }

    input_policy = {
        "backspace": {
            "legacy_allowed": _value(exam, "allow_backspace"),
            "policy": _value(exam, "backspace_policy"),
            "resolution": "LEGACY_FIELDS_PRESERVED",
        },
        "delete": _value(exam, "allow_delete"),
        "paste": _value(exam, "allow_paste"),
        "copy": _value(exam, "allow_copy"),
        "cut": _value(exam, "allow_cut"),
        "arrow_navigation": _value(exam, "allow_arrow_navigation"),
        "enter_behavior": _value(exam, "enter_behavior"),
        "space_behavior": _value(exam, "space_behavior"),
        "tab_behavior": _value(exam, "tab_behavior"),
        "keyboard_layout": _value(exam, "keyboard_layout"),
        "text_encoding": _value(exam, "text_encoding"),
    }

    scoring = {
        "legacy_mode": _value(exam, "scoring_mode"),
        "minimum_wpm": _value(exam, "minimum_wpm"),
        "required_keystrokes": _value(exam, "required_keystrokes"),
        "strokes_per_word": _value(exam, "strokes_per_word"),
        "error_allowance_percent": _value(exam, "error_allowance_percent"),
        "mistake_penalty_strokes": _value(exam, "mistake_penalty_strokes"),
        "error_rules": _value(exam, "error_rules") or {},
        "scoring_rules": _value(exam, "scoring_rules") or {},
        "qualification_rules": _value(exam, "qualification_rules") or {},
    }

    provenance = {
        "verification_status": _value(exam, "verification_status"),
        "official_source_url": _value(exam, "official_source_url"),
        "source_title": _value(exam, "source_title"),
        "source_checked_at": _value(exam, "source_checked_at"),
        "rule_notes": _value(exam, "rule_notes"),
        "presentation_reference": {
            "status": _value(exam, "presentation_reference_status"),
            "url": _value(exam, "presentation_reference_url"),
            "title": _value(exam, "presentation_reference_title"),
            "checked_at": _value(exam, "presentation_reference_checked_at"),
            "notes": _value(exam, "presentation_notes"),
        },
    }

    return {
        "specification_schema_version": SPECIFICATION_SCHEMA_VERSION,
        "source": {
            "model": "exams.ExamConfiguration",
            "legacy_rule_config_version": _value(exam, "rule_config_version"),
        },
        "identity": identity,
        "timing": timing,
        "passage": passage,
        "input_policy": input_policy,
        "scoring": scoring,
        "provenance": provenance,
        "catalogue": {
            "is_active": _value(exam, "is_active"),
            "display_order": _value(exam, "display_order"),
        },
    }
