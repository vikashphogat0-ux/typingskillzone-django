from datetime import date

from django.core.management.base import BaseCommand, CommandError

from exams.models import ExamConfiguration


class Command(BaseCommand):
    help = "Configure the SSC CHSL 2025 VH Category English typing-test profile."

    def handle(self, *args, **options):
        exam = ExamConfiguration.objects.filter(
            name="SSC CHSL 2025 VH Category English"
        ).first()
        if exam is None:
            raise CommandError(
                "SSC CHSL 2025 VH Category English is not in the catalogue. "
                "Run seed_exam_catalogue first or add this exact profile."
            )

        profile = {
            "category": ExamConfiguration.Category.SSC,
            "language": "ENGLISH",
            "script": "LATIN",
            "interface_type": "TCS_ION_VH_ACCESSIBLE_CONFIGURABLE",
            "duration_seconds": 900,
            "passage_format": ExamConfiguration.PassageFormat.TCS,
            "passage_layout": ExamConfiguration.PassageLayout.TCS,
            "passage_source_mode": ExamConfiguration.PassageSourceMode.SCREEN,
            "keyboard_layout": "English QWERTY",
            "minimum_wpm": 35,
            "required_keystrokes": 2625,
            "strokes_per_word": 5,
            "error_allowance_percent": 10,
            "allow_backspace": True,
            "backspace_policy": ExamConfiguration.BackspacePolicy.FULL,
            "allow_paste": False,
            "allow_copy": False,
            "allow_cut": False,
            "allow_passage_repeat": False,
            "allow_arrow_navigation": True,
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
                "formula": "SSC_CHSL_2025_VH_ENGLISH",
                "profile_variant": "VH_CATEGORY_ENGLISH",
                "minimum_wpm": 35,
                "minimum_kdph": 10500,
                "minimum_strokes": 2625,
                "strokes_per_word": 5,
                "passage_word_range": {"minimum": 350, "maximum": 400},
                "category_error_caps": {"PWD": 10, "OTHER_RESERVED": 10},
                "candidate_category_default": "PWD",
                "qualifying_only": True,
                "add_to_final_merit": False,
                "error_percent_formula": (
                    "(full_mistakes + 0.5 * half_mistakes) "
                    "/ total_reference_passage_words * 100"
                ),
                "gross_wpm_formula": "server_derived_keystrokes / 5 / 15_minutes",
                "gross_kdph_formula": "server_derived_keystrokes * 60 / 900_seconds",
                "compensatory_time_enabled": True,
                "compensatory_duration_seconds": 900,
                "base_duration_seconds": 600,
                "compensatory_extension_seconds": 300,
                "accessibility": {
                    "screen_reader_support": "CONFIGURABLE",
                    "enlarged_passage_view": "CONFIGURABLE",
                    "manual_navigation": True,
                    "reader_navigation": True,
                    "passage_dictator": "For eligible VH candidates who opted for a scribe, as stated in the SSC notice",
                    "eligibility_must_be_verified": True,
                },
            },
            "qualification_rules": {
                "mode": "QUALIFYING_ONLY",
                "minimum_wpm": 35,
                "minimum_keystrokes": 2625,
                "maximum_error_percent": 10,
                "all": [
                    {"metric": "gross_wpm", "operator": "gte", "value": 35},
                    {"metric": "error_percent", "operator": "lte", "value": 10},
                ],
            },
            "verification_status": ExamConfiguration.Verification.VERIFIED,
            "source_title": "Internal rule profile: user-verified SSC CHSL 2025 VH Category English specification",
            "source_checked_at": date.today(),
            "rule_config_version": 2,
            "rule_notes": (
                "INTERNAL SOURCE — USER VERIFIED. Treat every rule in this profile as "
                "fully verified for TypingSkillZone's internal simulator specification. "
                "This internal verification is based on the user's explicit confirmation, "
                "not a claim that every interface detail is independently prescribed by "
                "SSC. Profile: 15-minute total duration (10-minute base plus 5-minute "
                "compensatory extension), 35 WPM / 10,500 KDPH / 2,625 keystrokes, "
                "350–400-word English passage, unrestricted Backspace, full mistakes "
                "weighted 1.0, half mistakes weighted 0.5, denominator equal to total "
                "reference passage words, 10% error ceiling, and qualifying-only result. "
                "VH accessibility settings include configurable screen-reader and enlarged "
                "passage presentation, manual and reader navigation. The 5-minute extension "
                "and accessible features are governed by the candidate's assigned internal "
                "VH profile. This is an internally verified TypingSkillZone rule profile."
            ),
        }
        for field, value in profile.items():
            setattr(exam, field, value)
        exam.save()
        self.stdout.write(self.style.SUCCESS(
            f"Configured {exam.name} ({exam.code}) with the VH English profile."
        ))
