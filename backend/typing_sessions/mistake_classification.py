
"""Conservative typing mistake classification.

This is a practice-analysis utility, not an official examination
adjudication engine.
"""

import re
import string
from difflib import SequenceMatcher


PUNCTUATION = set(string.punctuation + "।॥،؛؟“”‘’")


def _clean_word(word):
    return "".join(
        char for char in word
        if char not in PUNCTUATION
    ).casefold()


def _is_word_char(char):
    return bool(char) and (char.isalnum() or char == "_")


def classify_typing_mistakes(reference, typed):
    reference = reference or ""
    typed = typed or ""

    categories = {
        "omission": 0,
        "substitution": 0,
        "addition": 0,
        "capitalization": 0,
        "punctuation": 0,
        "internal_spacing": 0,
        "word_spacing": 0,
        "paragraph_breaks": 0,
    }

    # Preserve paragraph structure while comparing word content.
    ref_words = re.findall(r"\S+", reference)
    typed_words = re.findall(r"\S+", typed)

    ref_clean = [_clean_word(word) for word in ref_words]
    typed_clean = [_clean_word(word) for word in typed_words]

    matcher = SequenceMatcher(
        None, ref_clean, typed_clean, autojunk=False
    )

    aligned_pairs = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        expected = ref_words[i1:i2]
        actual = typed_words[j1:j2]

        if tag == "equal":
            aligned_pairs.extend(zip(expected, actual))

        elif tag == "delete":
            categories["omission"] += len(expected)

        elif tag == "insert":
            categories["addition"] += len(actual)

        elif tag == "replace":
            # Detect a word split by an accidental internal space.
            joined_actual = "".join(actual)
            joined_expected = "".join(expected)

            if (
                len(expected) == 1
                and len(actual) > 1
                and _clean_word(joined_actual) == ref_clean[i1]
            ):
                categories["internal_spacing"] += 1
            elif (
                len(actual) == 1
                and len(expected) > 1
                and _clean_word(joined_expected) == typed_clean[j1]
            ):
                categories["internal_spacing"] += 1
            else:
                paired = min(len(expected), len(actual))
                categories["substitution"] += paired
                categories["omission"] += len(expected) - paired
                categories["addition"] += len(actual) - paired

    # Formatting checks on words aligned by content.
    for expected, actual in aligned_pairs:
        if expected != actual:
            if expected.casefold() == actual.casefold():
                categories["capitalization"] += 1

            expected_marks = "".join(
                char for char in expected if char in PUNCTUATION
            )
            actual_marks = "".join(
                char for char in actual if char in PUNCTUATION
            )

            if expected_marks != actual_marks:
                categories["punctuation"] += 1

    # Compare whitespace only when the word sequences align.
    if ref_clean == typed_clean and ref_words:
        ref_spaces = re.findall(r"\s+", reference)
        typed_spaces = re.findall(r"\s+", typed)

        for expected, actual in zip(ref_spaces, typed_spaces):
            if expected == actual:
                continue

            if "\n" in expected or "\n" in actual:
                categories["paragraph_breaks"] += 1
            elif len(expected) != len(actual):
                categories["word_spacing"] += 1

        # Extra or missing whitespace boundaries.
        if len(ref_spaces) != len(typed_spaces):
            categories["word_spacing"] += abs(
                len(ref_spaces) - len(typed_spaces)
            )

    total = sum(categories.values())

    return {
        "categories": categories,
        "total_detected_errors": total,
    }
