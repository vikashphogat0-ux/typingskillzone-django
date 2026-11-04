"""Apply reviewed research defaults once; never overwrite admin-edited profiles."""
from django.core.management.base import BaseCommand

from exams.models import ExamConfiguration


# Only exact catalogue entries are configured. Unverified details are deliberately omitted.
PROFILES = {
    "Delhi Police HC English Test": {
        "duration_seconds": 600, "language": "ENGLISH", "minimum_wpm": 30,
        "passage_word_limit": 400, "passage_source_mode": "PRINTED",
        "scoring_mode": "CUSTOM",
        "scoring_rules": {"score_bands": [[30, 10], [31, 12], [36, 15], [41, 18], [46, 21], [51, 25]],
                          "mistake_penalty_words": 1, "maximum_marks": 25},
        "rule_notes": "Delhi Police HCM 2025: 10-minute English typing, minimum 30 WPM, printed passage minimum 400 words. Backspace restriction not specified in the notification; unrestricted is a practice default.",
    },
    "Delhi Police HC Hindi Test": {
        "duration_seconds": 600, "language": "HINDI", "minimum_wpm": 25,
        "passage_word_limit": 350, "passage_source_mode": "PRINTED",
        "scoring_mode": "CUSTOM",
        "scoring_rules": {"score_bands": [[25, 10], [26, 12], [31, 15], [36, 18], [41, 21], [46, 25]],
                          "mistake_penalty_words": 1, "maximum_marks": 25},
        "rule_notes": "Delhi Police HCM 2025: 10-minute Hindi typing, minimum 25 WPM, printed passage minimum 350 words. Backspace restriction not specified in the notification; unrestricted is a practice default.",
    },
    "Delhi Police AWO/TPO Test": {
        "duration_seconds": 900, "language": "ENGLISH", "required_keystrokes": 1000,
        "passage_word_limit": 200, "passage_source_mode": "PRINTED",
        "scoring_mode": "CUSTOM",
        "scoring_rules": {"mistake_deduction_words": 1, "disqualify_at_mistakes": 25},
        "rule_notes": "Delhi Police AWO/TPO 2025: 15 minutes, 1,000 key depressions and a printed passage of 200 words. Backspace behaviour not specified.",
    },
    "BSF HCM English Test": {
        "duration_seconds": 600, "language": "ENGLISH", "minimum_wpm": 35,
        "strokes_per_word": 5, "error_allowance_percent": 5,
        "scoring_mode": "ERROR_PERCENTAGE",
        "rule_notes": "BSF-led CAPF direct recruitment 2024 profile: 10 minutes, 35 WPM English, 5% permitted mistakes. Backspace behaviour not specified.",
    },
    "BSF HCM Hindi Mangal Gail": {
        "duration_seconds": 600, "language": "HINDI", "minimum_wpm": 30,
        "keyboard_layout": "Remington Gail", "text_encoding": "Mangal",
        "strokes_per_word": 5, "error_allowance_percent": 5,
        "scoring_mode": "ERROR_PERCENTAGE",
        "rule_notes": "BSF-led CAPF direct recruitment 2024 profile: 10 minutes, 30 WPM Hindi, Mangal font; 5% permitted mistakes. Backspace behaviour not specified.",
    },
    "BSF HCM Hindi Mangal Inscript": {
        "duration_seconds": 600, "language": "HINDI", "minimum_wpm": 30,
        "keyboard_layout": "Inscript", "text_encoding": "Mangal",
        "strokes_per_word": 5, "error_allowance_percent": 5,
        "scoring_mode": "ERROR_PERCENTAGE",
        "rule_notes": "BSF-led CAPF direct recruitment 2024 profile: 10 minutes, 30 WPM Hindi, Mangal font; 5% permitted mistakes. Backspace behaviour not specified.",
    },
    "RSMSSB LDC English Typing Test": {
        "duration_seconds": 600, "language": "ENGLISH", "passage_word_limit": 500,
        "passage_format": "PARAGRAPHS", "passage_source_mode": "SCREEN",
        "scoring_mode": "CORRECT_WORD_MARKS",
        "scoring_rules": {"marks_per_correct_word": 0.05, "maximum_marks": 25, "minimum_marks": 9},
        "backspace_policy": "WORD_LOCK_AFTER_SEPARATOR", "space_behavior": "COMMIT_WORD",
        "enter_behavior": "COMMIT_WORD",
        "rule_notes": "RSSB/RSMSSB LDC 2024 Phase-II instructions: 10-minute English speed test, 500-word paragraph passage, 0.05 marks per correct word, 25 marks and 9 minimum. Backspace within current word; previous word locks after Space/Enter.",
    },
    "MP-CPCT English Typing Test": {
        "duration_seconds": 900, "language": "ENGLISH", "passage_format": "PARAGRAPHS",
        "passage_source_mode": "SCREEN", "trial_seconds": 300,
        "rule_notes": "MP CPCT rulebook: 5-minute English mock followed by 15-minute paragraph-based typing. Backspace policy not specified.",
    },
    "MP-CPCT Mangal Remington Gail Hindi": {
        "duration_seconds": 900, "language": "HINDI", "keyboard_layout": "Remington Gail",
        "text_encoding": "Unicode", "passage_format": "PARAGRAPHS",
        "passage_source_mode": "SCREEN", "trial_seconds": 600,
        "rule_notes": "MP CPCT rulebook: 10-minute Hindi mock followed by 15-minute paragraph-based typing; Unicode Remington Gail. Backspace policy not specified.",
    },
    "MP-CPCT Mangal Inscript Hindi": {
        "duration_seconds": 900, "language": "HINDI", "keyboard_layout": "Inscript",
        "text_encoding": "Unicode", "passage_format": "PARAGRAPHS",
        "passage_source_mode": "SCREEN", "trial_seconds": 600,
        "rule_notes": "MP CPCT rulebook: 10-minute Hindi mock followed by 15-minute paragraph-based typing; Unicode Inscript. Backspace policy not specified.",
    },
    "WBPSC Clerkship English Test": {
        "duration_seconds": 600, "language": "ENGLISH", "passage_source_mode": "MANUSCRIPT",
        "trial_seconds": 300, "allow_paste": False,
        "scoring_mode": "FULL_HALF_MISTAKES",
        "rule_notes": "WBPSC Clerkship instructions: 5-minute trial, 10-minute test from hard-copy manuscript; copy/paste prohibited. Exact backspace rule not established.",
    },
    "Jharkhand HC English (Adv.03-24)": {
        "duration_seconds": 300, "language": "ENGLISH", "minimum_wpm": 40,
        "passage_word_limit": 200, "passage_source_mode": "SCREEN",
        "rule_notes": "Jharkhand Civil Court 2024: 200 English words in 5 minutes (40 WPM); qualifying. Passage may be repeated and continued typing counted. Backspace policy not specified.",
    },
    "Jharkhand HC Hindi (Adv.03-24)": {
        "duration_seconds": 600, "language": "HINDI", "minimum_wpm": 30,
        "passage_word_limit": 300, "keyboard_layout": "Kruti Dev 10",
        "text_encoding": "Legacy font", "passage_source_mode": "SCREEN",
        "allow_passage_repeat": True,
        "rule_notes": "Jharkhand Civil Court 2024: 300 Hindi words in 10 minutes (30 WPM), Kruti Dev 10; passage may be repeated and continued typing counted. Backspace policy not specified.",
    },
    "CBSE English Typing Test": {
        "duration_seconds": 600, "language": "ENGLISH", "minimum_wpm": 35,
        "scoring_mode": "CORRECT_WORDS",
        "rule_notes": "CBSE Junior Assistant 2024: 10-minute English typing, 35 WPM; net speed uses correct words only. Backspace policy not specified.",
    },
    "AIIMS CRE English Typing Test": {
        "duration_seconds": 900, "language": "ENGLISH", "minimum_wpm": 35,
        "keyboard_layout": "QWERTY", "strokes_per_word": 50,
        "mistake_penalty_strokes": 50, "scoring_mode": "STROKE_PENALTY",
        "rule_notes": "AIIMS CRE-4 2025 JAA/LDC/UDC: 15 minutes, 35 WPM English, 50 strokes per word and 50-stroke penalty per full mistake. Backspace policy not specified.",
    },
    "AIIMS CRE Hindi Mangal Inscript": {
        "duration_seconds": 900, "language": "HINDI", "minimum_wpm": 30,
        "keyboard_layout": "Inscript", "text_encoding": "Mangal",
        "strokes_per_word": 50, "mistake_penalty_strokes": 50,
        "scoring_mode": "STROKE_PENALTY",
        "rule_notes": "AIIMS CRE-4 2025 JAA/LDC/UDC: 15 minutes, 30 WPM Hindi, Mangal/Inscript, 50 strokes per word and 50-stroke penalty per full mistake. Backspace policy not specified.",
    },
    "Supreme Court of India - JCA Test": {
        "duration_seconds": 600, "language": "ENGLISH", "minimum_wpm": 35,
        "error_allowance_percent": 3, "scoring_mode": "ERROR_PERCENTAGE",
        "rule_notes": "Supreme Court JCA 2025: 10 minutes, 35 WPM English, up to 3% mistakes permitted. Backspace policy not specified.",
    },
    "Patna High Court English Test": {
        "duration_seconds": 600, "language": "ENGLISH", "minimum_wpm": 40,
        "passage_word_limit": 400, "scoring_mode": "CUSTOM",
        "scoring_rules": {"maximum_marks": 100, "minimum_marks": 90},
        "rule_notes": "Patna High Court Computer Operator-cum-Typist 2026: 10 minutes, 400-word English passage, 40 WPM, 100 marks and 90 minimum. Backspace policy not specified.",
    },
    "Bombay High Court - English Test": {
        "duration_seconds": 600, "language": "ENGLISH", "passage_word_limit": 400,
        "scoring_mode": "CUSTOM",
        "scoring_rules": {"minimum_marks": 10},
        "rule_notes": "Bombay High Court Clerk: 10-minute, 400-word English typing test; minimum 10 marks. Backspace policy not specified.",
    },
}


class Command(BaseCommand):
    help = "Seed researched exam typing settings once without overwriting admin-edited configurations."

    def handle(self, *args, **options):
        applied = skipped = missing = 0
        for name, settings in PROFILES.items():
            exam = ExamConfiguration.objects.filter(name=name).first()
            if exam is None:
                missing += 1
                continue
            if exam.rule_config_version >= 2:
                skipped += 1
                continue
            for field, value in settings.items():
                setattr(exam, field, value)
            exam.rule_config_version = 2
            exam.save()
            applied += 1
        self.stdout.write(self.style.SUCCESS(
            f"Typing profiles: {applied} configured, {skipped} preserved, {missing} not found. "
            "Review every profile in Django Admin before publishing."
        ))
