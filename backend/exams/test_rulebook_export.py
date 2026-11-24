from django.test import SimpleTestCase

from exams.management.commands.export_exam_rulebook import extract_profile_blocks


class RulebookExportTests(SimpleTestCase):
    def test_preserves_profile_order_duplicates_and_verbatim_source(self):
        paragraphs = [
            "SSC Example English",
            "Exam Pattern & Qualifying Nature: Qualifying test.",
            "Duration & Target: 10 minutes.",
            "SSC Example English",
            "Exam Pattern & Qualifying Nature: Separate cycle profile.",
            "Duration & Target: 12 minutes.",
        ]
        profiles = extract_profile_blocks(paragraphs)
        self.assertEqual(len(profiles), 2)
        self.assertEqual(profiles[0]["name"], profiles[1]["name"])
        self.assertNotEqual(profiles[0]["profile_id"], profiles[1]["profile_id"])
        self.assertEqual(profiles[0]["source_text"][1], "Duration & Target: 10 minutes.")
        self.assertEqual(profiles[1]["source_text"][1], "Duration & Target: 12 minutes.")

    def test_missing_heading_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            extract_profile_blocks(["Exam Pattern & Qualifying Nature: orphaned"])
