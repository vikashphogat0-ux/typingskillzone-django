"""Pure validation contract for exam-rule provenance.

This module deliberately does not persist evidence or infer domain verification
from the legacy profile-level verification flag. It defines the contract that
future admin editing and publication workflows must satisfy.
"""
from datetime import date
from urllib.parse import urlsplit


DOMAIN_EVIDENCE_SCHEMA_VERSION = 1

SPECIFICATION_DOMAINS = (
    "identity",
    "timing",
    "passage",
    "input_policy",
    "scoring",
    "qualification",
    "presentation",
)

DOMAIN_STATUSES = ("UNVERIFIED", "PARTIAL", "VERIFIED")


def _valid_https_url(value):
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlsplit(value.strip())
    return parsed.scheme == "https" and bool(parsed.netloc)


def _valid_date(value):
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def validate_domain_evidence(evidence):
    """Validate a domain->evidence mapping and return normalized data/errors.

    A VERIFIED domain needs at least one authoritative HTTPS reference with a
    title, exact page/clause locator, checked date, and explicit supported
    claims. PARTIAL needs at least one usable reference. UNVERIFIED may be empty.
    Unknown domains and malformed structures are rejected.
    """
    errors = []
    if not isinstance(evidence, dict):
        return {}, ["Evidence must be an object keyed by specification domain."]

    # Accept the normalized persisted envelope as well as the compact admin form.
    if "domains" in evidence:
        if evidence.get("schema_version") != DOMAIN_EVIDENCE_SCHEMA_VERSION:
            errors.append("Unsupported domain evidence schema version.")
        evidence = evidence.get("domains")
        if not isinstance(evidence, dict):
            return {}, errors + ["The domains value must be an object."]

    unknown = sorted(set(evidence) - set(SPECIFICATION_DOMAINS))
    if unknown:
        errors.append("Unknown specification domains: " + ", ".join(unknown))

    normalized = {}
    for domain in SPECIFICATION_DOMAINS:
        item = evidence.get(domain)
        if item is None:
            normalized[domain] = {"status": "UNVERIFIED", "references": []}
            continue
        if not isinstance(item, dict):
            errors.append(f"{domain}: evidence entry must be an object.")
            continue

        status = item.get("status", "UNVERIFIED")
        references = item.get("references", [])
        if status not in DOMAIN_STATUSES:
            errors.append(f"{domain}: unsupported status {status!r}.")
            continue
        if not isinstance(references, list):
            errors.append(f"{domain}: references must be a list.")
            continue

        clean_references = []
        for index, reference in enumerate(references):
            prefix = f"{domain}.references[{index}]"
            if not isinstance(reference, dict):
                errors.append(f"{prefix}: reference must be an object.")
                continue
            url = reference.get("url")
            title = reference.get("title")
            locator = reference.get("locator")
            checked_at = reference.get("checked_at")
            claims = reference.get("claims")
            if not _valid_https_url(url):
                errors.append(f"{prefix}: a valid HTTPS source URL is required.")
            if not isinstance(title, str) or not title.strip():
                errors.append(f"{prefix}: source title is required.")
            if not isinstance(locator, str) or not locator.strip():
                errors.append(f"{prefix}: exact page, section, or clause locator is required.")
            if not _valid_date(checked_at):
                errors.append(f"{prefix}: checked_at must be an ISO date (YYYY-MM-DD).")
            if not isinstance(claims, list) or not claims or any(
                not isinstance(claim, str) or not claim.strip() for claim in claims
            ):
                errors.append(f"{prefix}: at least one explicit supported claim is required.")
            clean_references.append({
                "url": url.strip() if isinstance(url, str) else url,
                "title": title.strip() if isinstance(title, str) else title,
                "locator": locator.strip() if isinstance(locator, str) else locator,
                "checked_at": checked_at,
                "claims": [claim.strip() for claim in claims if isinstance(claim, str)]
                if isinstance(claims, list) else claims,
            })

        if status == "VERIFIED" and not clean_references:
            errors.append(f"{domain}: VERIFIED requires at least one evidence reference.")
        if status == "PARTIAL" and not clean_references:
            errors.append(f"{domain}: PARTIAL requires at least one evidence reference.")

        normalized[domain] = {
            "status": status,
            "references": clean_references,
        }

    return {
        "schema_version": DOMAIN_EVIDENCE_SCHEMA_VERSION,
        "domains": normalized,
    }, errors
