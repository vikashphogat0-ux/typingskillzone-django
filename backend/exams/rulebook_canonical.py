"""Canonical rulebook profiles: one record per exam, aliases for every source entry.

Pure Python (no Django import) so the rules are testable on their own.

- 161 source entries are grouped by cleaned exam name. Groups with more than one entry are merged.
- Every source profile_id stays as an alias of its canonical profile.
- Explicit fields from the rulebook specification are applied after merging.
- Hedged wording ("typically", "historically", ...) is kept as a caveat, and the constraint it
  describes is marked not enforced.
- Every canonical profile is source-compiled and practice-only until its notice is verified.
"""
import re

RAW_EXPECTED = 161
CANONICAL_EXPECTED = 156
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
    """Merge source profiles into canonical profiles. Input and output keep the importer's shape."""
    groups = {}
    order = []
    for profile in profiles:
        key = _key(profile.get("name") or profile.get("source_heading") or "")
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(profile)

    canonical = []
    for index, key in enumerate(order, start=1):
        members = groups[key]
        name = clean_name(members[0].get("name") or members[0].get("source_heading"))
        lines = []
        for member in members:
            for line in member.get("source_text") or []:
                if line not in lines:
                    lines.append(line)
        caveats = [line for line in lines if HEDGE.search(line)]
        record = {
            "profile_id": _slug(name),
            "number": index,
            "name": name,
            "source_heading": name,
            "source_text": lines,
            "aliases": [m.get("profile_id") for m in members if m.get("profile_id")],
            "merged_source_count": len(members),
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
