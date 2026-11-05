from django.test import SimpleTestCase

from exams.provenance import (
    DOMAIN_EVIDENCE_SCHEMA_VERSION,
    SPECIFICATION_DOMAINS,
    validate_domain_evidence,
)


class DomainEvidenceValidationTests(SimpleTestCase):
    def reference(self, **overrides):
        value = {
            "url": "https://ssc.gov.in/notice.pdf",
            "title": "Official recruitment notice",
            "locator": "Page 14, paragraph 7.3",
            "checked_at": "2026-11-05",
            "claims": ["timing.duration_seconds", "scoring.minimum_wpm"],
        }
        value.update(overrides)
        return value

    def test_missing_domains_remain_unverified(self):
        normalized, errors = validate_domain_evidence({})
        self.assertEqual(errors, [])
        self.assertEqual(normalized["schema_version"], DOMAIN_EVIDENCE_SCHEMA_VERSION)
        self.assertEqual(set(normalized["domains"]), set(SPECIFICATION_DOMAINS))
        self.assertTrue(all(
            item["status"] == "UNVERIFIED" and item["references"] == []
            for item in normalized["domains"].values()
        ))

    def test_verified_domain_requires_complete_claim_level_reference(self):
        normalized, errors = validate_domain_evidence({
            "timing": {"status": "VERIFIED", "references": [self.reference()]}
        })
        self.assertEqual(errors, [])
        self.assertEqual(normalized["domains"]["timing"]["status"], "VERIFIED")
        self.assertEqual(
            normalized["domains"]["timing"]["references"][0]["claims"],
            ["timing.duration_seconds", "scoring.minimum_wpm"],
        )

    def test_verified_domain_rejects_missing_locator_or_claims(self):
        _, errors = validate_domain_evidence({
            "timing": {
                "status": "VERIFIED",
                "references": [self.reference(locator="", claims=[])],
            }
        })
        self.assertTrue(any("exact page" in error for error in errors))
        self.assertTrue(any("explicit supported claim" in error for error in errors))

    def test_partial_domain_requires_a_reference(self):
        _, errors = validate_domain_evidence({
            "passage": {"status": "PARTIAL", "references": []}
        })
        self.assertTrue(any("PARTIAL requires" in error for error in errors))

    def test_rejects_unknown_domain_and_non_https_source(self):
        _, errors = validate_domain_evidence({
            "keyboard": {"status": "VERIFIED", "references": [self.reference(url="http://example.com")]},
        })
        self.assertTrue(any("Unknown specification domains" in error for error in errors))

    def test_rejects_invalid_date_and_malformed_payload(self):
        _, errors = validate_domain_evidence({
            "timing": {"status": "VERIFIED", "references": [self.reference(checked_at="yesterday")]},
        })
        self.assertTrue(any("ISO date" in error for error in errors))
        _, malformed = validate_domain_evidence([])
        self.assertTrue(malformed)
