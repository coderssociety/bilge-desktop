"""Turns one dictated utterance into the text to type after what was typed before: spoken
punctuation becomes marks, sentences start with a capital, and pieces are spaced like prose."""

from bilge.core.language import AssistantLanguage
from bilge.core.text import folded

# Longest phrases first, so "noktalı virgül" is not read as "nokta" + "lı virgül".
_TURKISH_MARKS: tuple[tuple[str, str], ...] = (
    ("noktali virgul", ";"), ("soru isareti", "?"), ("unlem isareti", "!"), ("iki nokta", ":"), ("uc nokta", "…"),
    ("tirnak ac", "“"), ("tirnak kapat", "”"), ("parantez ac", "("), ("parantez kapat", ")"),
    ("virgul", ","), ("nokta", "."), ("unlem", "!"), ("tire", "-"),
)  # fmt: skip
_ENGLISH_MARKS: tuple[tuple[str, str], ...] = (
    ("question mark", "?"), ("exclamation mark", "!"), ("exclamation point", "!"), ("full stop", "."),
    ("open quote", "“"), ("close quote", "”"), ("end quote", "”"), ("open parenthesis", "("),
    ("close parenthesis", ")"), ("semicolon", ";"), ("colon", ":"), ("ellipsis", "…"), ("comma", ","),
    ("period", "."), ("dash", "-"), ("hyphen", "-"),
)  # fmt: skip
_ATTACHES_LEFT = frozenset({",", ".", "?", "!", ":", ";", "…", "”", ")"})
_ATTACHES_RIGHT = frozenset({"“", "("})
_SENTENCE_ENDS = frozenset({".", "?", "!", "…", "\n"})


def format(spoken: str, after: str | None, language: AssistantLanguage = AssistantLanguage.TURKISH) -> str:
    pieces = _tokens(spoken, _ENGLISH_MARKS if language is AssistantLanguage.ENGLISH else _TURKISH_MARKS)
    output = ""
    pending_space = False
    for piece in pieces:
        if piece not in _ATTACHES_LEFT and pending_space:
            output += " "
        output += piece
        pending_space = piece not in _ATTACHES_RIGHT
    output = output.replace("“", '"').replace("”", '"')
    if not output:
        return ""
    first = output[0]
    starts_sentence = after is None or not after or after[-1] in _SENTENCE_ENDS
    if starts_sentence:
        output = _uppercased(first, language) + output[1:]
    needs_space = after is not None and after != "" and not after.endswith(("\n", " "))
    return (" " if needs_space and first not in _ATTACHES_LEFT else "") + output


def _uppercased(text: str, language: AssistantLanguage) -> str:
    if language is AssistantLanguage.TURKISH:
        text = text.replace("i", "İ").replace("ı", "I")
    return text.upper()


def _tokens(spoken: str, marks: tuple[tuple[str, str], ...]) -> list[str]:
    """Words and marks, with spoken punctuation replaced."""
    words = spoken.split()
    result: list[str] = []
    index = 0
    while index < len(words):
        found = _mark(index, words, marks)
        if found is None:
            result.append(words[index])
            index += 1
        else:
            length, mark = found
            result.append(mark)
            index += length
    return result


def _mark(index: int, words: list[str], marks: tuple[tuple[str, str], ...]) -> tuple[int, str] | None:
    for phrase, mark in marks:
        parts = phrase.split(" ")
        if index + len(parts) > len(words):
            continue
        if [folded(word) for word in words[index : index + len(parts)]] == parts:
            return len(parts), mark
    return None
