"""Word-aligned, escaped-by-template comparison for completed typing attempts."""
from difflib import SequenceMatcher
import re
import unicodedata


def _tokens(text):
    return re.findall(r"\s+|\S+", text or "")


def build_word_comparison(reference, typed):
    """Return aligned display tokens; word-level differences are highlighted once."""
    reference_tokens = _tokens(unicodedata.normalize("NFC", reference or ""))
    typed_tokens = _tokens(unicodedata.normalize("NFC", typed or ""))

    reference_word_indexes = [i for i, token in enumerate(reference_tokens) if not token.isspace()]
    typed_word_indexes = [i for i, token in enumerate(typed_tokens) if not token.isspace()]
    reference_words = [reference_tokens[i] for i in reference_word_indexes]
    typed_words = [typed_tokens[i] for i in typed_word_indexes]

    reference_status = ["plain"] * len(reference_tokens)
    typed_status = ["plain"] * len(typed_tokens)
    matcher = SequenceMatcher(a=reference_words, b=typed_words, autojunk=False)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for ref_index, typed_index in zip(
                reference_word_indexes[i1:i2], typed_word_indexes[j1:j2]
            ):
                exact = reference_tokens[ref_index] == typed_tokens[typed_index]
                reference_status[ref_index] = "correct" if exact else "incorrect"
                typed_status[typed_index] = "correct" if exact else "incorrect"
        elif tag == "delete":
            for ref_index in reference_word_indexes[i1:i2]:
                reference_status[ref_index] = "omitted"
        elif tag == "insert":
            for typed_index in typed_word_indexes[j1:j2]:
                typed_status[typed_index] = "added"
        elif tag == "replace":
            expected_indexes = reference_word_indexes[i1:i2]
            actual_indexes = typed_word_indexes[j1:j2]
            paired = min(len(expected_indexes), len(actual_indexes))
            for offset in range(paired):
                ref_index = expected_indexes[offset]
                typed_index = actual_indexes[offset]
                expected_word = reference_tokens[ref_index]
                actual_word = typed_tokens[typed_index]
                similarity = SequenceMatcher(
                    None, expected_word.casefold(), actual_word.casefold(),
                    autojunk=False,
                ).ratio()
                # Similar spellings are typos. A substantially different
                # Latin word is better represented as an omission plus an
                # extra word. Devanagari replacements remain paired as
                # incorrect words even when their code-point lengths differ;
                # character-level similarity is not a reliable word-alignment
                # signal for Hindi.
                same_length = len(expected_word) == len(actual_word)
                contains_devanagari = any(
                    "DEVANAGARI" in unicodedata.name(char, "")
                    for char in expected_word + actual_word
                )
                likely_typo = (
                    similarity >= 0.60 or same_length or contains_devanagari
                )
                if likely_typo:
                    reference_status[ref_index] = "incorrect"
                    typed_status[typed_index] = "incorrect"
                else:
                    reference_status[ref_index] = "omitted"
                    typed_status[typed_index] = "added"
            for ref_index in expected_indexes[paired:]:
                reference_status[ref_index] = "omitted"
            for typed_index in actual_indexes[paired:]:
                typed_status[typed_index] = "added"

    return {
        "reference": [
            {"text": token, "status": reference_status[index]}
            for index, token in enumerate(reference_tokens)
        ],
        "typed": [
            {"text": token, "status": typed_status[index]}
            for index, token in enumerate(typed_tokens)
        ],
    }
