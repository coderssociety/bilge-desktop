"""English counterparts of relative_day_parser and timer_phrase_parser: "tomorrow", "next Friday",
"in 3 days"; "10:30", "7 pm", "at ten", "noon"; "in 10 minutes", "half an hour"."""

import re
from datetime import datetime, tzinfo

from bilge.core.tools.relative_day_parser import calendar_weekday
from bilge.core.tools.timer_phrase_parser import Result

_UNITS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "a": 1, "an": 1,
}  # fmt: skip
_TEENS: dict[str, int] = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}  # fmt: skip
_TENS: dict[str, int] = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}  # fmt: skip
# Calendar weekday numbers (1 = Sunday).
_WEEKDAYS: dict[str, int] = {
    "sunday": 1, "monday": 2, "tuesday": 3, "wednesday": 4, "thursday": 5, "friday": 6, "saturday": 7,
}  # fmt: skip
_DURATION_UNITS: dict[str, int] = {
    "hour": 3600, "hours": 3600,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60,
    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
}  # fmt: skip
PART_OF_DAY_WORDS = frozenset(["morning", "afternoon", "evening", "night", "tonight", "noon", "midnight"])

_CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})\s*(?:([ap])\.?\s*m\b)?")
_HOUR_WITH_MERIDIEM = re.compile(r"(?:^|[^\d:])(\d{1,2})\s*([ap])\.?\s*m\b")


def day_offset(text: str, now: datetime, tz: tzinfo | None = None) -> int | None:
    words = _words(text)
    if "in" in words:
        index = words.index("in")
        if index + 2 < len(words) and words[index + 2] in ("day", "days"):
            count = _number(words[index + 1])
            if count is not None:
                return count
    for index, word in enumerate(words):
        target = _WEEKDAYS.get(word)
        if target is None:
            continue
        today = calendar_weekday(now.astimezone(tz) if tz is not None else now)
        offset = (target - today + 7) % 7 or 7
        next_week = index > 0 and words[index - 1] == "next" and offset < 7
        return offset + 7 if next_week else offset
    if _contains(words, ["day", "after", "tomorrow"]):
        return 2
    if "tomorrow" in words:
        return 1
    if "today" in words or "tonight" in words:
        return 0
    return None


def parse(text: str, appointment: bool = True) -> Result | None:
    """A clock time or a duration. For appointments a bare "at 3" means 15:00; for alarms
    ("wake me up at 6") the hour is taken as said."""
    clock = _clock_time(text, appointment)
    if clock is not None:
        return Result(hour=clock[0], minute=clock[1], duration_seconds=None)
    seconds = _duration(_words(text))
    return Result(hour=None, minute=None, duration_seconds=seconds) if seconds > 0 else None


def _clock_time(text: str, appointment: bool) -> tuple[int, int] | None:
    lowered = text.lower()
    match = _CLOCK.search(lowered)
    if match is not None:
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour < 24 and minute < 60:
            return _adjusted(hour, match.group(3)), minute
    match = _HOUR_WITH_MERIDIEM.search(lowered)
    if match is not None and 1 <= int(match.group(1)) <= 12:
        return _adjusted(int(match.group(1)), match.group(2)), 0
    words = _words(text)
    if "noon" in words or "midday" in words:
        return 12, 0
    if "midnight" in words:
        return 0, 0
    hour = _bare_hour(words)
    if hour is None:
        return None
    evening = "evening" in words or "tonight" in words or "night" in words
    afternoon = (appointment and hour < 7) or (evening and hour < 12)
    return (hour + 12 if afternoon else hour), 0


def _bare_hour(words: list[str]) -> int | None:
    # "at ten", "at 7": afternoon for 1-6, as appointments rarely start before 7 in the morning.
    # Only a real number counts: "at a meeting" is not one o'clock.
    for index, word in enumerate(words):
        if word != "at" or index + 1 >= len(words) or words[index + 1] in ("a", "an"):
            continue
        hour = _number(words[index + 1])
        if hour is None or not 1 <= hour <= 12:
            continue
        if index + 2 < len(words) and words[index + 2] in ("minute", "minutes", "percent"):
            continue
        return hour
    return None


def _adjusted(hour: int, meridiem: str | None) -> int:
    if meridiem == "p":
        return hour + 12 if hour < 12 else hour
    if meridiem == "a":
        return 0 if hour == 12 else hour
    return hour


def _duration(words: list[str]) -> int:
    total = 0
    for index, word in enumerate(words):
        unit = _DURATION_UNITS.get(word, 0)
        if unit == 0 or index == 0:
            continue
        if words[index - 1] == "an" and index > 1 and words[index - 2] == "half":
            total += unit // 2
        else:
            count = _number_ending_at(index - 1, words)
            if count is not None:
                total += count * unit
        # "an hour and a half"
        if words[index + 1 : index + 4] == ["and", "a", "half"]:
            total += unit // 2
    if not _contains(words, ["half", "an", "hour"]) and _contains(words, ["half", "hour"]):
        total += 1800
    return total


def _number_ending_at(index: int, words: list[str]) -> int | None:
    """ "25", "twenty five", "ninety", "an" ending at `index`."""
    word = words[index]
    value = _int(word)
    if value is None:
        value = _TEENS.get(word, _TENS.get(word))
    if value is not None:
        return value
    unit = _UNITS.get(word)
    if unit is None:
        return None
    if index > 0 and words[index - 1] in _TENS:
        return _TENS[words[index - 1]] + unit
    return unit


def _number(word: str) -> int | None:
    value = _int(word)
    if value is not None:
        return value
    return _UNITS.get(word, _TEENS.get(word, _TENS.get(word)))


def _int(word: str) -> int | None:
    return int(word) if word.isascii() and word.isdigit() else None


def _words(text: str) -> list[str]:
    mapped = "".join(ch if ch.isalpha() or ch.isnumeric() else " " for ch in text.lower())
    return mapped.split()


def _contains(words: list[str], phrase: list[str]) -> bool:
    return any(words[start : start + len(phrase)] == phrase for start in range(len(words) - len(phrase) + 1))
