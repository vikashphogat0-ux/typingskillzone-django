"""Word-level grading: alignment of typed words against the passage.

Each typed word is either matched, substituted (spelling error), omitted from the passage,
or inserted as an extra word. A mistake inside one word counts once. Passage words after the
last typed word are untyped and are never counted. The browser highlight uses the same
alignment, so what the student sees highlighted is what is scored.
"""
import re

WORD = re.compile(r"\S+")


def levenshtein(a, b):
    """Number of single-character edits (insert, delete, substitute) turning a into b."""
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def word_alignment(reference_words, typed_words):
    """Longest-common-subsequence alignment. Ops are ("equal"|"delete"|"insert", ref_index, typed_index)."""
    n, m = len(reference_words), len(typed_words)
    table = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if reference_words[i] == typed_words[j]:
                table[i][j] = table[i + 1][j + 1] + 1
            else:
                table[i][j] = max(table[i + 1][j], table[i][j + 1])
    ops = []
    i = j = 0
    while i < n and j < m:
        if reference_words[i] == typed_words[j]:
            ops.append(("equal", i, j))
            i += 1
            j += 1
        elif table[i + 1][j] >= table[i][j + 1]:
            ops.append(("delete", i, j))
            i += 1
        else:
            ops.append(("insert", i, j))
            j += 1
    while i < n:
        ops.append(("delete", i, j))
        i += 1
    while j < m:
        ops.append(("insert", i, j))
        j += 1
    return ops


def grade_words(reference, typed):
    """Grade the typed text against the passage. Returns a dict with counts and per-word details."""
    ref_words = WORD.findall(reference or "")
    typed_words = WORD.findall(typed or "")
    typed_count = len(typed_words)

    blocks, current, correct = [], None, 0
    for kind, i, j in word_alignment(ref_words, typed_words):
        if kind == "equal":
            correct += 1
            if current:
                blocks.append(current)
                current = None
            continue
        if current is None:
            current = {"deletes": [], "inserts": [], "start": j}
        (current["deletes"] if kind == "delete" else current["inserts"]).append(i if kind == "delete" else j)
    if current:
        blocks.append(current)

    substitutions = omissions = insertions = spelling_edits = 0
    pairs_out = []
    for block in blocks:
        inserts = block["inserts"]
        deletes = block["deletes"]
        if not inserts and block["start"] >= typed_count:
            continue  # untyped passage text: not an error
        if inserts and block["start"] + len(inserts) == typed_count:
            deletes = deletes[: len(inserts)]  # passage words after the last typed word are untyped
        paired = min(len(deletes), len(inserts))
        for offset in range(paired):
            reference_index, typed_index = deletes[offset], inserts[offset]
            distance = levenshtein(ref_words[reference_index], typed_words[typed_index])
            substitutions += 1
            spelling_edits += distance
            pairs_out.append(("substitution", reference_index, typed_index, distance))
        for reference_index in deletes[paired:]:
            omissions += 1
            pairs_out.append(("omission", reference_index, None, None))
        for typed_index in inserts[paired:]:
            insertions += 1
            pairs_out.append(("insertion", None, typed_index, None))

    return {
        "errors": substitutions + omissions + insertions,
        "substitutions": substitutions,
        "omissions": omissions,
        "insertions": insertions,
        "spelling_edits": spelling_edits,
        "correct_words": correct,
        "details": pairs_out,
    }
