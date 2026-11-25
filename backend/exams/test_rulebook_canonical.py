import re
import unittest

from exams.rulebook_canonical import CANONICAL_EXPECTED, RAW_EXPECTED, alias_index, canonicalize, clean_name


def _raw(number, name, text=None):
    return {"number": number, "profile_id": f"{number}-{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')}-{number:03d}",
            "name": name, "source_heading": name, "source_text": text or [f"Duration & Target: 10 minutes"]}


class CanonicalRulebookTests(unittest.TestCase):
    def setUp(self):
        self.raw = [
            _raw(1, "1. 1. SSC CHSL 2025 English Test (TCS Interface)"),
            _raw(21, "21. 21. MP High Court Jabalpur English", ["Qualifying Criteria: typically 5%-10% max error."]),
            _raw(156, "156. MP High Court Jabalpur English", ["Qualifying / merit-linked per recruitment rules."]),
            _raw(30, "30. 30. Rajasthan HC STENO/JJA/LDC English"),
            _raw(130, "130. Rajasthan HC STENO/JJA/LDC English"),
            _raw(12, "12. 12. Bombay High Court - English Test"),
            _raw(149, "149. Bombay High Court English Test"),
            _raw(161, "161. MP-CPCT English Typing Test"),
            _raw(160, "160. MP-CPCT Mangal Inscript Hindi"),
        ]
        self.canonical = canonicalize(self.raw)
        self.index = alias_index(self.canonical)

    def test_duplicate_names_remain_independent_source_profiles(self):
        mp = self.index[self.raw[1]["profile_id"]]
        mp_duplicate = self.index[self.raw[2]["profile_id"]]
        self.assertIsNot(mp, mp_duplicate)
        self.assertEqual(mp["merged_source_count"], 1)
        self.assertEqual(mp["aliases"], [])

    def test_duplicate_names_are_allowed_when_source_profile_ids_differ(self):
        names = [clean_name(r["name"]).lower() for r in self.canonical]
        self.assertLess(len(set(names)), len(names))
        self.assertEqual(len({r["profile_id"] for r in self.canonical}), len(self.canonical))

    def test_titles_have_no_leading_punctuation_or_doubled_numbers(self):
        for record in self.canonical:
            self.assertIsNone(re.match(r"^[\s.\d]+", record["name"]), record["name"])
            self.assertIsNone(re.search(r"\d+\.\s*\d+\.", record["name"]), record["name"])

    def test_explicit_fields_are_applied(self):
        mp = self.index[self.raw[1]["profile_id"]]
        self.assertEqual(mp["evaluation_mode"], "qualifying")
        self.assertEqual(mp["max_error_percent"], {"range": [5, 10], "configurable_by_admin": True, "enforced": False})
        rj = self.index[self.raw[3]["profile_id"]]
        self.assertEqual(rj["backspace_mode"], "allowed")
        self.assertIs(rj["clipboard_allowed"], False)
        mp_en = self.index[self.raw[7]["profile_id"]]
        self.assertEqual(mp_en["min_net_words_required"], 450)
        self.assertEqual(mp_en["passage_target_words"], {"min": 550, "max": 600})
        mp_hi = self.index[self.raw[8]["profile_id"]]
        self.assertEqual(mp_hi["min_net_words_required"], 300)
        self.assertEqual(mp_hi["passage_target_words"], {"min": 450, "max": 500})
        bombay = self.index[self.raw[5]["profile_id"]]
        self.assertEqual(bombay["target_strokes"], 2000)
        self.assertEqual(bombay["passage_buffer_strokes"], 2800)
        self.assertIsNot(bombay, self.index[self.raw[6]["profile_id"]])

    def test_hedged_wording_is_a_caveat_and_not_enforced(self):
        mp = self.index[self.raw[1]["profile_id"]]
        self.assertTrue(any("typically" in c for c in mp["caveats"]))
        self.assertFalse(mp["hedged_constraints_enforced"])

    def test_every_profile_is_source_compiled_practice_only(self):
        for record in self.canonical:
            self.assertEqual(record["verification_status"], "source-compiled")
            self.assertEqual(record["exam_mode"], "practice_only")

    def test_expected_counts_are_documented(self):
        self.assertEqual(RAW_EXPECTED, 161)
        self.assertEqual(CANONICAL_EXPECTED, 161)

    def test_importer_no_longer_marks_profiles_verified(self):
        from pathlib import Path
        source = Path(__file__).with_name("management").joinpath("commands", "import_exam_rulebook_profiles.py").read_text(encoding="utf-8")
        self.assertNotIn("Verification.VERIFIED", source)


if __name__ == "__main__":
    unittest.main()
