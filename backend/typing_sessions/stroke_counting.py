"""Stroke-event counting contract for typing practice.

A stroke is counted from an explicit physical key event, not reconstructed
from final Unicode text. Browser event telemetry is client supplied and is
therefore UNVERIFIED; this module must not be used to certify official marks.
IME composition commits cannot be translated into physical strokes after the
fact and are reported as unresolved.
"""

STROKE_COUNTER_VERSION = "tsz-key-event-v1"
SUPPORTED_LANGUAGES = {"ENGLISH", "HINDI"}
_MODIFIER_CODES = {
    "ShiftLeft", "ShiftRight", "ControlLeft", "ControlRight",
    "AltLeft", "AltRight", "MetaLeft", "MetaRight",
}
_ALLOWED_EVENT_TYPES = {"KEY_DOWN", "COMPOSITION_COMMIT"}


def count_stroke_events(*, events, language, keyboard_layout):
    """Count captured physical key-downs without guessing from submitted text.

    Each KEY_DOWN represents one physical key press. Modifier-only keys and
    auto-repeat events are excluded. A COMPOSITION_COMMIT is not countable:
    its physical key sequence is unavailable in that event record.

    Returned counts are always labelled client telemetry, never verified
    official stroke counts.
    """
    language = str(language or "").upper()
    if language not in SUPPORTED_LANGUAGES:
        return _unresolved("UNSUPPORTED_LANGUAGE", "Language is not supported.")

    if not isinstance(keyboard_layout, str) or not keyboard_layout.strip():
        return _unresolved("LAYOUT_REQUIRED", "An explicit keyboard layout is required.")

    if not isinstance(events, list):
        return _unresolved("INVALID_EVENT_LIST", "Events must be a list.")

    if len(events) > 1000000:
        return _unresolved("EVENT_LIMIT_EXCEEDED", "Event list exceeds the safety limit.")

    counted = 0
    excluded_modifiers = 0
    excluded_repeats = 0
    unresolved_compositions = 0
    errors = []

    for index, event in enumerate(events):
        if not isinstance(event, dict):
            errors.append({"index": index, "reason": "Event must be an object."})
            continue

        event_type = event.get("type")
        if event_type not in _ALLOWED_EVENT_TYPES:
            errors.append({"index": index, "reason": "Unsupported event type."})
            continue

        if event_type == "COMPOSITION_COMMIT":
            unresolved_compositions += 1
            continue

        code = event.get("code")
        if not isinstance(code, str) or not code:
            errors.append({"index": index, "reason": "KEY_DOWN requires a physical key code."})
            continue

        if event.get("repeat") is True:
            excluded_repeats += 1
            continue

        if code in _MODIFIER_CODES:
            excluded_modifiers += 1
            continue

        # KEY_DOWN events represent one physical press, including punctuation,
        # digits, Space and Enter. This is a telemetry convention, not an SSC
        # ruling about which keys count as a stroke.
        counted += 1

    if errors:
        return {
            "status": "INVALID_EVENT_STREAM",
            "counter_version": STROKE_COUNTER_VERSION,
            "language": language,
            "keyboard_layout": keyboard_layout,
            "counted_strokes": None,
            "unresolved_composition_events": unresolved_compositions,
            "errors": errors,
            "trust": "UNVERIFIED_CLIENT_TELEMETRY",
            "official_scoring_eligible": False,
        }

    if unresolved_compositions:
        return {
            "status": "INCOMPLETE",
            "counter_version": STROKE_COUNTER_VERSION,
            "language": language,
            "keyboard_layout": keyboard_layout,
            "counted_strokes": counted,
            "excluded_modifier_events": excluded_modifiers,
            "excluded_repeat_events": excluded_repeats,
            "unresolved_composition_events": unresolved_compositions,
            "trust": "UNVERIFIED_CLIENT_TELEMETRY",
            "official_scoring_eligible": False,
            "reason": "IME composition records do not reveal the physical key sequence.",
        }

    return {
        "status": "COUNTED",
        "counter_version": STROKE_COUNTER_VERSION,
        "language": language,
        "keyboard_layout": keyboard_layout,
        "counted_strokes": counted,
        "excluded_modifier_events": excluded_modifiers,
        "excluded_repeat_events": excluded_repeats,
        "unresolved_composition_events": 0,
        "trust": "UNVERIFIED_CLIENT_TELEMETRY",
        "official_scoring_eligible": False,
        "reason": "Counts captured physical key-down events only; client telemetry is not independently verified.",
    }


def _unresolved(status, reason):
    return {
        "status": status,
        "counter_version": STROKE_COUNTER_VERSION,
        "counted_strokes": None,
        "trust": "UNVERIFIED_CLIENT_TELEMETRY",
        "official_scoring_eligible": False,
        "reason": reason,
    }
