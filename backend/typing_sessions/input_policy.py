"""Server-verifiable checks for submitted text input policies.

Keyboard events such as Backspace, Delete, paste and arrow navigation cannot
be reconstructed reliably from a final textarea value. Those controls remain
browser-side deterrents and are never represented as server-verified.
"""
from django.core.exceptions import ValidationError


def audit_submitted_text(*, typed_text, rules):
    """Reject explicit text-level violations and report unverifiable controls."""
    policy = rules.get("input_policy") or {}
    enter_behavior = policy.get("enter_behavior", "UNSPECIFIED")
    space_behavior = policy.get("space_behavior", "UNSPECIFIED")
    tab_behavior = policy.get("tab_behavior", "UNSPECIFIED")

    checks = {
        "newline": "NOT_SPECIFIED",
        "space": "NOT_SPECIFIED",
        "tab": "NOT_SPECIFIED",
    }
    violations = []

    if enter_behavior in {"DISABLED", "COMMIT_WORD"}:
        checks["newline"] = "REJECTED" if "\n" in typed_text or "\r" in typed_text else "PASSED"
        if "\n" in typed_text or "\r" in typed_text:
            violations.append("Newline characters are not permitted by the configured Enter policy.")
    elif enter_behavior == "NEW_LINE":
        checks["newline"] = "PASSED"

    if space_behavior == "DISABLED":
        checks["space"] = "REJECTED" if " " in typed_text else "PASSED"
        if " " in typed_text:
            violations.append("Space characters are not permitted by the configured Space policy.")
    elif space_behavior in {"NORMAL", "COMMIT_WORD"}:
        checks["space"] = "PASSED"

    if tab_behavior == "DISABLED":
        checks["tab"] = "REJECTED" if "\t" in typed_text else "PASSED"
        if "\t" in typed_text:
            violations.append("Tab characters are not permitted by the configured Tab policy.")
    elif tab_behavior in {"INSERT_TAB", "INSERT_SPACES"}:
        checks["tab"] = "PASSED"

    client_controls = {
        "backspace": {
            "configured": policy.get("backspace"),
            "verification": "CLIENT_SIDE_ONLY_UNVERIFIED",
        },
        "delete": {
            "configured": policy.get("delete"),
            "verification": "CLIENT_SIDE_ONLY_UNVERIFIED",
        },
        "arrow_navigation": {
            "configured": policy.get("arrow_navigation"),
            "verification": "CLIENT_SIDE_ONLY_UNVERIFIED",
        },
        "paste": {
            "configured": policy.get("paste"),
            "verification": "CLIENT_SIDE_ONLY_UNVERIFIED",
        },
        "copy": {
            "configured": policy.get("copy"),
            "verification": "CLIENT_SIDE_ONLY_UNVERIFIED",
        },
        "cut": {
            "configured": policy.get("cut"),
            "verification": "CLIENT_SIDE_ONLY_UNVERIFIED",
        },
    }
    audit = {
        "status": "REJECTED" if violations else "TEXT_POLICY_VALIDATED",
        "checks": checks,
        "violations": violations,
        "client_controls": client_controls,
        "server_verification_scope": "SUBMITTED_TEXT_ONLY",
    }
    if violations:
        raise ValidationError(violations)
    return audit
