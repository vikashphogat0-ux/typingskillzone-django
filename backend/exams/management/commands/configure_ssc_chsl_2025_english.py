from datetime import date

from django.core.management.base import BaseCommand, CommandError

from exams.models import ExamConfiguration


class Command(BaseCommand):
    help = "Apply the user-provided SSC CHSL 2025 English TCS typing-test profile."

    def handle(self, *args, **options):
        exam = ExamConfiguration.objects.filter(
            name="SSC CHSL 2025 English Test (TCS Interface)"
        ).first()
        if exam is None:
            raise CommandError(
                "SSC CHSL 2025 English Test (TCS Interface) is not in the catalogue. "
                "Run seed_exam_catalogue first."
            )

        profile = {
            "category": ExamConfiguration.Category.SSC,
            "language": "ENGLISH",
            "script": "LATIN",
            "interface_type": "TCS_ION_STANDARD",
            "duration_seconds": 600,
            "passage_format": ExamConfiguration.PassageFormat.TCS,
            "passage_layout": ExamConfiguration.PassageLayout.TCS,
            "passage_source_mode": ExamConfiguration.PassageSourceMode.SCREEN,
            "keyboard_layout": "English QWERTY",
            "minimum_wpm": 35,
            "required_keystrokes": 1750,
            "strokes_per_word": 5,
            "error_allowance_percent": 7,
            "allow_backspace": True,
            "backspace_policy": ExamConfiguration.BackspacePolicy.FULL,
            "allow_paste": False,
            "allow_copy": False,
            "allow_cut": False,
            "allow_passage_repeat": False,
            "scoring_mode": ExamConfiguration.ScoringMode.CUSTOM,
            "error_rules": {
                "classification": "FULL_HALF_MISTAKES",
                "full_mistakes": ["omission", "substitution", "addition"],
                "half_mistakes": [
                    "capitalization", "punctuation", "internal_spacing",
                    "word_spacing", "paragraph_breaks",
                ],
                "full_mistake_weight": 1.0,
                "half_mistake_weight": 0.5,
                "error_denominator": "total_reference_passage_words",
            },
            "scoring_rules": {
                "formula": "SSC_CHSL_2025_ENGLISH",
                "minimum_wpm": 35,
                "minimum_kdph": 10500,
                "minimum_strokes": 1750,
                "compensatory_time_enabled": True,
                "compensatory_duration_seconds": 900,
                "strokes_per_word": 5,
                "passage_word_range": {"minimum": 350, "maximum": 400},
                "category_error_caps": {
                    "UR": 7,
                    "OBC": 10,
                    "EWS": 10,
                    "SC": 10,
                    "ST": 10,
                    "PWD": 10,
                    "OTHER_RESERVED": 10,
                },
                "candidate_category_default": "UR",
                "qualifying_only": True,
                "add_to_final_merit": False,
                "error_percent_formula": (
                    "(full_mistakes + 0.5 * half_mistakes) "
                    "/ total_reference_passage_words * 100"
                ),
                "gross_wpm_formula": "reported_key_depressions / 5 / elapsed_minutes",
                "gross_kdph_formula": "reported_key_depressions * 60 / elapsed_minutes",
            },
            "qualification_rules": {
                "mode": "QUALIFYING_ONLY",
                "minimum_wpm": 35,
                "minimum_keystrokes": 1750,
                "compensatory_time_enabled": True,
                "compensatory_duration_seconds": 900,
                "category_error_caps": {
                    "UR": 7, "OBC": 10, "EWS": 10, "SC": 10,
                    "ST": 10, "PWD": 10, "OTHER_RESERVED": 10,
                },
                "all": [
                    {"metric": "gross_wpm", "operator": "gte", "value": 35},
                    {"metric": "error_percent", "operator": "lte", "value": 7},
                ],
            },
            "verification_status": ExamConfiguration.Verification.PARTIAL,
            "source_title": "User-provided SSC CHSL 2025 English simulator rules",
            "source_checked_at": date.today(),
            "rule_config_version": 1,
            "rule_notes": (
                "Configured from the exact user-supplied simulator specification. "
                "10-minute English QWERTY TCS split-screen; no word or error highlighting; "
                "manual reference scrolling; Backspace enabled; clipboard copy/paste/cut "
                "disabled; Ctrl+A and whole-field clearing blocked in the live UI; "
                "350–400 word passage; 35 WPM / 10,500 KDPH / 1,750 keystroke target; "
                "full mistakes count 1 and half mistakes count 0.5; error percentage "
                "uses the total reference passage word count; UR cap 7%, reserved-category "
                "cap 10%; qualifying-only. Compensatory-time duration is not specified "
                "in the supplied rules and is not fabricated. Qualification remains "
                "provisional until the complete recruitment-cycle rule profile is verified."
            ),
        }
        for field, value in profile.items():
            setattr(exam, field, value)
        exam.save()
        self.stdout.write(self.style.SUCCESS(
            f"Configured {exam.name} ({exam.code}) with the CHSL 2025 English profile."
        ))
