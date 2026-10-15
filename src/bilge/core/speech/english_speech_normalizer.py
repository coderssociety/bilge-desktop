"""English output for the synthesizer: markup removed and symbols spelled out. The synthesizer reads
English numbers itself, so digits are left alone."""

import re

from bilge.core.speech import spoken_text

_WORDS = (
    (re.compile(r"(?<=\d)\s?%"), " percent"),
    (re.compile(r"\s?°\s?C\b"), " degrees Celsius"),
    (re.compile(r"\s?°\s?F\b"), " degrees Fahrenheit"),
    (re.compile(r"\s?°"), " degrees"),
    (re.compile(r"\s?₺|\s?\bTL\b"), " lira"),
)
_REPEATED_SPACES = re.compile(r"[ \t]{2,}")


def normalize(text: str) -> str:
    result = spoken_text.without_markup(text)
    for pattern, replacement in _WORDS:
        result = pattern.sub(replacement, result)
    return _REPEATED_SPACES.sub(" ", result).strip()
