from datetime import date

from django.core.management.base import BaseCommand
from django.db.models import Q

from exams.models import ExamConfiguration


class Command(BaseCommand):
    help = "Configure the Delhi Police Head Constable Ministerial English and Hindi simulators."

    PROFILES = (
        {
            "language": "ENGLISH",
            "script": "LATIN",
            "code": "delhi-police-hcm-english",
            "name": "Delhi Police Head Constable Ministerial — English",
            "minimum_wpm": 30,
            "keyboard_layout": "QWERTY",
        },
        {
            "language": "HINDI",
            "script": "DEVANAGARI",
            "code": "delhi-police-hcm-hindi",
            "name": "Delhi Police Head Constable Ministerial — Hindi",
            "minimum_wpm": 25,
            "keyboard_layout": "Mangal",
        },
    )

    def handle(self, *args, **options):
        for profile in self.PROFILES:
            existing = (
                ExamConfiguration.objects.filter(
                    Q(code__icontains="delhi") | Q(name__icontains="delhi"),
                    language__iexact=profile["language"],
                )
                .order_by("id")
                .first()
            )
            exam = existing or ExamConfiguration(code=profile["code"])
            exam.name = profile["name"]
            exam.code = profile["code"]
            exam.category = ExamConfiguration.Category.POLICE
            exam.language = profile["language"]
            exam.script = profile["script"]
            exam.interface_type = "TCS_ION_STANDARD"
            exam.duration_seconds = 600

            # Mode 1: split reference/input panes, plain text and free-flow typing.
            exam.passage_format = ExamConfiguration.PassageFormat.TCS
            exam.passage_layout = ExamConfiguration.PassageLayout.PARA_TAB
            exam.passage_source_mode = ExamConfiguration.PassageSourceMode.PRINTED
            exam.passage_preserve_tabs = True
            exam.passage_tab_size = 4
            exam.passage_font_family = "Arial" if profile["language"] == "ENGLISH" else "Mangal"
            exam.passage_font_size_pt = 12
            exam.passage_line_height = 1.6
            exam.passage_paragraph_spacing_pt = 12
            exam.passage_alignment = ExamConfiguration.TextAlignment.LEFT
            exam.passage_first_line_indent_em = 0

            # Rulebook Mode 1 explicitly enables Backspace; standard editing remains free-flow.
            exam.allow_backspace = True
            exam.backspace_policy = ExamConfiguration.BackspacePolicy.FULL
            exam.allow_delete = True
            exam.allow_arrow_navigation = True
            exam.allow_paste = True
            exam.allow_copy = True
            exam.allow_cut = True
            exam.enter_behavior = ExamConfiguration.EnterBehavior.NEW_LINE
            exam.space_behavior = ExamConfiguration.SpaceBehavior.NORMAL
            exam.tab_behavior = ExamConfiguration.TabBehavior.INSERT_SPACES
            exam.keyboard_layout = profile["keyboard_layout"]
            exam.text_encoding = "UTF-8" if profile["language"] == "HINDI" else "ASCII"

            exam.minimum_wpm = profile["minimum_wpm"]
            exam.required_keystrokes = None
            exam.strokes_per_word = 5
            exam.error_allowance_percent = 5
            exam.mistake_penalty_strokes = None
            exam.scoring_mode = ExamConfiguration.ScoringMode.CUSTOM
            exam.error_rules = {"count_word_errors": True, "mistake_weighting": "FULL_HALF"}
            exam.scoring_rules = {
                "formula": "DELHI_POLICE_MODEL_D",
                "maximum_marks": 25,
                "score_bands": [],
                "full_mistake_weight": 1,
                "half_mistake_weight": 0.5,
                "full_mistake_categories": ["omission", "substitution", "addition"],
                "half_mistake_categories": [
                    "capitalization", "punctuation", "internal_spacing",
                    "word_spacing", "paragraph_breaks",
                ],
                "marks_configuration_status": "PENDING_OFFICIAL_BANDS",
            }
            exam.qualification_rules = {
                "allow_partial_verification": True,
                "all": [
                    {"metric": "gross_wpm", "operator": "gte", "value": profile["minimum_wpm"]},
                    {"metric": "error_percent", "operator": "lte", "value": 5},
                ],
            }

            # The supplied compendium is a consolidated secondary rulebook, not
            # the original recruitment notification. Keep the profile provisional.
            exam.verification_status = ExamConfiguration.Verification.PARTIAL
            exam.source_title = "User-provided Indian Government Typing Exam Simulators Master Rulebook"
            exam.source_checked_at = date.today()
            exam.official_source_url = ""
            exam.rule_config_version = 2
            exam.rule_notes = (
                "Configured from the user-provided master rulebook, page 5 (Delhi Police HC) "
                "and page 2 (universal mistake rules). 10 minutes; English 30 WPM; Hindi "
                "25 WPM; Backspace enabled; 5% weighted mistake cap; Model D, 0-25 speed-graded "
                "merit marks. The source does not publish the 0-25 speed-to-marks bands, so "
                "score_bands intentionally remains empty and marks remain pending until an "
                "official conversion schedule is supplied. Qualification is provisional."
            )
            exam.display_order = 10
            exam.is_active = True
            exam.save()
            self.stdout.write(self.style.SUCCESS(
                f"Configured {exam.code} (id={exam.pk}, verification={exam.verification_status})."
            ))
