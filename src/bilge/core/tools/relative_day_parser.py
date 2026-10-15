"""Reads which day a Turkish request refers to ("yarın", "cuma", "haftaya çarşamba", "3 gün sonra")
as an offset from today. A bare weekday means its next occurrence; today's weekday means next week."""

import re
from datetime import datetime, tzinfo

from bilge.core.text import folded

_FIXED: tuple[tuple[str, int], ...] = (("obur gun", 2), ("ertesi gun", 1), ("yarin", 1), ("bugun", 0))
# Calendar weekday numbers (1 = Sunday), as in Swift's Calendar.
_WEEKDAYS: dict[str, int] = {
    "pazar": 1,
    "pazartesi": 2,
    "sali": 3,
    "carsamba": 4,
    "persembe": 5,
    "cuma": 6,
    "cumartesi": 7,
}
_STEMS_LONGEST_FIRST = sorted(_WEEKDAYS, key=len, reverse=True)
_DAYS_LATER = re.compile(r"(\d+) gun sonra")


def calendar_weekday(moment: datetime) -> int:
    """1 = Sunday ... 7 = Saturday."""
    return moment.isoweekday() % 7 + 1


def day_offset(text: str, now: datetime, tz: tzinfo | None = None) -> int | None:
    """`tz` plays the role of Swift's calendar time zone; without it `now` is read as given."""
    folded_text = folded(text)
    days_later = _DAYS_LATER.search(folded_text)
    if days_later is not None:
        return int(days_later.group(1))
    words = folded_text.split()
    for index, word in enumerate(words):
        stem = next((stem for stem in _STEMS_LONGEST_FIRST if word.startswith(stem)), None)
        if stem is None:
            continue
        today = calendar_weekday(now.astimezone(tz) if tz is not None else now)
        offset = (_WEEKDAYS[stem] - today + 7) % 7 or 7
        next_week = index > 0 and words[index - 1].startswith("haftaya")
        return offset + 7 if next_week and offset < 7 else offset
    return next((offset for phrase, offset in _FIXED if phrase in folded_text), None)
