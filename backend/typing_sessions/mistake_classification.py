
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



def _attempted_reference_prefix(reference, typed_words, typed):
    """Keep internal omissions but exclude reference words after the final typed word."""
    reference = reference or ""
    reference_spans = list(re.finditer(r"\S+", reference))
    if not typed_words or not reference_spans:
        return ""

    reference_words = [match.group(0) for match in reference_spans]
    reference_clean = [_clean_word(word) for word in reference_words]
    typed_clean = [_clean_word(word) for word in typed_words]
    matcher = SequenceMatcher(None, reference_clean, typed_clean, autojunk=False)
    # Do not let a final typo absorb the entire untyped reference suffix.
    blocks = [block for block in matcher.get_matching_blocks() if block.size]
    if blocks:
        last_block = max(blocks, key=lambda block: block.b + block.size)
        matched_reference_end = max(block.a + block.size for block in blocks)
        matched_typed_end = last_block.b + last_block.size
        trailing_typed_words = len(typed_words) - matched_typed_end
        reached_reference_words = min(
            len(reference_words),
            matched_reference_end + trailing_typed_words,
        )
    else:
        reached_reference_words = min(len(reference_words), len(typed_words))
    if reached_reference_words <= 0:
        return ""
    end = reference_spans[reached_reference_words - 1].end()
    if typed and typed[-1].isspace():
        trailing = re.match(r"\s*", reference[end:])
        if trailing:
            end += len(trailing.group(0))
    return reference[:end]


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

    # Compare only words the learner reached; the remaining reference
    # suffix is pending text, not a series of omissions.
    typed_words = re.findall(r"\S+", typed)
    reference = _attempted_reference_prefix(reference, typed_words, typed)
    ref_words = re.findall(r"\S+", reference)

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
            # Compare letters without punctuation so a case error is still counted when the
            # same word also has a punctuation error.
            expected_letters = "".join(char for char in expected if char not in PUNCTUATION)
            actual_letters = "".join(char for char in actual if char not in PUNCTUATION)
            if (
                expected_letters != actual_letters
                and expected_letters.casefold() == actual_letters.casefold()
            ):
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

    # Categories describe detected defect types and may overlap within one
    # word. The penalty unit is the affected word, counted only once.
    ref_words_for_count = re.findall(r"\\S+", _attempted_reference_prefix(reference, typed_words, typed))
    word_matcher = SequenceMatcher(
        None,
        ref_words_for_count,
        typed_words,
        autojunk=False,
    )
    total = 0
    for tag, i1, i2, j1, j2 in word_matcher.get_opcodes():
        if tag != "equal":
            total += max(i2 - i1, j2 - j1)

    return {
        "categories": categories,
        "total_detected_errors": total,
    }
