from django.test import SimpleTestCase

from exams.management.commands.import_exam_rulebook_profiles import (
    _backspace_policy,
    _first_duration_seconds,
    build_draft_defaults,
)
from exams.models import ExamConfiguration


class RulebookDraftImportTests(SimpleTestCase):
    def test_duration_is_extracted_without_guessing(self):
        self.assertEqual(_first_duration_seconds(["Duration & Target: 10 minutes • 35 WPM"]), 600)
        self.assertIsNone(_first_duration_seconds(["Duration varies by notification."]))

    def test_ambiguous_backspace_is_not_guessed(self):
        result = _backspace_policy(["Interface: Backspace behavior depends on centre instructions."])
        self.assertEqual(result, ExamConfiguration.BackspacePolicy.NOT_SPECIFIED)

    def test_disabled_backspace_is_preserved(self):
        result = _backspace_policy(["Interface: Backspace disabled."])
        self.assertEqual(result, ExamConfiguration.BackspacePolicy.DISABLED)

    def test_imported_profile_is_active_and_keeps_source_configuration(self):
        profile = {
            "number": 1,
            "profile_id": "rrb-example-en-001",
            "name": "RRB Example English",
            "source_text": [
                "Exam Pattern & Qualifying Nature: Qualifying.",
                "Duration & Target: 10 minutes • 30 WPM.",
                "Interface, Passage & Keyboard Rules: Backspace disabled.",
                "WPM & Error Formula:",
                '"Net WPM"=(words - mistakes)/10',
                "Qualifying Criteria: At least 30 Net WPM.",
            ],
        }
        defaults = build_draft_defaults(profile)
        self.assertTrue(defaults["is_active"])
        self.assertEqual(defaults["duration_seconds"], 600)
        self.assertEqual(defaults["backspace_policy"], ExamConfiguration.BackspacePolicy.DISABLED)
        self.assertFalse(defaults["scoring_rules"]["executable"])
        self.assertFalse(defaults["qualification_rules"]["executable"])


    def test_explicit_tcs_layout_and_keyboard_hints_are_extracted(self):
        profile = {
            "number": 1,
            "profile_id": "ssc-chsl-example",
            "name": "SSC CHSL Hindi (Mangal Font)",
            "source_text": [
                "Duration & Target: 10 minutes • 30 WPM (9,000 KDPH / ~1,500 key depressions in 10 minutes).",
                "Interface, Passage & Keyboard Rules: TCS iON split-screen with Mangal (Inscript / Remington Gail) layout. Backspace is allowed; copy/paste disabled.",
                "Qualifying Criteria: Meet the applicable benchmark.",
            ],
        }
        defaults = build_draft_defaults(profile)
        self.assertEqual(defaults["duration_seconds"], 600)
        self.assertEqual(defaults["minimum_wpm"], 30.0)
        self.assertEqual(defaults["required_keystrokes"], 1500)
        self.assertEqual(defaults["passage_layout"], ExamConfiguration.PassageLayout.TCS)
        self.assertEqual(defaults["passage_source_mode"], ExamConfiguration.PassageSourceMode.SCREEN)
        self.assertEqual(defaults["keyboard_layout"], "Remington Gail")
        self.assertFalse(defaults["allow_copy"])
        self.assertFalse(defaults["allow_paste"])
        self.assertTrue(defaults["is_active"])

    def test_notification_dependent_or_multiple_wpm_values_are_not_collapsed(self):
        profile = {
            "number": 2,
            "profile_id": "conditional-example",
            "name": "State Typing English",
            "source_text": [
                "Duration & Target: 10 minutes • 30–35 WPM depending on post.",
                "Interface, Passage & Keyboard Rules: English QWERTY.",
            ],
        }
        defaults = build_draft_defaults(profile)
        self.assertIsNone(defaults["minimum_wpm"])
        self.assertEqual(defaults["keyboard_layout"], "QWERTY")
        self.assertEqual(defaults["passage_layout"], ExamConfiguration.PassageLayout.UNCONFIGURED)

    def test_explicit_enter_space_tab_rules_are_extracted(self):
        profile = {
            "number": 3,
            "profile_id": "explicit-controls",
            "name": "Court Typing English",
            "source_text": [
                "Duration & Target: 10 minutes.",
                "Interface, Passage & Keyboard Rules: Enter inserts a new line; normal Spacebar; Tab inserts 5 spaces. Paragraph-based passage on-screen.",
            ],
        }
        defaults = build_draft_defaults(profile)
        self.assertEqual(defaults["enter_behavior"], ExamConfiguration.EnterBehavior.NEW_LINE)
        self.assertEqual(defaults["space_behavior"], ExamConfiguration.SpaceBehavior.NORMAL)
        self.assertEqual(defaults["tab_behavior"], ExamConfiguration.TabBehavior.INSERT_SPACES)
        self.assertEqual(defaults["passage_tab_size"], 5)
        self.assertEqual(defaults["passage_layout"], ExamConfiguration.PassageLayout.PARAGRAPHS)
        self.assertEqual(defaults["passage_source_mode"], ExamConfiguration.PassageSourceMode.SCREEN)

    def test_ambiguous_controls_and_layout_remain_unconfigured(self):
        profile = {
            "number": 4,
            "profile_id": "ambiguous-controls",
            "name": "State Typing Hindi",
            "source_text": [
                "Duration & Target: 10 minutes.",
                "Interface, Passage & Keyboard Rules: Enter/Space/Tab behaviour may vary by centre; passage presentation as per notification.",
            ],
        }
        defaults = build_draft_defaults(profile)
        self.assertNotIn("enter_behavior", defaults)
        self.assertNotIn("space_behavior", defaults)
        self.assertNotIn("tab_behavior", defaults)
        self.assertEqual(defaults["passage_layout"], ExamConfiguration.PassageLayout.UNCONFIGURED)
        self.assertEqual(defaults["passage_source_mode"], ExamConfiguration.PassageSourceMode.UNSPECIFIED)
    def test_rrb_formula_is_recorded_as_non_executable_candidate(self):
        profile = {
            "number": 32,
            "profile_id": "rrb-ntpc-example",
            "name": "RRB NTPC Typing Test English",
            "source_text": [
                "Exam Pattern & Qualifying Nature: Qualifying typing test.",
                "Duration & Target: 10 minutes • 30 WPM (minimum 300 words).",
                "WPM & Error Formula:",
                '"Ignored Mistakes"=0.05×"Typed Words"',
                '"Penalty Words"=max(0,"Total Mistakes"-"Ignored Mistakes")×10',
                '"Net WPM"=("Typed Words"-"Penalty Words")/10',
            ],
        }
        defaults = build_draft_defaults(profile)
        self.assertEqual(defaults["scoring_rules"]["candidate_formula"], "RRB_CBTST_5_PERCENT")
        self.assertEqual(defaults["scoring_rules"]["mistake_allowance_percent"], 5)
        self.assertEqual(defaults["scoring_rules"]["excess_mistake_deduction_words"], 10)
        self.assertFalse(defaults["scoring_rules"]["executable"])
        self.assertEqual(defaults["scoring_mode"], ExamConfiguration.ScoringMode.GENERIC)

    def test_delhi_police_hcm_2025_english_formula_is_executable(self):
        profile = {
            "number": 43,
            "profile_id": "delhi-police-hc-english",
            "name": "Delhi Police HC English Test",
            "source_text": [
                "Exam Pattern & Qualifying Nature: Marks-bearing typing test.",
                "Duration & Target: 10 minutes • 30 WPM minimum qualifying speed.",
                "WPM & Error Formula:",
                '"GWPM"="Total Keystrokes"/(5×10)',
                '"NWPM"=("Gross Words"-("Full"+0.5("Half")))/10',
                "Qualifying Criteria & Marking: 30 WPM minimum; 25 marks.",
            ],
        }
        defaults = build_draft_defaults(profile)
        self.assertEqual(defaults["scoring_rules"]["candidate_formula"], "DELHI_POLICE_HCM_2025")
        self.assertEqual(defaults["scoring_rules"]["minimum_wpm"], 30)
        self.assertEqual(defaults["scoring_rules"]["maximum_marks"], 25)
        self.assertTrue(defaults["scoring_rules"]["executable"])
        self.assertEqual(defaults["scoring_mode"], ExamConfiguration.ScoringMode.CUSTOM)

    def test_delhi_police_hcm_2025_hindi_marks_are_extracted_as_draft(self):
        profile = {
            "number": 44,
            "profile_id": "delhi-police-hc-hindi",
            "name": "Delhi Police HC Hindi Test",
            "source_text": ["Duration & Target: 10 minutes • 25 WPM minimum."],
        }
        defaults = build_draft_defaults(profile)
        self.assertEqual(defaults["scoring_rules"]["candidate_formula"], "DELHI_POLICE_HCM_2025")
        self.assertEqual(defaults["scoring_rules"]["minimum_wpm"], 25)
        self.assertEqual(defaults["scoring_rules"]["marks_bands"][0]["minimum_wpm"], 45)

    def test_ssc_chsl_2025_english_candidate_has_official_cycle_error_caps(self):
        profile = {
            "number": 1,
            "profile_id": "ssc-chsl-2025-english",
            "name": "1. SSC CHSL 2025 English Test (TCS Interface)",
            "source_text": [
                "Duration & Target: 10 minutes • 35 WPM (10,500 KDPH / ~1,750 key depressions).",
                "Qualifying Criteria: Category error limits apply.",
            ],
        }
        defaults = build_draft_defaults(profile)
        candidate = defaults["scoring_rules"]
        self.assertEqual(candidate["candidate_formula"], "SSC_CHSL_2025_ENGLISH")
        self.assertEqual(candidate["minimum_wpm"], 35)
        self.assertEqual(candidate["minimum_strokes"], 1750)
        self.assertEqual(candidate["category_error_caps"]["UR"], 7)
        self.assertEqual(candidate["category_error_caps"]["VH"], 10)
        self.assertTrue(candidate["executable"])
        self.assertEqual(defaults["scoring_mode"], ExamConfiguration.ScoringMode.CUSTOM)

    def test_ssc_chsl_2025_vh_candidate_keeps_compensatory_time_separate(self):
        profile = {
            "number": 2,
            "profile_id": "ssc-chsl-2025-vh",
            "name": "2. SSC CHSL 2025 VH Category English",
            "source_text": [
                "Duration & Target: Extended time (15 minutes, including 5 minutes compensatory time) • 35 WPM.",
            ],
        }
        defaults = build_draft_defaults(profile)
        candidate = defaults["scoring_rules"]
        self.assertEqual(candidate["candidate_formula"], "SSC_CHSL_2025_VH_ENGLISH")
        self.assertEqual(candidate["standard_duration_seconds"], 600)
        self.assertEqual(candidate["compensatory_duration_seconds"], 900)
        self.assertEqual(candidate["minimum_strokes_compensatory"], 2625)
        self.assertEqual(candidate["category_error_caps"]["PWD"], 10)
        self.assertTrue(candidate["compensatory_time_enabled"])
        self.assertTrue(candidate["executable"])

    def test_ssc_chsl_2025_hindi_kruti_dev_remains_unverified_for_font_and_layout(self):
        profile = {
            "number": 3,
            "profile_id": "ssc-chsl-2025-hindi-kurtidev",
            "name": "3. SSC CHSL 2025 Hindi (KurtiDev)",
            "source_text": ["Duration & Target: 10 minutes • 30 WPM (9,000 KDPH / ~1,500 key depressions)."],
        }
        defaults = build_draft_defaults(profile)
        candidate = defaults["scoring_rules"]
        self.assertEqual(candidate["candidate_formula"], "SSC_CHSL_2025_HINDI_KRUTIDEV")
        self.assertEqual(candidate["minimum_wpm"], 30)
        self.assertEqual(candidate["minimum_strokes"], 1500)
        self.assertIn("does not specify Kruti Dev", candidate["verification_note"])
        self.assertFalse(candidate["executable"])
        self.assertEqual(defaults["scoring_mode"], ExamConfiguration.ScoringMode.GENERIC)

    def test_ssc_chsl_2025_hindi_mangal_remains_separate_and_unverified(self):
        profile = {
            "number": 4,
            "profile_id": "ssc-chsl-2025-hindi-mangal",
            "name": "4. SSC CHSL 2025 Hindi (Mangal Font)",
            "source_text": ["Duration & Target: 10 minutes • 30 WPM (9,000 KDPH / ~1,500 key depressions)."],
        }
        defaults = build_draft_defaults(profile)
        candidate = defaults["scoring_rules"]
        self.assertEqual(candidate["candidate_formula"], "SSC_CHSL_2025_HINDI_MANGAL")
        self.assertEqual(candidate["minimum_kdph"], 9000)
        self.assertIn("does not specify Mangal", candidate["verification_note"])
        self.assertFalse(candidate["executable"])

    def test_ssc_cgl_2025_standard_and_vh_are_active_variant_profiles(self):
        standard = build_draft_defaults({
            "number": 5,
            "profile_id": "ssc-cgl-2025-dest",
            "name": "5. SSC CGL 2025 Typing Test (TCS)",
            "source_text": ["Duration & Target: 15 minutes • about 2,000 key depressions."],
        })
        vh = build_draft_defaults({
            "number": 6,
            "profile_id": "ssc-cgl-2025-vh",
            "name": "6. SSC CGL 2025 VH Category",
            "source_text": ["Duration & Target: 20 minutes (15 minutes + 5 minutes compensatory time) • ~2,000 key depressions."],
        })
        self.assertEqual(standard["scoring_rules"]["candidate_formula"], "SSC_CGL_2025_DEST")
        self.assertEqual(standard["scoring_rules"]["duration_seconds"], 900)
        self.assertEqual(vh["scoring_rules"]["candidate_formula"], "SSC_CGL_2025_VH_DEST")
        self.assertEqual(vh["scoring_rules"]["compensatory_duration_seconds"], 1200)
        self.assertTrue(standard["scoring_rules"]["executable"])
        self.assertTrue(vh["scoring_rules"]["executable"])
        self.assertTrue(standard["is_active"])
        self.assertTrue(vh["is_active"])

    def test_ssc_cgl_more_strokes_is_practice_not_official_exam(self):
        defaults = build_draft_defaults({
            "number": 7,
            "profile_id": "ssc-cgl-more-strokes",
            "name": "7. SSC CGL 2025 More Strokes Test",
            "source_text": ["Duration & Target: 15 minutes • ~2,200–2,500+ key depressions."],
        })
        candidate = defaults["scoring_rules"]
        self.assertEqual(candidate["candidate_formula"], "SSC_CGL_MORE_STROKES_PRACTICE")
        self.assertEqual(candidate["practice_target_key_depressions"], 2200)
        self.assertFalse(candidate["official_exam"])
        self.assertFalse(candidate["executable"])
