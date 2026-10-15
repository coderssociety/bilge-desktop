"""Splits text into sentence-sized pieces so speech can start before the whole reply is synthesized."""

from bilge.core.text import lowercased

DEFAULT_MAX_LENGTH = 160

_TERMINATORS = frozenset(".!?…")
_ABBREVIATIONS = frozenset(
    {
        "dr", "prof", "doç", "av", "sn", "vb", "vs", "örn", "bkz", "no", "st", "cad", "sok", "mah", "apt", "yy",
        "mr", "mrs", "ms", "jr", "sr", "etc", "approx", "ave", "rd", "vol", "fig",
    }
)  # fmt: skip


def split(text: str, max_length: int = DEFAULT_MAX_LENGTH) -> list[str]:
    sentences: list[str] = []
    remainder = text
    while (boundary := first_boundary(remainder, end_counts_as_boundary=True)) is not None:
        sentences.append(remainder[:boundary])
        remainder = remainder[boundary:]
    stripped = (sentence.strip() for sentence in sentences)
    return [part for sentence in stripped if sentence for part in _wrap(sentence, max_length)]


def first_boundary(text: str, end_counts_as_boundary: bool) -> int | None:
    """Index just past the first sentence terminator that is followed by whitespace (or the end, if allowed)."""
    index = 0
    while index < len(text):
        character = text[index]
        if character not in _TERMINATORS:
            index += 1
            continue
        end = index + 1
        while end < len(text) and text[end] in _TERMINATORS:
            end += 1
        at_end = end == len(text)
        is_boundary = (at_end and end_counts_as_boundary) or (not at_end and text[end].isspace())
        if is_boundary and (character != "." or not _ends_with_abbreviation(text[:index])):
            return end
        index = end
    return len(text) if end_counts_as_boundary and text else None


def _ends_with_abbreviation(prefix: str) -> bool:
    words = prefix.split()
    last_word = words[-1] if words else ""
    return lowercased(last_word) in _ABBREVIATIONS


def _wrap(sentence: str, max_length: int) -> list[str]:
    if len(sentence) <= max_length:
        return [sentence]
    parts: list[str] = []
    current = ""
    for clause in sentence.split(", "):
        candidate = clause if not current else current + ", " + clause
        # +1 leaves room for the comma kept at the end of a non-final part.
        if not current or len(candidate) + 1 <= max_length:
            current = candidate
        else:
            parts.append(current + ",")
            current = clause
    if current:
        parts.append(current)
    return [piece for part in parts for piece in _hard_wrap(part, max_length)]


def _hard_wrap(text: str, max_length: int) -> list[str]:
    if len(text) <= max_length:
        return [text]
    parts: list[str] = []
    current = ""
    for word in (word for word in text.split(" ") if word):
        candidate = word if not current else current + " " + word
        if len(candidate) > max_length and current:
            parts.append(current)
            current = word
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


class SentenceAccumulator:
    """Collects streamed text fragments and releases whole sentences as soon as they are unambiguous."""

    def __init__(self, max_length: int = DEFAULT_MAX_LENGTH) -> None:
        self._buffer = ""
        self._max_length = max_length

    def append(self, fragment: str) -> list[str]:
        remainder = self._buffer + fragment
        completed: list[str] = []
        while (boundary := first_boundary(remainder, end_counts_as_boundary=False)) is not None:
            completed.append(remainder[:boundary])
            remainder = remainder[boundary:]
        self._buffer = remainder
        return [sentence for text in completed for sentence in split(text, self._max_length)]

    def finish(self) -> list[str]:
        buffer, self._buffer = self._buffer, ""
        return split(buffer, self._max_length)
