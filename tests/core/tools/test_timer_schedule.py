from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from bilge.core.tools import timer_schedule

ISTANBUL = ZoneInfo("Europe/Istanbul")
NOW = datetime(2026, 10, 13, 14, tzinfo=ISTANBUL)


def test_durations_add_minutes_and_seconds():
    date = timer_schedule.fire_date(minutes=10, seconds=30, hour=None, minute=None, now=NOW, tz=ISTANBUL)
    assert date == NOW + timedelta(seconds=630)


def test_a_clock_time_later_today_fires_today():
    date = timer_schedule.fire_date(minutes=None, seconds=None, hour=18, minute=30, now=NOW, tz=ISTANBUL)
    assert date == datetime(2026, 10, 13, 18, 30, tzinfo=ISTANBUL)


def test_a_clock_time_already_passed_fires_tomorrow():
    date = timer_schedule.fire_date(minutes=None, seconds=None, hour=7, minute=None, now=NOW, tz=ISTANBUL)
    assert date == datetime(2026, 10, 14, 7, tzinfo=ISTANBUL)


def test_clock_time_wins_over_a_duration_when_both_are_given():
    date = timer_schedule.fire_date(minutes=5, seconds=None, hour=18, minute=0, now=NOW, tz=ISTANBUL)
    assert date == datetime(2026, 10, 13, 18, tzinfo=ISTANBUL)


@pytest.mark.parametrize(
    ("minutes", "seconds", "hour", "minute"),
    [(None, None, None, None), (0, 0, None, None), (-5, None, None, None), (1500, None, None, None),
     (None, None, 24, 0), (None, None, 7, 75)],
)  # fmt: skip
def test_rejects_empty_zero_negative_too_long_or_out_of_range_input(minutes, seconds, hour, minute):
    date = timer_schedule.fire_date(minutes=minutes, seconds=seconds, hour=hour, minute=minute, now=NOW, tz=ISTANBUL)
    assert date is None


def test_labels_are_trimmed_to_a_short_phrase():
    assert timer_schedule.clean_label("  çay  ") == "çay"
    assert timer_schedule.clean_label("") is None
    assert len(timer_schedule.clean_label("uzun " * 30) or "") <= 40
