import unittest

from exams.rulebook_canonical import with_internal_rulebook_basis


class InternalRulebookBasisTests(unittest.TestCase):
    def test_marks_rules_as_internal_without_losing_existing_rules(self):
        rules = with_internal_rulebook_basis({"formula": "SSC_CHSL_2025_ENGLISH"})
        self.assertEqual(rules["rulebook_verification"], "internal")
        self.assertEqual(rules["formula"], "SSC_CHSL_2025_ENGLISH")

    def test_empty_rules_become_internal_basis_only(self):
        self.assertEqual(with_internal_rulebook_basis(None), {"rulebook_verification": "internal"})

    def test_does_not_mutate_the_input(self):
        original = {"formula": "X"}
        with_internal_rulebook_basis(original)
        self.assertNotIn("rulebook_verification", original)


if __name__ == "__main__":
    unittest.main()
