"""Read-only integrity checks for persisted typing result audit metadata.

This module never recalculates scores or mutates historical attempts.
"""
import hashlib
import json


def scoring_rules_fingerprint(scoring_rules):
    """Return the stable SHA-256 fingerprint used by result audit metadata."""
    payload = json.dumps(
        scoring_rules or {},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_result_integrity(*, rules_snapshot, result_snapshot):
    """Compare a result's recorded audit with its immutable session snapshot."""
    if not isinstance(rules_snapshot, dict) or not isinstance(result_snapshot, dict):
        return {"status": "MALFORMED", "checks": [], "reason": "Stored snapshots are not valid objects."}

    audit = result_snapshot.get("scoring_audit")
    if not isinstance(audit, dict) or not audit.get("scoring_rules_sha256"):
        return {
            "status": "LEGACY_UNCHECKABLE",
            "checks": [],
            "reason": "This historical result predates scoring audit fingerprints.",
        }

    checks = []
    expected_fingerprint = scoring_rules_fingerprint(rules_snapshot.get("scoring_rules"))
    checks.append({
        "name": "scoring_rules_fingerprint",
        "status": "MATCH" if audit.get("scoring_rules_sha256") == expected_fingerprint else "MISMATCH",
    })

    result_engine = result_snapshot.get("scoring_version")
    audit_engine = audit.get("engine_version")
    checks.append({
        "name": "scoring_engine_version",
        "status": "MATCH" if result_engine and result_engine == audit_engine else "MISMATCH",
    })

    snapshot_config_version = rules_snapshot.get("rule_config_version")
    audit_config_version = audit.get("rule_config_version")
    checks.append({
        "name": "rule_config_version",
        "status": "MATCH" if snapshot_config_version == audit_config_version else "MISMATCH",
    })

    passed = all(item["status"] == "MATCH" for item in checks)
    return {
        "status": "VALID" if passed else "MISMATCH",
        "checks": checks,
        "reason": (
            "Recorded audit metadata matches the immutable session snapshot."
            if passed else
            "At least one audit field differs from the immutable session snapshot."
        ),
    }
