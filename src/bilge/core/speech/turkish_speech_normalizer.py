"""Rewrites model output into plain spoken Turkish before TTS: digits, times, dates, symbols and markdown."""

import re
from collections.abc import Callable

from bilge.core.speech import spoken_text
from bilge.core.speech.turkish_number_words import MONTH_NAMES, cardinal, digits_preserving_leading_zeros

_SUFFIX = r"(?:['’]([^\W\d_]+))?"
_MAX_READABLE_DIGITS = 15

_DATE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b" + _SUFFIX)
_TIME = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b" + _SUFFIX)
_PERCENT = re.compile(r"%\s?(?=\d)")
_DEGREES = re.compile(r"\s?°\s?C?\b|\s?°")
_LIRA = re.compile(r"\s?₺|\s?\bTL\b")
_DOLLAR = re.compile(r"\s?\$")
_EURO = re.compile(r"\s?€")
_THOUSANDS = re.compile(r"\b\d{1,3}(?:\.\d{3})+\b")
_DECIMAL = re.compile(r"\b(\d+),(\d+)\b" + _SUFFIX)
_INTEGER = re.compile(r"\b(\d+)\b" + _SUFFIX)
_REPEATED_SPACES = re.compile(r"[ \t]{2,}")


def normalize(text: str) -> str:
    result = spoken_text.without_markup(text)
    result = _replace_dates(result)
    result = _replace_times(result)
    result = _PERCENT.sub("yüzde ", result)
    result = _DEGREES.sub(" derece", result)
    result = _LIRA.sub(" lira", result)
    result = _DOLLAR.sub(" dolar", result)
    result = _EURO.sub(" avro", result)
    result = _THOUSANDS.sub(lambda match: match[0].replace(".", ""), result)
    result = _replace(_DECIMAL, result, _read_decimal)
    result = _replace(_INTEGER, result, _read_integer_with_suffix)
    return _REPEATED_SPACES.sub(" ", result).strip()


def _replace_dates(text: str) -> str:
    def read(groups: tuple[str | None, ...]) -> str | None:
        day, month, year = (_ascii_int(group) for group in groups[:3])
        if day is None or month is None or year is None or not 1 <= day <= 31 or not 1 <= month <= 12:
            return None
        return " ".join((cardinal(day), MONTH_NAMES[month - 1], cardinal(year))) + (groups[3] or "")

    return _replace(_DATE, text, read)


def _replace_times(text: str) -> str:
    def read(groups: tuple[str | None, ...]) -> str | None:
        hour, minutes = _ascii_int(groups[0]), groups[1]
        if hour is None or minutes is None:
            return None
        minute_words = "" if minutes == "00" else " " + digits_preserving_leading_zeros(minutes)
        return cardinal(hour) + minute_words + (groups[2] or "")

    return _replace(_TIME, text, read)


def _read_decimal(groups: tuple[str | None, ...]) -> str | None:
    # Swift crashes on a whole part this long; here it falls through and is read digit by digit.
    if len(groups[0] or "") > _MAX_READABLE_DIGITS:
        return None
    whole, fraction = _ascii_int(groups[0]), groups[1]
    if whole is None or fraction is None:
        return None
    return cardinal(whole) + " virgül " + digits_preserving_leading_zeros(fraction) + (groups[2] or "")


def _read_integer_with_suffix(groups: tuple[str | None, ...]) -> str | None:
    digits = groups[0]
    if digits is None:
        return None
    return _read_integer(digits) + (groups[1] or "")


def _read_integer(digits: str) -> str:
    value = None if len(digits) > _MAX_READABLE_DIGITS else _ascii_int(digits)
    if value is None:
        return " ".join(cardinal(_ascii_int(digit) or 0) for digit in digits)
    return cardinal(value)


def _ascii_int(digits: str | None) -> int | None:
    """Swift's Int(_:) parses ASCII digits only, while \\d also matches other scripts' digits."""
    if digits is None or not digits.isascii() or not digits.isdigit():
        return None
    return int(digits)


def _replace(pattern: re.Pattern[str], text: str, transform: Callable[[tuple[str | None, ...]], str | None]) -> str:
    """Replaces each match with `transform(groups)`; returning None keeps the original match."""

    def substitute(match: re.Match[str]) -> str:
        replacement = transform(match.groups())
        return match[0] if replacement is None else replacement

    return pattern.sub(substitute, text)
