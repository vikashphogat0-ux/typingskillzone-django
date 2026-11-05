"""Validation for explicitly versioned exam scoring configuration."""


def validate_mistake_classification_config(config):
    """Return validation errors for the supported exact word-pair schema."""
    errors = []
    if not isinstance(config, dict):
        return ["Mistake classification must be a JSON object."]
    if config.get("version") != 1:
        errors.append("Mistake classification version must be 1.")
    if config.get("unit") != "word":
        errors.append("Mistake classification unit must be 'word'.")
    source_reference = config.get("source_reference")
    if source_reference is not None:
        if not isinstance(source_reference, dict):
            errors.append("Source reference must be an object.")
        else:
            for key in ("url", "title", "locator", "checked_at"):
                if key in source_reference and not isinstance(source_reference[key], str):
                    errors.append(f"Source reference {key} must be text.")
            if source_reference.get("checked_at"):
                from datetime import date
                try:
                    date.fromisoformat(source_reference["checked_at"])
                except ValueError:
                    errors.append("Source reference checked_at must use YYYY-MM-DD.")

    overrides = config.get("overrides")
    if not isinstance(overrides, list):
        errors.append("Mistake classification overrides must be a list.")
        return errors

    seen = set()
    for index, item in enumerate(overrides):
        prefix = f"Override {index + 1}"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        reference = item.get("reference")
        typed = item.get("typed")
        classification = item.get("classification")
        if not isinstance(reference, str) or not isinstance(typed, str):
            errors.append(f"{prefix} reference and typed values must be strings.")
            continue
        if classification not in {"FULL", "HALF", "IGNORED"}:
            errors.append(f"{prefix} classification must be FULL, HALF or IGNORED.")
        key = (reference, typed)
        if key in seen:
            errors.append(f"{prefix} duplicates an earlier reference/typed pair.")
        seen.add(key)
    return errors
