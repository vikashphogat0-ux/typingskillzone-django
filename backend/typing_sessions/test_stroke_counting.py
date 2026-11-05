from django.test import SimpleTestCase

from typing_sessions.stroke_counting import count_stroke_events


class StrokeEventCountingTests(SimpleTestCase):
    def test_english_counts_physical_key_down_events(self):
        result = count_stroke_events(
            language="ENGLISH",
            keyboard_layout="US_QWERTY",
            events=[
                {"type": "KEY_DOWN", "code": "KeyH"},
                {"type": "KEY_DOWN", "code": "KeyI"},
                {"type": "KEY_DOWN", "code": "Space"},
                {"type": "KEY_DOWN", "code": "KeyX"},
            ],
        )
        self.assertEqual(result["status"], "COUNTED")
        self.assertEqual(result["counted_strokes"], 4)
        self.assertFalse(result["official_scoring_eligible"])

    def test_hindi_physical_key_events_are_counted_without_counting_unicode_characters(self):
        result = count_stroke_events(
            language="HINDI",
            keyboard_layout="INSCRIPT",
            events=[
                {"type": "KEY_DOWN", "code": "KeyK"},
                {"type": "KEY_DOWN", "code": "KeyA"},
                {"type": "KEY_DOWN", "code": "Space"},
            ],
        )
        self.assertEqual(result["status"], "COUNTED")
        self.assertEqual(result["counted_strokes"], 3)
        self.assertEqual(result["language"], "HINDI")
        self.assertFalse(result["official_scoring_eligible"])

    def test_modifier_and_repeat_events_are_excluded(self):
        result = count_stroke_events(
            language="ENGLISH",
            keyboard_layout="US_QWERTY",
            events=[
                {"type": "KEY_DOWN", "code": "ShiftLeft"},
                {"type": "KEY_DOWN", "code": "KeyA"},
                {"type": "KEY_DOWN", "code": "KeyA", "repeat": True},
            ],
        )
        self.assertEqual(result["counted_strokes"], 1)
        self.assertEqual(result["excluded_modifier_events"], 1)
        self.assertEqual(result["excluded_repeat_events"], 1)

    def test_ime_composition_makes_count_incomplete(self):
        result = count_stroke_events(
            language="HINDI",
            keyboard_layout="IME",
            events=[
                {"type": "KEY_DOWN", "code": "KeyK"},
                {"type": "COMPOSITION_COMMIT", "data": "क"},
            ],
        )
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["counted_strokes"], 1)
        self.assertEqual(result["unresolved_composition_events"], 1)
        self.assertFalse(result["official_scoring_eligible"])

    def test_malformed_events_are_rejected(self):
        result = count_stroke_events(
            language="ENGLISH",
            keyboard_layout="US_QWERTY",
            events=[{"type": "KEY_DOWN"}],
        )
        self.assertEqual(result["status"], "INVALID_EVENT_STREAM")
        self.assertIsNone(result["counted_strokes"])

    def test_missing_layout_and_unsupported_language_are_not_guessed(self):
        missing = count_stroke_events(language="HINDI", keyboard_layout="", events=[])
        unsupported = count_stroke_events(language="PUNJABI", keyboard_layout="INSCRIPT", events=[])
        self.assertEqual(missing["status"], "LAYOUT_REQUIRED")
        self.assertEqual(unsupported["status"], "UNSUPPORTED_LANGUAGE")
