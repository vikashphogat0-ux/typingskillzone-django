"""Import the user-verified Master Exam Rulebook into configurable exam profiles.

The source wording is retained verbatim. Exam-specific settings are stored in the
existing JSON rule fields so admins can select variants without changing engine code.
"""
import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from exams.catalogue import infer_metadata
from exams.models import ExamConfiguration


def _source_lines(profile, prefix):
    return [line for line in profile.get("source_text", []) if line.startswith(prefix)]


def _first_duration_seconds(lines):
    for line in lines:
        match = re.search(r"(\d+)\s*minutes?", line, re.IGNORECASE)
        if match:
            return int(match.group(1)) * 60
    return None


def _explicit_number(pattern, text, cast=int):
    match = re.search(pattern, text, re.IGNORECASE)
    return cast(match.group(1)) if match else None


def _backspace_policy(lines):
    text = " ".join(lines).lower()
    if re.search(r"backspace\s+(?:is\s+)?disabled", text):
        return ExamConfiguration.BackspacePolicy.DISABLED
    if re.search(r"backspace\s+is\s+allowed", text):
        return ExamConfiguration.BackspacePolicy.FULL
    if "backspace behavior depends" in text or "backspace behaviour depends" in text:
        return ExamConfiguration.BackspacePolicy.NOT_SPECIFIED
    return ExamConfiguration.BackspacePolicy.NOT_SPECIFIED


def _explicit_interaction_defaults(text):
    """Return only interaction settings directly stated in source wording."""
    values = {}
    lower = text.lower()
    if re.search(r"copy\\s*/\\s*paste.*disabled|copy/paste disabled|copy and paste.*disabled", lower):
        values.update(allow_copy=False, allow_paste=False)
    elif re.search(r"copy\\s*/\\s*paste.*allowed|copy/paste allowed|copy and paste.*allowed", lower):
        values.update(allow_copy=True, allow_paste=True)
    if re.search(r"delete key.*disabled|deletion.*disabled", lower):
        values["allow_delete"] = False
    elif re.search(r"delete key.*allowed|deletion.*allowed", lower):
        values["allow_delete"] = True
    if re.search(r"arrow keys?.*disabled|arrow navigation.*disabled", lower):
        values["allow_arrow_navigation"] = False
    elif re.search(r"arrow keys?.*allowed|arrow navigation.*allowed", lower):
        values["allow_arrow_navigation"] = True
    if re.search(r"enter\\s+(?:key\\s+)?(?:inserts?|creates?)\\s+(?:a\\s+)?new\\s+line", lower):
        values["enter_behavior"] = ExamConfiguration.EnterBehavior.NEW_LINE
    if re.search(r"(?:normal\\s+)?spacebar", lower):
        values["space_behavior"] = ExamConfiguration.SpaceBehavior.NORMAL
    tab_match = re.search(r"tab\\s+inserts?\\s+(\\d+)\\s+spaces?", lower)
    if tab_match:
        values["tab_behavior"] = ExamConfiguration.TabBehavior.INSERT_SPACES
        values["passage_tab_size"] = int(tab_match.group(1))
    if "paragraph-based passage" in lower or "paragraph based passage" in lower:
        values["passage_layout"] = ExamConfiguration.PassageLayout.PARAGRAPHS
    if "on-screen" in lower or "on screen" in lower:
        values["passage_source_mode"] = ExamConfiguration.PassageSourceMode.SCREEN
    return values

def _explicit_keyboard_layout(name, text):
    combined = (name + " " + text).lower()
    if "kruti dev 010" in combined or "krutidev 010" in combined:
        return "Kruti Dev 010 Remington"
    if "remington gail" in combined or "mangal-gail" in combined or "mangal gail" in combined:
        return "Remington Gail"
    if "inscript" in combined:
        return "Inscript"
    if "qwerty" in combined:
        return "QWERTY"
    return ""



def _rrb_scoring_candidate(lines):
    text = " ".join(lines).lower()
    allowance_is_five_percent = bool(
        re.search(r"(?:5%|0\\.05)\\s*(?:of|×|\\*)?\\s*(?:(?:the )?(?:total )?words? typed|typed words)", text)
        or re.search(r"(?:ignored|forgiven|allowance).{0,60}5\\s*%", text)
    )
    ten_word_penalty = bool(
        re.search(r"(?:10|ten)[- ]words?[- ]per[- ](?:excess[- ])?mistake|(?:10|ten) words? (?:per|for each) (?:excess|remaining)?\\s*mistake|10\\s*words?\\s*(?:deducted|penalty)", text)
        or re.search(r"(?:mistakes?|errors?).{0,100}(?:×|\\*)\\s*10|(?:×|\\*)\\s*10.{0,100}(?:mistakes?|errors?)", text)
    )
    if allowance_is_five_percent and ten_word_penalty and "full" in text and "half" in text:
        return {
            "candidate_formula": "RRB_CBTST_5_PERCENT",
            "mistake_allowance_percent": 5,
            "excess_mistake_deduction_words": 10,
            "executable": False,
            "source_formula_text": [line for line in lines if "Formula" in line or "mistake" in line.lower()],
        }
    return None

def _delhi_police_hcm_scoring_candidate(name):
    normalized = (name or "").lower()
    if "delhi police hc english test" in normalized:
        minimum_wpm = 30
        marks_bands = [
            {"minimum_wpm": 51, "marks": 25}, {"minimum_wpm": 46, "marks": 21},
            {"minimum_wpm": 41, "marks": 18}, {"minimum_wpm": 36, "marks": 15},
            {"minimum_wpm": 31, "marks": 12}, {"minimum_wpm": 30, "marks": 10},
        ]
    elif "delhi police hc hindi test" in normalized:
        minimum_wpm = 25
        marks_bands = [
            {"minimum_wpm": 45, "marks": 25}, {"minimum_wpm": 41, "marks": 21},
            {"minimum_wpm": 36, "marks": 18}, {"minimum_wpm": 31, "marks": 15},
            {"minimum_wpm": 26, "marks": 12}, {"minimum_wpm": 25, "marks": 10},
        ]
    else:
        return None
    return {
        "candidate_formula": "DELHI_POLICE_HCM_2025",
        "minimum_wpm": minimum_wpm,
        "maximum_marks": 25,
        "marks_bands": marks_bands,
        "mistake_penalty_words": 1,
        "official_source_url": "https://ssc.gov.in/api/attachment/uploads/masterData/NoticeBoards/Notice_of_DPHCM_2025.pdf",
        "official_source_reference": "SSC Notice of Head Constable (Ministerial) in Delhi Police Examination, 2025, paragraphs 24-24.2",
        "executable": False,
        "verification_note": "Candidate mapped to SSC DPHCM 2025 paras 24-24.2; admin source verification is still required before activation.",
    }


def _ssc_chsl_2025_scoring_candidate(name):
    normalized = (name or "").lower()
    if "ssc chsl 2025 vh category english" in normalized:
        return {
            "candidate_formula": "SSC_CHSL_2025_VH_ENGLISH",
            "minimum_wpm": 35,
            "minimum_kdph": 10500,
            "standard_duration_seconds": 600,
            "compensatory_duration_seconds": 900,
            "minimum_strokes_standard": 1750,
            "minimum_strokes_compensatory": 2625,
            "category_error_caps": {"PWD": 10},
            "compensatory_time_enabled": True,
            "executable": False,
            "official_notice_reference": "SSC CHSL 2025 Notice, para 13.8.13.7; 5-minute compensatory time for eligible scribe candidates",
            "cycle_cutoff_reference": "SSC CHSLE 2025 FRTA, 17 August 2026, paragraph 6(ii): VH/PwBD typing-test error ceiling 10%",
        }
    if "ssc chsl 2025 hindi (kurtidev)" in normalized:
        return {
            "candidate_formula": "SSC_CHSL_2025_HINDI_KRUTIDEV",
            "minimum_wpm": 30, "minimum_kdph": 9000, "minimum_strokes": 1500,
            "keyboard_layout": "Remington Gail / Kruti Dev 010 (rulebook claim; SSC notice does not specify layout)",
            "font": "Kruti Dev 010 (rulebook claim; requires cycle-specific confirmation)",
            "category_error_caps": {"UR": 7, "OBC": 10, "EWS": 10, "SC": 10, "ST": 10, "ESM": 10, "OH": 10, "HH": 10, "VH": 10, "PWD": 10},
            "compensatory_duration_seconds": 900, "standard_duration_seconds": 600,
            "executable": False,
            "verification_note": "SSC CHSL 2025 notice confirms Hindi 30 WPM, 9000 KDPH, 10 minutes and 5-minute scribe compensatory time; it does not specify Kruti Dev or Remington layout. Keep font/layout inactive pending official centre instructions.",
        }
    if "ssc chsl 2025 hindi (mangal font)" in normalized:
        return {
            "candidate_formula": "SSC_CHSL_2025_HINDI_MANGAL",
            "minimum_wpm": 30, "minimum_kdph": 9000, "minimum_strokes": 1500,
            "keyboard_layout": "Inscript / Remington Gail (rulebook claim; requires cycle-specific confirmation)",
            "font": "Mangal Unicode (rulebook claim; requires cycle-specific confirmation)",
            "category_error_caps": {"UR": 7, "OBC": 10, "EWS": 10, "SC": 10, "ST": 10, "ESM": 10, "OH": 10, "HH": 10, "VH": 10, "PWD": 10},
            "compensatory_duration_seconds": 900, "standard_duration_seconds": 600,
            "executable": False,
            "verification_note": "SSC CHSL 2025 notice confirms Hindi 30 WPM, 9000 KDPH, 10 minutes and 5-minute scribe compensatory time; it does not specify Mangal or keyboard layout. Keep font/layout inactive pending official centre instructions.",
        }
    if "ssc chsl 2025 hindi" in normalized:
        return {
            "candidate_formula": "SSC_CHSL_2025_HINDI",
            "minimum_wpm": 30, "minimum_kdph": 9000, "minimum_strokes": 1500,
            "category_error_caps": {"UR": 7, "OBC": 10, "EWS": 10, "SC": 10, "ST": 10, "ESM": 10, "OH": 10, "HH": 10, "VH": 10, "PWD": 10},
            "compensatory_duration_seconds": 900, "standard_duration_seconds": 600,
            "executable": False,
            "verification_note": "SSC CHSL 2025 notice confirms Hindi 30 WPM, 9000 KDPH, 10 minutes and 5-minute scribe compensatory time. Font/layout not specified.",
        }
    if "ssc chsl 2025 english test" in normalized:
        return {
            "candidate_formula": "SSC_CHSL_2025_ENGLISH",
            "minimum_wpm": 35,
            "minimum_kdph": 10500,
            "minimum_strokes": 1750,
            "category_error_caps": {
                "UR": 7, "OBC": 10, "EWS": 10, "SC": 10, "ST": 10,
                "ESM": 10, "OH": 10, "HH": 10, "VH": 10, "PWD": 10,
                "OTHER_RESERVED": 10,
            },
            "executable": False,
            "official_notice_reference": "SSC CHSL 2025 Notice, paras 13.8.13.1-13.8.13.7",
            "cycle_cutoff_reference": "SSC CHSLE 2025 FRTA, 17 August 2026, paragraph 6(ii): UR 7%; all listed reserved/horizontal categories 10%",
        }
    return None

def _ssc_cgl_2025_scoring_candidate(name):
    normalized = (name or "").lower()
    if "ssc cgl 2025 vh category" in normalized:
        return {
            "candidate_formula": "SSC_CGL_2025_VH_DEST",
            "standard_duration_seconds": 900,
            "compensatory_duration_seconds": 1200,
            "target_key_depressions": 2000,
            "error_denominator": "typed_words",
            "normal_error_caps": {"UR": 20, "OBC": 25, "EWS": 25, "SC": 30, "ST": 30, "ESM": 30, "OH": 30, "HH": 30, "VH": 30, "PWD": 30, "OTHER": 30},
            "higher_error_caps": {"UR": 5, "OBC": 7, "EWS": 7, "SC": 7, "ST": 7, "ESM": 7, "OH": 10, "HH": 10, "VH": 10, "PWD": 10},
            "executable": False,
            "official_notice_reference": "SSC CGL 2025 Notice, paras 13.8.10.1-13.8.10.7 and 16.2",
            "verification_note": "Rulebook VH timing is 15 minutes plus 5 minutes for eligible scribe candidates. Select normal or higher standard only from the candidate's post eligibility and current cycle notice.",
        }
    if "ssc cgl 2025 typing test (tcs)" in normalized:
        return {
            "candidate_formula": "SSC_CGL_2025_DEST",
            "duration_seconds": 900,
            "target_key_depressions": 2000,
            "error_denominator": "typed_words",
            "normal_error_caps": {"UR": 20, "OBC": 25, "EWS": 25, "SC": 30, "ST": 30, "ESM": 30, "OH": 30, "HH": 30, "VH": 30, "PWD": 30, "OTHER": 30},
            "higher_error_caps": {"UR": 5, "OBC": 7, "EWS": 7, "SC": 7, "ST": 7, "ESM": 7, "OH": 10, "HH": 10, "VH": 10, "PWD": 10},
            "higher_standard_posts": ["Tax Assistant (CBIC)", "Tax Assistant (CBDT)", "UDC/SSA (Central Bureau of Narcotics)", "Computer Proficiency posts listed in SSC CGL 2025 Notice para 13.8.9"],
            "executable": False,
            "official_notice_reference": "SSC CGL 2025 Notice, paras 13.8.10.1-13.8.10.7 and 16.2-16.14",
            "cycle_cutoff_reference": "SSC CGL 2025 FRTA write-up, 08 April 2026, para 7(ii): higher DEST error limits UR 5%; OBC/SC/ST/EWS/ESM 7%; OH/HH/VH/PwBD-Others 10%",
            "verification_note": "2000 key depressions is the approximate passage size, not a separately stated candidate minimum. Higher-standard posts require the separate 2025 FRTA cutoff; all posts must clear normal standard.",
        }
    if "ssc cgl 2025 more strokes test" in normalized:
        return {
            "candidate_formula": "SSC_CGL_MORE_STROKES_PRACTICE",
            "duration_seconds": 900,
            "practice_target_key_depressions": 2200,
            "baseline_key_depressions": 2000,
            "practice_error_caps": {"UR": 5, "OBC": 7, "EWS": 7, "SC": 7, "ST": 7, "ESM": 7, "OH": 10, "HH": 10, "VH": 10, "PWD": 10},
            "executable": False,
            "official_exam": False,
            "verification_note": "This is a rulebook-defined stamina practice simulator, not an SSC-prescribed separate examination or official qualification test. 2000 is the baseline and 2200+ is the training aim.",
        }
    return None


def build_draft_defaults(profile):
    """Extract safe explicit hints while preserving the complete source prose."""
    name = profile.get("name") or profile.get("source_heading") or ""
    lines = profile.get("source_text") or []
    all_text = " ".join(lines)
    category, language, script, interface = infer_metadata(name)
    if "english" in name.lower():
        language = "ENGLISH"
    elif "hindi" in name.lower() or any(token in name.upper() for token in ("KURTIDEV", "KRUTIDEV", "MANGAL")):
        language = "HINDI"
    elif "marathi" in name.lower():
        language = "MARATHI"

    duration = _first_duration_seconds(_source_lines(profile, "Duration & Target:"))
    if duration is None:
        duration = _first_duration_seconds(lines)

    interaction_lines = _source_lines(profile, "Interface, Passage & Keyboard Rules:")
    interaction_text = " ".join(interaction_lines)
    backspace = _backspace_policy(interaction_lines)
    keyboard_layout = _explicit_keyboard_layout(name, interaction_text)

    # Extract a speed only when the source gives one single explicit WPM value.
    duration_target_text = " ".join(_source_lines(profile, "Duration & Target:"))
    has_wpm_range = re.search(r"\\d+(?:\\.\\d+)?\\s*(?:-|–|—|to)\\s*\\d+(?:\\.\\d+)?\\s*WPM", duration_target_text, re.IGNORECASE)
    wpm_values = set(re.findall(r"(\\d+(?:\\.\\d+)?)\\s*WPM", duration_target_text, re.IGNORECASE))
    minimum_wpm = float(next(iter(wpm_values))) if len(wpm_values) == 1 and not has_wpm_range else None
    required_keystrokes = _explicit_number(r"(\d[\d,]*)\s*key\s*depressions", " ".join(_source_lines(profile, "Duration & Target:")), cast=lambda value: int(value.replace(",", "")))
    if required_keystrokes is not None:
        required_keystrokes = int(str(required_keystrokes).replace(",", ""))

    is_tcs = "tcs ion" in interaction_text.lower() or "tcs-style" in interaction_text.lower()
    passage_layout = ExamConfiguration.PassageLayout.TCS if is_tcs else ExamConfiguration.PassageLayout.UNCONFIGURED
    passage_format = ExamConfiguration.PassageFormat.TCS if is_tcs else ExamConfiguration.PassageFormat.CUSTOM
    source_mode = ExamConfiguration.PassageSourceMode.SCREEN if is_tcs else ExamConfiguration.PassageSourceMode.UNSPECIFIED

    scoring_source = [line for line in lines if "Formula:" in line or "Formula" in line or line.startswith('"')]
    qualification_source = [
        line for line in lines
        if line.startswith("Qualifying Criteria") or line.startswith("Qualifying Criteria &")
        or line.startswith("WPM & Error Formula") or line.startswith("Marks")
        or line.startswith("Accuracy %") or line.startswith("(Where a ")
    ]

    scoring_candidate = _rrb_scoring_candidate(lines)
    if scoring_candidate is None:
        scoring_candidate = _delhi_police_hcm_scoring_candidate(name)
    if scoring_candidate is None:
        scoring_candidate = _ssc_chsl_2025_scoring_candidate(name)
    if scoring_candidate is None:
        scoring_candidate = _ssc_cgl_2025_scoring_candidate(name)
    scoring_payload = {
        "source_formula_text": scoring_source,
        "executable": False,
        "profile_configuration": {
            "schema_version": 1,
            "configurable_by_admin": True,
            "stroke_unit": 5,
            "evaluation_mode": (
                "qualifying" if any("qualifying" in line.lower() for line in lines)
                else "merit_marks" if any(token in all_text.lower() for token in ("marks", "merit", "score"))
                else "qualifying"
            ),
            "category_limits": {},
            "variants": [],
            "post_presets": [],
            "pass_rule": {},
            "source_profile_id": profile.get("profile_id"),
            "source_profile_number": profile.get("number"),
        },
    }
    if scoring_candidate:
        scoring_payload.update(scoring_candidate)
        supported_formulas = {
            "DELHI_POLICE_HCM_2025", "SSC_CHSL_2025_ENGLISH",
            "SSC_CHSL_2025_VH_ENGLISH", "SSC_CGL_2025_DEST",
            "SSC_CGL_2025_VH_DEST",
        }
        candidate_formula = scoring_candidate.get("candidate_formula")
        if candidate_formula in supported_formulas:
            scoring_payload["formula"] = candidate_formula
            scoring_payload["executable"] = True
        scoring_payload["profile_configuration"]["category_limits"] = (
            scoring_candidate.get("category_error_caps")
            or scoring_candidate.get("normal_error_caps") or {}
        )
        if scoring_candidate.get("compensatory_duration_seconds"):
            scoring_payload["profile_configuration"]["variants"] = [
                {"id": "standard", "label": "Standard", "duration_seconds": scoring_candidate.get("standard_duration_seconds")},
                {"id": "compensatory", "label": "Eligible compensatory time", "duration_seconds": scoring_candidate.get("compensatory_duration_seconds"), "requires_eligibility": True},
            ]


    profile_config = scoring_payload["profile_configuration"]
    normalized_name = name.lower()
    # Explicit selectors from the user-approved profile resolution specification.
    if "ssc chsl 2025" in normalized_name and "vh category" not in normalized_name:
        profile_config["variants"] = profile_config.get("variants") or [
            {"id": "standard", "label": "Standard", "duration_seconds": 600},
            {"id": "scribe_pwbd", "label": "Eligible scribe/PwBD", "duration_seconds": 900, "requires_eligibility": True},
        ]
        profile_config["category_limits"] = profile_config.get("category_limits") or {
            "UR": 7, "OBC": 10, "EWS": 10, "SC": 10, "ST": 10, "PwBD": 10, "ESM": 10
        }
    if "ssc chsl 2025 vh category english" in normalized_name:
        profile_config["variants"] = [
            {"id": "vh_compensatory", "label": "VH / eligible scribe", "duration_seconds": 900, "locked": True}
        ]
        profile_config["accessibility"] = {"vh": True, "compensatory_time": True}
    if "ssc cgl 2025" in normalized_name and "more strokes" not in normalized_name:
        profile_config["variants"] = [
            {"id": "normal", "label": "Normal standard", "standard_type": "NORMAL", "duration_seconds": 900},
            {"id": "higher", "label": "Higher standard post", "standard_type": "HIGHER", "duration_seconds": 900, "requires_post_eligibility": True},
        ]
        if "vh category" in normalized_name:
            profile_config["variants"].append(
                {"id": "vh_compensatory", "label": "VH / eligible scribe", "duration_seconds": 1200, "requires_eligibility": True}
            )
    if "ssc mts" in normalized_name or "selection post" in normalized_name:
        profile_config["post_presets"] = [
            {"id": "english", "language": "ENGLISH", "minimum_wpm": 35, "duration_seconds": 600},
            {"id": "hindi", "language": "HINDI", "minimum_wpm": 30, "duration_seconds": 600},
        ]
    if "ssc gd" in normalized_name:
        profile_config["conditional_activation"] = True
        profile_config["post_presets"] = [
            {"id": "english", "language": "ENGLISH", "minimum_wpm": 35, "duration_seconds": 600},
            {"id": "hindi", "language": "HINDI", "minimum_wpm": 30, "duration_seconds": 600},
        ]
    if "ssc cag deo" in normalized_name:
        profile_config["variants"] = [
            {"id": "grade_a", "label": "Grade A", "target_kdph": 8000, "duration_seconds": 900},
            {"id": "grade_b", "label": "Grade B", "target_kdph": 15000, "duration_seconds": 900},
        ]
    if "bombay high court" in normalized_name:
        profile_config["variants"] = [
            {"id": "penalty_20", "label": "20-mark penalty", "scoring_sub_mode": "penalty_20"},
            {"id": "proportional_accuracy", "label": "Proportional accuracy", "scoring_sub_mode": "proportional_accuracy"},
        ]
    if "andhra pradesh" in normalized_name or "aphc" in normalized_name:
        profile_config["post_presets"] = [
            {"id": "post_35", "label": "35 WPM post", "minimum_wpm": 35, "duration_seconds": 600},
            {"id": "post_40", "label": "40 WPM post", "minimum_wpm": 40, "duration_seconds": 600},
        ]
    if "allahabad high court" in normalized_name or "ro & aro" in normalized_name:
        profile_config["pass_rule"] = {"max_marks": 100, "per_mistake_deduction": None, "min_qualifying_marks": None, "admin_configurable": True}
    if "telangana high court" in normalized_name:
        profile_config["post_presets"] = [
            {"id": "speed_30", "minimum_wpm": 30}, {"id": "speed_35", "minimum_wpm": 35},
            {"id": "speed_40", "minimum_wpm": 40}, {"id": "speed_45", "minimum_wpm": 45},
        ]
        profile_config["category_limits"] = {"pass_percent": "admin_configurable"}
    if "gujarat high court" in normalized_name:
        profile_config["pass_rule"] = {"max_error_percent": 5, "admin_configurable_range": [5, 10]}
    if "patna high court" in normalized_name:
        profile_config["post_presets"] = [
            {"id": "english", "language": "ENGLISH", "minimum_wpm": 40, "duration_seconds": 600},
            {"id": "hindi", "language": "HINDI", "minimum_wpm": 30, "font": "Mangal", "layout": "Remington Gail", "duration_seconds": 600},
        ]
    if "punjab" in normalized_name and "haryana" in normalized_name:
        profile_config["variants"] = [
            {"id": "english", "language": "ENGLISH", "minimum_wpm": 30, "duration_seconds": 600},
            {"id": "notified_regional", "language": "NOTIFIED_REGIONAL", "minimum_wpm": 30, "duration_seconds": 600},
        ]
        profile_config["linked_skill_stages"] = {"spreadsheet": False, "office_test": False, "admin_configurable": True}
    if "maharashtra state typing" in normalized_name:
        profile_config["variants"] = [
            {"id": "english_qwerty", "language": "ENGLISH", "layout": "qwerty", "stroke_floor": 2000, "duration_seconds": 600},
            {"id": "marathi_remington", "language": "MARATHI", "layout": "mangal_remington_gail", "stroke_floor": 1500, "duration_seconds": 600},
            {"id": "hindi_inscript", "language": "HINDI", "layout": "mangal_inscript", "stroke_floor": 1500, "duration_seconds": 600},
            {"id": "hindi_krutidev_055", "language": "HINDI", "layout": "krutidev_055", "stroke_floor": 1500, "duration_seconds": 600},
            {"id": "hindi_krutidev_010", "language": "HINDI", "layout": "krutidev_010", "stroke_floor": 1500, "duration_seconds": 600},
        ]
    if "mp state typing" in normalized_name:
        profile_config["variants"] = [
            {"id": "mpesb", "authority": "MPESB"}, {"id": "mphc", "authority": "MPHC"},
            {"id": "spmcil_bnp", "authority": "SPMCIL/BNP"}, {"id": "mp_cpct", "authority": "MP-CPCT"},
        ]
    if "mp high court" in normalized_name and "hindi" in normalized_name:
        profile_config["variants"] = [
            {"id": "mangal_remington_gail", "font_layout": "Mangal Remington Gail"},
            {"id": "mangal_inscript", "font_layout": "Mangal Inscript"},
            {"id": "krutidev_010", "font_layout": "Kruti Dev 010"},
        ]
    if "mp-cpct" in normalized_name or "cpct" in normalized_name:
        profile_config["variants"] = [
            {"id": "english", "language": "ENGLISH", "duration_seconds": 900, "minimum_wpm": 30,
             "slabs": [{"min_wpm": 30, "max_wpm": 40, "percent": 50}, {"min_wpm": 41, "max_wpm": 50, "percent": 60}, {"min_wpm": 51, "max_wpm": 60, "percent": 70}, {"min_wpm": 61, "max_wpm": 80, "percent": 80}, {"min_wpm": 81, "percent": 100}]},
            {"id": "hindi", "language": "HINDI", "duration_seconds": 900, "minimum_wpm": 20,
             "slabs": [{"min_wpm": 20, "max_wpm": 25, "percent": 50}, {"min_wpm": 26, "max_wpm": 30, "percent": 60}, {"min_wpm": 31, "max_wpm": 40, "percent": 70}, {"min_wpm": 41, "max_wpm": 50, "percent": 80}, {"min_wpm": 51, "percent": 100}]},
        ]
        profile_config["evaluation_mode"] = "slab"
        profile_config["pass_rule"] = {"min_slab_percent": 50}
    profile_config["configurable_by_admin"] = True

    defaults = {
        "name": name,
        "category": category,
        "language": language,
        "script": script,
        "interface_type": interface,
        "duration_seconds": duration,
        "minimum_wpm": minimum_wpm,
        "required_keystrokes": required_keystrokes,
        "keyboard_layout": keyboard_layout,
        "backspace_policy": backspace,
        "allow_backspace": backspace != ExamConfiguration.BackspacePolicy.DISABLED,
        "passage_source_mode": source_mode,
        "passage_layout": passage_layout,
        "passage_format": passage_format,
        "scoring_mode": ExamConfiguration.ScoringMode.CUSTOM if scoring_payload.get("executable") else ExamConfiguration.ScoringMode.GENERIC,
        "error_rules": {"source_text": lines, "executable": False},
        "scoring_rules": scoring_payload,
        "qualification_rules": {"source_criteria_text": qualification_source, "executable": bool(scoring_payload.get("executable")), "evaluation_mode": scoring_payload["profile_configuration"]["evaluation_mode"]},
        "verification_status": ExamConfiguration.Verification.VERIFIED,
        "source_title": "Internal rule profile: Master Exam Rulebook (user-verified)",
        "source_checked_at": __import__("datetime").date(2026, 11, 25),
        "rule_notes": (
            "Imported from source profile " + str(profile.get("number")) + " / "
            + str(profile.get("profile_id")) + ". Rulebook source text is retained verbatim. Structured scoring is executable only where a matching engine formula is implemented; other profile rules remain admin-configurable.\n\n"
            + "\n".join(lines)
        ),
        "is_active": True,
    }
    defaults.update(_explicit_interaction_defaults(interaction_text))
    return defaults


class Command(BaseCommand):
    help = "Import user-verified rulebook entries as active, configurable exam profiles."

    def add_arguments(self, parser):
        parser.add_argument("json_path", help="Path to exam_rulebook_profiles.json")
        parser.add_argument("--expected-count", type=int, default=161)
        parser.add_argument("--refresh-existing-drafts", action="store_true", help="Refresh rows previously imported from the rulebook, including active rows carrying the importer source marker; never touch manually sourced profiles.")

    def handle(self, *args, **options):
        path = Path(options["json_path"]).expanduser()
        if not path.is_file():
            raise CommandError(f"JSON file not found: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CommandError(f"Could not read valid UTF-8 JSON: {exc}") from exc

        profiles = payload.get("profiles")
        expected = options["expected_count"]
        if payload.get("schema_version") != 1 or not isinstance(profiles, list):
            raise CommandError("Unsupported rulebook JSON schema.")
        if expected and len(profiles) != expected:
            raise CommandError(f"Expected {expected} profiles; found {len(profiles)}. No rows imported.")
        ids = [item.get("profile_id") for item in profiles]
        if any(not value for value in ids) or len(set(ids)) != len(ids):
            raise CommandError("Every profile must have a unique, non-empty profile_id. No rows imported.")

        created = preserved = 0
        for profile in profiles:
            code = slugify(profile["profile_id"])[:180]
            defaults = {"code": code, **build_draft_defaults(profile)}
            exam, was_created = ExamConfiguration.objects.get_or_create(code=code, defaults=defaults)
            if was_created:
                created += 1
            elif options["refresh_existing_drafts"] and (
                exam.source_title.startswith("Internal rule profile: Master Exam Rulebook")
                or (not exam.is_active and exam.source_title == "Master Exam Rulebook — source-preserved draft")
            ):
                for field, value in defaults.items():
                    setattr(exam, field, value)
                exam.save()
                preserved += 1
            else:
                preserved += 1

        self.stdout.write(self.style.SUCCESS(
            f"Rulebook import complete: {created} active profiles created; "
            f"{preserved} existing profiles preserved/refreshed; {len(profiles)} source entries processed."
        ))
        self.stdout.write(self.style.WARNING(
            "Profiles are marked verified from the user-confirmed internal rulebook. Only formulas implemented by the scoring engine are marked executable; other profiles retain full source criteria and admin-configurable structured settings. Existing importer-owned profiles are refreshed only with --refresh-existing-drafts."
        ))
