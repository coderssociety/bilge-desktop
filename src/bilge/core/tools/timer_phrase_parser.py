"""Deterministically reads "20:00" or "1 saat 15 dakika" from a command that already went through
turkish_number_parser and turkish_time_of_day. Used to override the model's guesses for these values."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Result:
    hour: int | None
    minute: int | None
    duration_seconds: int | None


_CLOCK = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
_UNITS: tuple[tuple[re.Pattern[str], float], ...] = (
    (re.compile(r"(\d+)(\s+buçuk)?\s+saat"), 3600),
    (re.compile(r"(\d+)(\s+buçuk)?\s+dakika"), 60),
    (re.compile(r"(\d+)(\s+buçuk)?\s+saniye"), 1),
)
_FRACTIONS_OF_HOUR: tuple[tuple[re.Pattern[str], float], ...] = (
    (re.compile(r"(?<![^\W\d_])yarım\s+saat", re.IGNORECASE), 1800),
    (re.compile(r"(?<![^\W\d_])çeyrek\s+saat", re.IGNORECASE), 900),
)


def parse(text: str) -> Result | None:
    clock = _CLOCK.search(text)
    if clock is not None:
        return Result(hour=int(clock.group(1)), minute=int(clock.group(2)), duration_seconds=None)
    total = 0.0
    for pattern, seconds in _UNITS:
        for match in pattern.finditer(text):
            half = 0.5 if match.group(2) is not None else 0
            total += (float(match.group(1)) + half) * seconds
    for pattern, seconds in _FRACTIONS_OF_HOUR:
        if pattern.search(text):
            total += seconds
    return Result(hour=None, minute=None, duration_seconds=int(total)) if total > 0 else None
