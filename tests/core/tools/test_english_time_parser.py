from datetime import datetime

import pytest

from bilge.core.tools import english_time_parser

THURSDAY = datetime(2026, 10, 15, 9)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("tomorrow at ten", 1),
        ("the day after tomorrow", 2),
        ("on Friday", 1),
        ("next Friday", 8),
        ("on Thursday", 7),
        ("in 3 days", 3),
        ("in three days", 3),
        ("today at noon", 0),
        ("set a timer", None),
    ],
)
def test_days(text, expected):
    assert english_time_parser.day_offset(text, now=THURSDAY) == expected


@pytest.mark.parametrize(
    ("text", "hour", "minute"),
    [
        ("Add a dentist appointment tomorrow at ten", 10, 0),
        ("meeting at 3", 15, 0),
        ("at 10:30", 10, 30),
        ("at 7 pm", 19, 0),
        ("at 7:15 p.m.", 19, 15),
        ("12 am", 0, 0),
        ("lunch at noon", 12, 0),
        ("dinner at eight tonight", 20, 0),
        ("Set an alarm for 6:30", 6, 30),
        ("At a dentist appointment tomorrow at 10", 10, 0),
    ],
)
def test_clock_times(text, hour, minute):
    result = english_time_parser.parse(text)
    assert result is not None
    assert result.hour == hour
    assert result.minute == minute


def test_alarms_keep_the_hour_as_said():
    wake = english_time_parser.parse("wake me up at 6", appointment=False)
    tonight = english_time_parser.parse("remind me at 9 tonight", appointment=False)
    assert wake is not None and wake.hour == 6
    assert tonight is not None and tonight.hour == 21


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("Set a timer for 10 minutes", 600),
        ("in an hour", 3600),
        ("for half an hour", 1800),
        ("1 hour 15 minutes", 4500),
        ("forty five seconds", 45),
        ("in twenty minutes", 1200),
    ],
)
def test_durations(text, seconds):
    result = english_time_parser.parse(text)
    assert result is not None
    assert result.duration_seconds == seconds


def test_nothing_to_read():
    assert english_time_parser.parse("Add milk to my list") is None
    assert english_time_parser.parse("Turn the volume to 30 percent") is None
