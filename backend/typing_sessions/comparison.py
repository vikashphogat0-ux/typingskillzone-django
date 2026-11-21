"""Word-aligned, escaped-by-template comparison for completed typing attempts."""
from difflib import SequenceMatcher
import re
import unicodedata


def _tokens(text):
    return re.findall(r"\\s+|\\S+", text or "")


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
                reference_status[expected_indexes[offset]] = "incorrect"
                typed_status[actual_indexes[offset]] = "incorrect"
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
