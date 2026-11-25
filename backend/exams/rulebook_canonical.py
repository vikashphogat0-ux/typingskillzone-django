"""Canonical rulebook profiles: one record per exam, aliases for every source entry.

Pure Python (no Django import) so the rules are testable on their own.

- All 161 source entries remain independent, addressable profile records.
- Profiles may share an exam name, but their source profile_id and settings are never merged.
- Explicit fields from the rulebook specification are applied after merging.
- Hedged wording ("typically", "historically", ...) is kept as a caveat, and the constraint it
  describes is marked not enforced.
- Every canonical profile is source-compiled and practice-only until its notice is verified.
"""
import re

RAW_EXPECTED = 161
CANONICAL_EXPECTED = 161
HEDGE = re.compile(r"\b(typically|historically|recent court sittings?|third-party|uncertain|generally|usually|commonly|reportedly|often|likely)\b", re.I)


def clean_name(name):
    text = (name or "").strip()
    for _ in range(3):
        text = re.sub(r"^\d+\.\s*", "", text).strip()
        text = text.lstrip(".").strip()
    return re.sub(r"\s+", " ", text)


def _key(name):
    return re.sub(r"[^a-z0-9]", "", clean_name(name).lower())


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", clean_name(name).lower()).strip("-")


def _override(name):
    """Explicit fields from the rulebook specification, keyed by cleaned name."""
    n = clean_name(name)
    low = n.lower()
    if low.startswith("mp high court jabalpur"):
        return {"evaluation_mode": "qualifying",
                "max_error_percent": {"range": [5, 10], "configurable_by_admin": True, "enforced": False}}
    if low.startswith("rajasthan hc steno"):
        return {"backspace_mode": "allowed", "clipboard_allowed": False}
    if n.startswith("MP-CPCT"):
        if "english" in low:
            return {"min_net_words_required": 450, "passage_target_words": {"min": 550, "max": 600}}
        return {"min_net_words_required": 300, "passage_target_words": {"min": 450, "max": 500}}
    if low.startswith("bombay high court"):
        return {"target_strokes": 2000, "passage_buffer_strokes": 2800}
    return {}


def canonicalize(profiles):
    """Preserve every source entry as an independent selectable profile."""
    canonical = []
    seen_ids = set()
    for index, profile in enumerate(profiles, start=1):
        name = clean_name(profile.get("name") or profile.get("source_heading"))
        source_id = str(profile.get("profile_id") or "").strip()
        if not source_id:
            raise ValueError(f"Source profile at position {index} has no profile_id.")
        if source_id in seen_ids:
            raise ValueError(f"Duplicate source profile_id: {source_id}")
        seen_ids.add(source_id)
        lines = list(profile.get("source_text") or [])
        caveats = [line for line in lines if HEDGE.search(line)]
        record = {
            "profile_id": source_id,
            "number": profile.get("number", index),
            "name": name,
            "source_heading": profile.get("source_heading") or name,
            "source_text": lines,
            "aliases": [],
            "merged_source_count": 1,
            "verification_status": "source-compiled",
            "exam_mode": "practice_only",
            "caveats": caveats,
            "hedged_constraints_enforced": False,
        }
        record.update(_override(name))
        canonical.append(record)
    return canonical

def alias_index(canonical):
    index = {}
    for record in canonical:
        index[record["profile_id"]] = record
        for alias in record["aliases"]:
            index[alias] = record
    return index


def with_internal_rulebook_basis(scoring_rules):
    """Mark scoring rules as internally verified from the master rulebook (not an official notice)."""
    updated = dict(scoring_rules or {})
    updated["rulebook_verification"] = "internal"
    return updated
