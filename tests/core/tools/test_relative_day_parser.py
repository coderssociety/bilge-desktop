from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bilge.core.tools import relative_day_parser

ISTANBUL = ZoneInfo("Europe/Istanbul")
TUESDAY = datetime(2026, 10, 13, 9, tzinfo=ISTANBUL)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("bugün saat 15:00'te toplantı", 0),
        ("yarın 10:00'da diş hekimi", 1),
        ("öbür gün sabah", 2),
        ("ertesi gün", 1),
        ("cuma günü toplantı ekle", 3),
        ("Pazartesi annemi ara", 6),
        ("salı günü", 7),
        ("haftaya çarşamba", 8),
        ("3 gün sonra", 3),
    ],
)
def test_resolves_relative_day_words_to_a_day_offset(text, expected):
    assert relative_day_parser.day_offset(text, now=TUESDAY, tz=ISTANBUL) == expected


def test_returns_none_when_no_day_is_mentioned():
    assert relative_day_parser.day_offset("15:00'te toplantı ekle", now=TUESDAY, tz=ISTANBUL) is None
