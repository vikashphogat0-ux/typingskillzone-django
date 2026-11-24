"""Idempotently seed the named exam profiles from the supplied master rulebook.

The compendium is a secondary consolidated source. Profiles are marked PARTIAL;
values not established per recruitment notice remain unset and visible as pending.
This command never deletes exams, passages, publications, attempts, or users.
"""
from datetime import date

from django.core.management.base import BaseCommand
from exams.models import ExamConfiguration


# name, category, language, duration seconds, target WPM, interface mode,
# scoring formula, error cap, keyboard, script, required strokes, repeat
PROFILES = [
    # Group A — SSC / central data entry
    ("SSC Data Processing Assistant Grade-A", "SSC", "ENGLISH", 900, 50, 1, "MODEL_A", 5, "QWERTY", "LATIN", 3750, False),
    ("SSC CHSL 2025 LDC/JSA", "SSC", "ENGLISH", 600, 35, 1, "MODEL_A", None, "QWERTY", "LATIN", 1750, False),
    ("SSC CHSL 2025 LDC/JSA", "SSC", "HINDI", 600, 30, 1, "MODEL_A", None, "Mangal (cycle-specific layout)", "DEVANAGARI", 1500, False),
    ("SSC CHSL VH Compensatory English", "SSC", "ENGLISH", 900, 35, 1, "MODEL_A", None, "QWERTY", "LATIN", 1750, False),
    ("SSC CGL VH Compensatory Typing", "SSC", "ENGLISH", 900, None, 1, "MODEL_A", None, "QWERTY", "LATIN", 2000, False),
    ("SSC CHSL Hindi Kruti Dev 010", "SSC", "HINDI_KRUTI", 600, 30, 1, "MODEL_A", None, "Kruti Dev 010", "DEVANAGARI_LEGACY", 1500, False),
    ("SSC CHSL Hindi Mangal", "SSC", "HINDI_MANGAL", 600, 30, 1, "MODEL_A", None, "Mangal", "DEVANAGARI_UNICODE", 1500, False),
    ("SSC CGL 2025 Typing Test", "SSC", "ENGLISH", 900, None, 1, "MODEL_A", None, "QWERTY", "LATIN", 2000, False),
    ("SSC CAG DEO Typing Test", "SSC", "ENGLISH", 900, None, 1, "MODEL_A", None, "QWERTY", "LATIN", 2000, False),
    ("SSC CGL More Strokes Practice", "PRACTICE", "ENGLISH", 900, None, 1, "MODEL_A", None, "QWERTY", "LATIN", 2200, False),
    ("SSC MTS / ER10321-IX", "SSC", "ENGLISH", 600, 35, 1, "MODEL_A", None, "QWERTY", "LATIN", None, False),
    ("SSC MTS / ER10321-IX", "SSC", "HINDI", 600, 30, 1, "MODEL_A", None, "Mangal/Kruti Dev (notice-specific)", "DEVANAGARI", None, False),
    ("SSC GD Typing Test", "POLICE", "ENGLISH", 600, 35, 1, "MODEL_A", None, "QWERTY", "LATIN", None, False),
    ("Postal PA/SA/MTS DEST", "CENTRAL", "ENGLISH", 900, None, 1, "MODEL_A", None, "QWERTY", "LATIN", 2000, False),

    # Group B — Courts
    ("Supreme Court JCA", "COURT", "ENGLISH", 600, 35, 4, "MODEL_A", 3, "QWERTY", "LATIN", 1750, False),
    ("Delhi High Court PA/SPA", "COURT", "ENGLISH", 600, 40, 4, "MODEL_A", 3, "QWERTY", "LATIN", 2000, False),
    ("Delhi High Court JJA", "COURT", "ENGLISH", 600, None, 4, "MODEL_A", None, "QWERTY", "LATIN", None, False),
    ("Allahabad High Court RO/ARO", "COURT", "ENGLISH", 1200, 25, 4, "MODEL_D", None, "QWERTY", "LATIN", 2500, False),
    ("Allahabad High Court Junior Assistant", "COURT", "ENGLISH", 600, 30, 4, "MODEL_D", None, "QWERTY", "LATIN", None, False),
    ("Allahabad High Court Junior Assistant", "COURT", "HINDI", 600, 25, 4, "MODEL_D", None, "Mangal Inscript/Gail (notice-specific)", "DEVANAGARI", None, False),
    ("Bombay High Court English", "COURT", "ENGLISH", None, None, 4, "MODEL_A", None, "QWERTY", "LATIN", None, False),
    ("Patna High Court", "COURT", "ENGLISH", None, None, 4, "MODEL_A", None, "QWERTY", "LATIN", None, False),
    ("Patna High Court", "COURT", "HINDI", None, None, 4, "MODEL_A", None, "Hindi layout per notice", "DEVANAGARI", None, False),
    ("Rajasthan High Court", "COURT", "ENGLISH", None, None, 2, "MODEL_A", None, "QWERTY", "LATIN", None, True),
    ("Rajasthan High Court", "COURT", "HINDI", None, None, 2, "MODEL_A", None, "Kruti Dev 010", "DEVANAGARI_LEGACY", None, True),
    ("Madhya Pradesh High Court Jabalpur", "COURT", "ENGLISH", None, None, 4, "MODEL_A", None, "QWERTY", "LATIN", None, False),
    ("Madhya Pradesh High Court Jabalpur", "COURT", "HINDI", None, None, 4, "MODEL_A", None, "Mangal", "DEVANAGARI_UNICODE", None, False),
    ("Chhattisgarh High Court", "COURT", "ENGLISH", None, None, 4, "MODEL_A", None, "QWERTY", "LATIN", None, False),
    ("Chhattisgarh High Court", "COURT", "HINDI", None, None, 4, "MODEL_A", None, "Kruti Dev 010", "DEVANAGARI_LEGACY", None, False),
    ("Punjab & Haryana High Court", "COURT", "ENGLISH", None, None, 4, "MODEL_A", None, "QWERTY", "LATIN", None, False),
    ("Calcutta High Court Assistant", "COURT", "ENGLISH", None, None, 4, "MODEL_A", None, "QWERTY", "LATIN", None, False),
    ("AP/Telangana/Gujarat High Court Assistant", "COURT", "ENGLISH", None, None, 4, "MODEL_A", None, "QWERTY", "LATIN", None, False),
    ("Jharkhand High Court Civil Clerk", "COURT", "ENGLISH", None, None, 4, "MODEL_A", None, "QWERTY", "LATIN", None, False),
    ("Jharkhand High Court Civil Clerk", "COURT", "HINDI", None, None, 4, "MODEL_A", None, "Kruti Dev 010", "DEVANAGARI_LEGACY", None, False),

    # Group C — Rail / CAPF / defence
    ("RRB NTPC/GDCE", "RAILWAY", "ENGLISH", 600, 30, 3, "MODEL_B", None, "QWERTY", "LATIN", None, True),
    ("RRB NTPC", "RAILWAY", "HINDI", 600, 25, 3, "MODEL_B", None, "Hindi layout per RRB notice", "DEVANAGARI", None, True),
    ("CAPF HCM BSF/CISF/CRPF/ITBP/SSB", "POLICE", "ENGLISH", None, None, 3, "MODEL_B", None, "QWERTY", "LATIN", None, True),
    ("CAPF HCM BSF/CISF/CRPF/ITBP/SSB", "POLICE", "HINDI", None, None, 3, "MODEL_B", None, "Hindi layout per force notice", "DEVANAGARI", None, True),
    ("Delhi Police Head Constable Ministerial", "POLICE", "ENGLISH", 600, 30, 1, "MODEL_D", 5, "QWERTY", "LATIN", None, False),
    ("Delhi Police Head Constable Ministerial", "POLICE", "HINDI", 600, 25, 1, "MODEL_D", 5, "Mangal", "DEVANAGARI", None, False),
    ("Delhi Police AWO/TPO", "POLICE", "ENGLISH", 900, None, 1, "MODEL_A", 5, "QWERTY", "LATIN", 1000, False),
    ("Army Agniveer Clerk/SKT", "POLICE", "ENGLISH", 600, 35, 3, "MODEL_A", 5, "QWERTY", "LATIN", 1750, False),

    # Group D — Delhi NCR / NTA / central autonomous
    ("DSSSB Advt 05/2023 & 01/2024", "CENTRAL", "ENGLISH", 600, 35, 1, "MODEL_A", None, "QWERTY", "LATIN", None, False),
    ("DSSSB Advt 05/2023 & 01/2024", "CENTRAL", "HINDI", 600, 30, 1, "MODEL_A", None, "Mangal/Gail/Inscript/Kruti Dev (post-specific)", "DEVANAGARI", None, False),
    ("DDA ASO/JSA", "CENTRAL", "ENGLISH", 600, 35, 1, "MODEL_A", 5, "QWERTY", "LATIN", None, False),
    ("EPFO SSA", "CENTRAL", "ENGLISH", 600, 35, 4, "MODEL_C1", 5, "QWERTY", "LATIN", None, False),
    ("EPFO SSA", "CENTRAL", "HINDI", 600, 30, 4, "MODEL_C1", 5, "Mangal/Gail (notice-specific)", "DEVANAGARI", None, False),
    ("DU/JNU/IGNOU/EMRS/KVS/CBSE/NCERT clerical typing", "UNIVERSITY", "ENGLISH", 600, 35, 4, "MODEL_C1", 5, "QWERTY", "LATIN", None, False),
    ("DU/JNU/IGNOU/EMRS/KVS/CBSE/NCERT clerical typing", "UNIVERSITY", "HINDI", 600, 30, 4, "MODEL_C1", 5, "Mangal/Gail/Kruti Dev (post-specific)", "DEVANAGARI", None, False),
    ("DRDO Typing Test", "CENTRAL", "ENGLISH", 600, 35, 1, "MODEL_A", 5, "QWERTY", "LATIN", None, False),
    ("DRDO Typing Test", "CENTRAL", "HINDI", 600, 30, 1, "MODEL_A", 5, "Mangal/Kruti Dev (notice-specific)", "DEVANAGARI", None, False),
    ("SPMCIL/Bank Note Press Dewas", "PSU", "ENGLISH", 600, 40, 1, "MODEL_C1", None, "QWERTY", "LATIN", None, False),
    ("SPMCIL/Bank Note Press Dewas", "PSU", "HINDI", 600, 30, 1, "MODEL_C1", None, "Hindi layout per notice", "DEVANAGARI", None, False),
    ("CCRAS/Central Silk Board/NBEMS/Visva Bharati/NPCIL/NIT/IIT/PGIMER/JIPMER/DPSR", "CENTRAL", "ENGLISH", 600, 35, 1, "MODEL_A", 5, "QWERTY", "LATIN", None, False),

    # Group E — Bihar / BELTRON
    ("BELTRON", "STATE", "ENGLISH", 600, 30, 2, "MODEL_C1", None, "QWERTY", "LATIN", None, False),
    ("BELTRON", "STATE", "HINDI", 600, 25, 2, "MODEL_C1", None, "Mangal Remington Gail/Inscript", "DEVANAGARI", None, False),
    ("Bihar SSC/BSSC", "STATE", "ENGLISH", 600, None, 2, "MODEL_C1", None, "QWERTY", "LATIN", None, False),
    ("Bihar SSC/BSSC", "STATE", "HINDI", 600, 30, 2, "MODEL_C1", None, "Mangal Remington Gail", "DEVANAGARI", None, False),
    ("Bihar Vidhan Parishad", "STATE", "ENGLISH", 600, 30, 1, "MODEL_C1", 5, "QWERTY", "LATIN", None, False),
    ("Bihar Vidhan Parishad", "STATE", "HINDI", 600, 30, 1, "MODEL_C1", 5, "Kruti Dev 010/Mangal Gail", "DEVANAGARI", None, False),
    ("Civil Courts Deposition Writer", "COURT", "ENGLISH", 600, 40, 4, "MODEL_C1", None, "QWERTY", "LATIN", None, False),
    ("Civil Courts Deposition Writer", "COURT", "HINDI", 600, 30, 4, "MODEL_C1", None, "Mangal/Kruti Dev", "DEVANAGARI", None, False),
    ("BPSC/Bihar Police ASI/Jeevika/BCECEB/SFC", "STATE", "HINDI", 600, None, 1, "MODEL_C1", None, "Mangal Gail/Inscript", "DEVANAGARI", None, False),

    # Group F — Uttar Pradesh
    ("UPSSSC Junior Assistant", "STATE", "ENGLISH", 300, 30, 4, "MODEL_C1", None, "QWERTY", "LATIN", None, False),
    ("UPSSSC Junior Assistant", "STATE", "HINDI", 300, 25, 4, "MODEL_C1", None, "Kruti Dev 010/Mangal Inscript", "DEVANAGARI", None, False),
    ("UP Police SI/ASI/CO", "POLICE", "ENGLISH", 900, 30, 1, "MODEL_C1", None, "QWERTY", "LATIN", None, False),
    ("UP Police SI/ASI/CO", "POLICE", "HINDI", 900, 25, 1, "MODEL_C1", None, "Mangal Inscript/Gail", "DEVANAGARI", None, False),
    ("UPPSC RO/ARO/APS/Computer Operator", "STATE", "HINDI", None, 25, 1, "MODEL_C1", None, "Kruti Dev 010/Mangal Inscript", "DEVANAGARI", None, False),
    ("UPPSC RO/ARO/APS/Computer Operator", "STATE", "ENGLISH", None, None, 1, "MODEL_C1", None, "QWERTY", "LATIN", None, False),
    ("UPPCL/UPRVUNL Executive/Camp Assistant", "PSU", "HINDI", 300, 30, 1, "MODEL_D", None, "Kruti Dev 010", "DEVANAGARI_LEGACY", None, False),
    ("UPPCL/UPRVUNL Executive/Camp Assistant", "PSU", "ENGLISH", 300, 35, 1, "MODEL_D", None, "QWERTY", "LATIN", None, False),
    ("BHU Typing Test", "UNIVERSITY", "ENGLISH", 600, 35, 4, "MODEL_C1", None, "QWERTY", "LATIN", None, False),
    ("BHU Typing Test", "UNIVERSITY", "HINDI", 600, 30, 4, "MODEL_C1", None, "Mangal/Kruti Dev", "DEVANAGARI", None, False),

    # Group G — regional/state
    ("MPSC Clerk Typist", "STATE", "ENGLISH", 600, 40, 2, "MODEL_A", 7, "QWERTY", "LATIN", 2000, False),
    ("MPSC Clerk Typist", "STATE", "MARATHI", 600, 30, 2, "MODEL_A", 7, "Remington Gail/Kruti Dev 055", "DEVANAGARI", 1500, False),
    ("MPSC Clerk Typist", "STATE", "HINDI", 600, 30, 2, "MODEL_A", 7, "Remington Gail/Kruti Dev 055", "DEVANAGARI", 1500, False),
    ("MP-CPCT", "STATE", "ENGLISH", 900, 30, 2, "MODEL_D", None, "QWERTY", "LATIN", None, False),
    ("MP-CPCT", "STATE", "HINDI", 900, 20, 2, "MODEL_D", None, "Mangal Gail/Inscript", "DEVANAGARI", None, False),
    ("MP Police ASI", "POLICE", "HINDI", 600, 30, 1, "MODEL_C1", None, "Mangal Gail/Inscript", "DEVANAGARI", None, False),
    ("RSMSSB LDC", "STATE", "ENGLISH", 600, None, 1, "MODEL_D", None, "QWERTY", "LATIN", None, False),
    ("RSMSSB LDC", "STATE", "HINDI", 600, None, 1, "MODEL_D", None, "Kruti Dev 010", "DEVANAGARI_LEGACY", None, False),
    ("RSSB Informatics Assistant", "STATE", "ENGLISH", 900, 20, 1, "MODEL_C1", None, "QWERTY", "LATIN", None, False),
    ("RSSB Informatics Assistant", "STATE", "HINDI", 900, 20, 1, "MODEL_C1", None, "Kruti Dev 010", "DEVANAGARI_LEGACY", None, False),
    ("RVUNL Junior Assistant", "PSU", "ENGLISH", 600, None, 1, "MODEL_D", None, "QWERTY", "LATIN", None, False),
    ("RVUNL Junior Assistant", "PSU", "HINDI", 600, None, 1, "MODEL_D", None, "Kruti Dev 010", "DEVANAGARI_LEGACY", None, False),
    ("JSSC JIS(CKHT)CCE LDC", "STATE", "ENGLISH", 600, 30, 1, "MODEL_A", 5, "QWERTY", "LATIN", None, False),
    ("JSSC JIS(CKHT)CCE LDC", "STATE", "HINDI", 600, 25, 1, "MODEL_A", 2, "Kruti Dev 010", "DEVANAGARI_LEGACY", None, False),
    ("HARTRON SETC DEST", "STATE", "ENGLISH", 300, 30, 1, "MODEL_C1", None, "QWERTY", "LATIN", None, False),
    ("Kurukshetra University/LUVAS Hisar/Chandigarh Admin Clerk", "STATE", "ENGLISH", 600, 35, 1, "MODEL_C1", None, "QWERTY", "LATIN", None, False),
    ("WBPSC Clerkship", "STATE", "ENGLISH", 600, 20, 1, "MODEL_C1", None, "QWERTY", "LATIN", None, False),
    ("WBPSC Clerkship", "STATE", "BENGALI", 600, 10, 1, "MODEL_C1", None, "Bijoy", "BENGALI", None, False),
    ("LAHD-SSRB Junior Assistant", "STATE", "ENGLISH", 600, 35, 1, "MODEL_A", 5, "QWERTY", "LATIN", None, False),

    # Group H — AIIMS and diagnostic
    ("AIIMS CRE", "CENTRAL", "ENGLISH", 900, 35, 4, "MODEL_C2", None, "QWERTY", "LATIN", 2625, False),
    ("AIIMS CRE", "CENTRAL", "HINDI", 900, 30, 4, "MODEL_C2", None, "Mangal Inscript/Gail", "DEVANAGARI", 2250, False),
    ("AIIMS Bhubaneswar DEO", "CENTRAL", "ENGLISH", 900, None, 4, "MODEL_C2", None, "QWERTY", "LATIN", 2000, False),
    ("AIIMS JAA/AIIMS Bhopal", "CENTRAL", "ENGLISH", 900, 35, 4, "MODEL_C2", None, "QWERTY", "LATIN", None, False),
    ("Speed Booster RKC", "PRACTICE", "ENGLISH", None, None, 1, "GENERIC", None, "QWERTY", "LATIN", None, True),
    ("Speed Booster RKC", "PRACTICE", "HINDI", None, None, 1, "GENERIC", None, "All configured Hindi layouts", "DEVANAGARI", None, True),
]


class Command(BaseCommand):
    help = "Create/update every named exam/language profile in the master rulebook."

    def handle(self, *args, **options):
        created = updated = 0
        for order, row in enumerate(PROFILES, 1):
            (name, category, language, duration, target, mode, formula,
             error_cap, keyboard, script, strokes, repeat) = row
            code = "-".join(name.lower().replace("/", " ").replace("&", " ").split())
            code = f"{code[:115]}-{language.lower().replace('_', '-')}"
            existing = ExamConfiguration.objects.filter(code=code).first()
            exam, was_created = ExamConfiguration.objects.get_or_create(
                code=code,
                defaults={"name": name, "category": category, "language": language},
            )
            exam.name = f"{name} — {language.replace('_', ' ').title()}"
            exam.category = category
            exam.language = language
            exam.script = script
            exam.interface_type = {
                1: "TCS_ION_STANDARD",
                2: "TCS_ION_WORD_LOCKED",
                3: "RRB_CAPF_STRICT",
                4: "NTA_COURT_SPLIT_PANE",
            }[mode]
            exam.duration_seconds = duration
            exam.passage_format = ExamConfiguration.PassageFormat.TCS if mode == 1 else ExamConfiguration.PassageFormat.CUSTOM
            exam.passage_layout = ExamConfiguration.PassageLayout.PARA_TAB if category == "COURT" else ExamConfiguration.PassageLayout.PARAGRAPHS
            exam.passage_source_mode = ExamConfiguration.PassageSourceMode.SCREEN
            exam.passage_preserve_tabs = category == "COURT"
            exam.passage_tab_size = 4
            exam.passage_font_family = "Arial" if script == "LATIN" else keyboard
            exam.passage_font_size_pt = 12
            exam.passage_line_height = 1.6
            exam.passage_paragraph_spacing_pt = 12
            exam.allow_backspace = mode != 3
            exam.backspace_policy = (
                ExamConfiguration.BackspacePolicy.DISABLED if mode == 3 else
                ExamConfiguration.BackspacePolicy.WORD_LOCK_AFTER_SEPARATOR if mode == 2 else
                ExamConfiguration.BackspacePolicy.FULL
            )
            exam.allow_delete = mode != 3
            exam.allow_arrow_navigation = mode != 3
            exam.allow_paste = False
            exam.allow_copy = False
            exam.allow_cut = False
            exam.enter_behavior = ExamConfiguration.EnterBehavior.NEW_LINE
            exam.space_behavior = ExamConfiguration.SpaceBehavior.COMMIT_WORD if mode == 2 else ExamConfiguration.SpaceBehavior.NORMAL
            exam.tab_behavior = ExamConfiguration.TabBehavior.INSERT_TAB if category == "COURT" else ExamConfiguration.TabBehavior.DISABLED
            exam.keyboard_layout = keyboard
            exam.text_encoding = "UTF-8" if script != "LATIN" else "ASCII"
            exam.minimum_wpm = target
            exam.required_keystrokes = strokes
            exam.strokes_per_word = 5
            exam.error_allowance_percent = error_cap
            exam.allow_passage_repeat = repeat
            exam.scoring_mode = ExamConfiguration.ScoringMode.CUSTOM if formula.startswith("MODEL_") else ExamConfiguration.ScoringMode.GENERIC
            exam.error_rules = {
                "count_word_errors": True,
                "mistake_weighting": "FULL_HALF",
                "full_mistake_categories": ["omission", "substitution", "addition"],
                "half_mistake_categories": ["capitalization", "punctuation", "internal_spacing", "word_spacing", "paragraph_breaks", "transposition"],
            }
            exam.scoring_rules = {
                "formula": formula,
                "strokes_per_word": 5,
                "minimum_strokes": strokes,
                "score_bands": [],
                "marks_configuration_status": "PENDING_OFFICIAL_SCHEDULE" if formula == "MODEL_D" else None,
                "source_rulebook_mode": mode,
            }
            exam.qualification_rules = {
                "status": "PENDING_OFFICIAL_VERIFICATION",
                "requires_all_languages": language in {"ENGLISH", "HINDI"},
                "minimum_wpm": target,
                "maximum_error_percent": error_cap,
                "required_keystrokes": strokes,
                "qualification_is_provisional": True,
            }
            exam.verification_status = ExamConfiguration.Verification.PARTIAL
            exam.source_title = "User-provided Indian Government Typing Exam Simulators Master Rulebook"
            exam.source_checked_at = date.today()
            exam.official_source_url = ""
            exam.rule_config_version = 3
            exam.rule_notes = (
                f"Seeded from the master compendium directory. Interface Mode {mode}; "
                f"formula {formula}; duration/target/error/stroke floor only where the directory "
                "states a single value. Grouped recruitment rows and post/category-specific "
                "differences require individual official notification verification. "
                "Do not present qualification as official while verification_status is PARTIAL. "
                "Mode 3 repeat behavior is configured as permitted repeat, not an auto-loop, "
                "until the precise exam's console instructions are verified."
            )
            exam.display_order = order
            exam.is_active = True
            exam.save()
            created += int(was_created)
            updated += int(not was_created)
        self.stdout.write(self.style.SUCCESS(
            f"Master rulebook profiles processed: {len(PROFILES)}; created={created}; updated={updated}. "
            "Existing unrelated profiles and all learner data were preserved."
        ))
