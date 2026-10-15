"""Finds a spoken wake phrase at the start of a transcript, tolerating ASR misspellings,
split words ("a sistan") and Turkish suffixes ("asistanım")."""

import unicodedata
from dataclasses import dataclass

from bilge.core.text import folded, similarity

DEFAULT_MINIMUM_SIMILARITY = 0.75
_FILLERS = frozenset(
    {"hey", "hay", "ey", "hu", "selam", "merhaba", "sey", "alo", "ya", "hi", "hello", "ok", "okay", "oh"}
)
_MAX_LEADING_FILLERS = 2
_MAX_TOKENS_PER_PHRASE = 3
# Room for Turkish vocative/possessive endings: "asistanım", "bilgeciğim".
_MAX_SUFFIX_LENGTH = 5
# One misspelled letter in a short word is another common word ("bilge" → "bilgi"),
# so wake phrases this short must be spelled exactly (suffixes still allowed).
_EXACT_MATCH_MAX_LENGTH = 5


@dataclass(frozen=True)
class Match:
    command: str
    similarity: float


class WakePhraseMatcher:
    def __init__(self, phrase: str, minimum_similarity: float = DEFAULT_MINIMUM_SIMILARITY) -> None:
        words = folded(phrase).split()
        # A leading filler inside the configured phrase ("Hey Defne") is optional when spoken.
        leading_count = 0
        while leading_count < len(words) and words[leading_count] in _FILLERS:
            leading_count += 1
        core = words[leading_count:]
        self._phrase_fillers = frozenset(words[:leading_count])
        self._phrase_key = "".join(core or words)
        self.minimum_similarity = 1.0 if len(self._phrase_key) <= _EXACT_MATCH_MAX_LENGTH else minimum_similarity

    def match(self, transcript: str) -> Match | None:
        if not self._phrase_key:
            return None
        tokens = [(original, folded(original)) for original in transcript.split()]
        tokens = [(original, key) for original, key in tokens if key]

        best_end: int | None = None
        best_similarity = 0.0
        for start in range(min(_MAX_LEADING_FILLERS, len(tokens)) + 1):
            if start > 0 and not self._is_filler(tokens[start - 1][1]):
                break
            for length in range(1, _MAX_TOKENS_PER_PHRASE + 1):
                if start + length > len(tokens):
                    break
                candidate = "".join(key for _, key in tokens[start : start + length])
                score = self._score(candidate)
                if score >= self.minimum_similarity and score > best_similarity:
                    best_end, best_similarity = start + length, score
        if best_end is None:
            return None
        command = " ".join(original for original, _ in tokens[best_end:])
        return Match(command=_trim_leading_punctuation(command), similarity=best_similarity)

    def _is_filler(self, key: str) -> bool:
        return key in _FILLERS or key in self._phrase_fillers

    def _score(self, candidate: str) -> float:
        best = similarity(candidate, self._phrase_key)
        extra = len(candidate) - len(self._phrase_key)
        if 1 <= extra <= _MAX_SUFFIX_LENGTH:
            best = max(best, similarity(candidate[: len(self._phrase_key)], self._phrase_key))
        return best


def _trim_leading_punctuation(text: str) -> str:
    index = 0
    while index < len(text) and (text[index].isspace() or unicodedata.category(text[index]).startswith("P")):
        index += 1
    return text[index:]
