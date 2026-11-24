from datetime import date

from django.core.management.base import BaseCommand, CommandError

from exams.models import ExamConfiguration


class Command(BaseCommand):
    help = "Apply the user-approved SSC Data Processing Assistant Grade-A simulator profile."

    def handle(self, *args, **options):
        exam = ExamConfiguration.objects.filter(
            name="SSC Data Processing Assistant Grade-A"
        ).first()
        if exam is None:
            raise CommandError(
                "SSC Data Processing Assistant Grade-A is not in the catalogue. "
                "Run seed_exam_catalogue first."
            )

        # This is a user-supplied simulator profile, not a claim that every
        # interface/scoring detail is specified in an SSC recruitment notice.
        profile = {
            "category": ExamConfiguration.Category.SSC,
            "language": "ENGLISH",
            "script": "LATIN",
            "interface_type": "TCS_ION_STANDARD",
            "duration_seconds": 900,
            "passage_format": ExamConfiguration.PassageFormat.PARAGRAPHS,
            "passage_layout": ExamConfiguration.PassageLayout.PARA_TAB,
            "passage_preserve_tabs": True,
            "passage_tab_size": 4,
            "passage_source_mode": ExamConfiguration.PassageSourceMode.SCREEN,
            "keyboard_layout": "English QWERTY",
            "minimum_wpm": 50,
            "required_keystrokes": 3750,
            "strokes_per_word": 5,
            "error_allowance_percent": 5,
            "trial_seconds": 300,
            "review_seconds": 0,
            "correction_seconds": 0,
            "allow_passage_repeat": False,
            "allow_backspace": True,
            "backspace_policy": ExamConfiguration.BackspacePolicy.FULL,
            "allow_delete": True,
            "allow_arrow_navigation": True,
            "allow_paste": False,
            "allow_copy": False,
            "allow_cut": False,
            "enter_behavior": ExamConfiguration.EnterBehavior.NEW_LINE,
            "space_behavior": ExamConfiguration.SpaceBehavior.NORMAL,
            "tab_behavior": ExamConfiguration.TabBehavior.INSERT_TAB,
            "scoring_mode": ExamConfiguration.ScoringMode.CUSTOM,
            "error_rules": {
                "full_mistakes": ["omission", "substitution", "addition", "spelling", "incomplete_word", "repeated_word"],
                "half_mistakes": ["internal_spacing", "word_spacing", "capitalization", "punctuation", "transposition", "paragraph_indentation"],
                "half_mistake_weight": 0.5,
                "full_mistake_weight": 1.0,
            },
            "scoring_rules": {
                "formula": "SSC_DPA_GRADE_A",
                "minimum_strokes": 3750,
                "minimum_kdph": 15000,
                "compensatory_time_enabled": True,
                "compensatory_duration_seconds": 1200,
                "strokes_per_word": 5,
                "qualifying_only": True,
                "add_to_final_merit": False,
                "candidate_category_default": "UR",
                "category_error_caps": {
                    "UR": 5,
                    "OBC": 7,
                    "EWS": 7,
                    "SC": 10,
                    "ST": 10,
                    "PWD": 10,
                    "OTHER_RESERVED": 10,
                },
                "passage_character_range": {"minimum": 3700, "maximum": 4000},
                "gross_kdph_formula": "total_key_depressions / elapsed_minutes * 60",
                "gross_wpm_formula": "total_key_depressions / (5 * elapsed_minutes)",
                "net_wpm_formula": "(total_key_depressions / 5 - weighted_mistakes) / elapsed_minutes",
                "error_percent_formula": "weighted_mistakes / total_reference_passage_words * 100",
            },
            "qualification_rules": {
                "allow_partial_verification": True,
                "minimum_kdph": 15000,
                "minimum_wpm": 50,
                "mode": "QUALIFYING_ONLY",
                "minimum_keystrokes": 3750,
                "category_error_caps": {
                    "UR": 5, "OBC": 7, "EWS": 7, "SC": 10,
                    "ST": 10, "PWD": 10, "OTHER_RESERVED": 10,
                },
            },
            "verification_status": ExamConfiguration.Verification.VERIFIED,
            "source_title": "Internal rule profile: user-verified SSC DPA Grade-A simulator specification",
            "source_checked_at": date.today(),
            "rule_config_version": 2,
            "rule_notes": (
                "Applied from the user's explicit simulator specification. "
                "15-minute test; 5-minute non-evaluated demo; optional 20-minute "
                "compensatory mode for eligible candidates; 3,750-stroke floor; "
                "split-screen English QWERTY; no live highlighting; manual scroll; "
                "Backspace enabled; clipboard disabled; Tab paragraph indentation; "
                "no passage retyping; full/half mistake weights; category error caps. "
                "This is a user-verified internal implementation profile: the user-supplied "
                "interface and mistake rules are internally verified for TypingSkillZone and are not represented as independently sourced SSC clauses."
            ),
        }
        for field, value in profile.items():
            setattr(exam, field, value)
        exam.save()
        self.stdout.write(self.style.SUCCESS(
            f"Configured {exam.name} ({exam.code}) with the SSC DPA Grade-A profile."
        ))
