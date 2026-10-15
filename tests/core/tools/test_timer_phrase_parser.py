import pytest

from bilge.core.tools import timer_phrase_parser
from bilge.core.tools.timer_phrase_parser import Result


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("20:00'de ilacımı hatırlat", Result(hour=20, minute=0, duration_seconds=None)),
        ("yarın 07:30'da uyandır", Result(hour=7, minute=30, duration_seconds=None)),
        ("45 dakikalık zamanlayıcı kur", Result(hour=None, minute=None, duration_seconds=2700)),
        ("1 saat 15 dakika sonra hatırlat", Result(hour=None, minute=None, duration_seconds=4500)),
        ("30 saniye say", Result(hour=None, minute=None, duration_seconds=30)),
        ("2 buçuk saat sonra", Result(hour=None, minute=None, duration_seconds=9000)),
        ("Yarım saat sonra uyar", Result(hour=None, minute=None, duration_seconds=1800)),
        ("çeyrek saatlik zamanlayıcı", Result(hour=None, minute=None, duration_seconds=900)),
    ],
)
def test_reads_clock_times_and_durations_from_resolved_command_text(text, expected):
    assert timer_phrase_parser.parse(text) == expected


def test_returns_none_when_nothing_precise_is_said():
    assert timer_phrase_parser.parse("çay için zamanlayıcı kur") is None
