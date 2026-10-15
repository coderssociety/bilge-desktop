from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bilge.core import text
from bilge.core.briefing.daily_briefing import DailyBriefing, is_morning_greeting, is_request

ISTANBUL = ZoneInfo("Europe/Istanbul")


def date(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 14, hour, minute, tzinfo=ISTANBUL)


@pytest.mark.parametrize(
    "phrase", ["Günün özeti", "Bugün neler var", "Bana günü özetle", "Sabah özetini ver", "Bugün beni neler bekliyor"]
)
def test_requests_for_the_days_summary(phrase: str) -> None:
    assert is_request(phrase)


@pytest.mark.parametrize("phrase", ["Bugün hava nasıl", "Bugün takvimimde ne var", "Günaydın", "Bu akşam ne var"])
def test_not_a_summary_request(phrase: str) -> None:
    assert not is_request(phrase)


def test_a_morning_greeting_on_its_own() -> None:
    assert is_morning_greeting("Günaydın")
    assert is_morning_greeting("günaydın Bilge")
    assert not is_morning_greeting("Günaydın, saat kaç")


def test_everything_there_is_in_a_few_sentences() -> None:
    briefing = DailyBriefing(
        now=date(8, 30),
        weather="İstanbul'da bugün hava güneşli, 18 ile 24 derece arasında.",
        events=[DailyBriefing.Event("Ekip toplantısı", date(10)), DailyBriefing.Event("Diş hekimi", date(15, 30))],
        reminders=["Faturayı öde"],
        unread_mail=4,
    )
    assert briefing.text(tz=ISTANBUL) == (
        "Günaydın. Bugün 14 Ekim Çarşamba. İstanbul'da bugün hava güneşli, 18 ile 24 derece arasında. "
        "Bugün 2 etkinliğin var: 10:00'da Ekip toplantısı, 15:30'da Diş hekimi. Bugünkü anımsatıcın: Faturayı öde. "
        "4 okunmamış e-postan var."
    )


def test_a_quiet_day_and_a_long_list() -> None:
    quiet = DailyBriefing(now=date(19), weather=None, events=[], reminders=[], unread_mail=0)
    assert quiet.text(tz=ISTANBUL) == "İyi akşamlar. Bugün 14 Ekim Çarşamba. Bugün başka etkinliğin yok."
    busy = DailyBriefing(
        now=date(13),
        weather=None,
        events=[DailyBriefing.Event(f"Görüşme {number}", date(number + 1)) for number in range(9, 15)],
        reminders=["A", "B", "C"],
        unread_mail=None,
    )
    assert busy.text(tz=ISTANBUL) == (
        "İyi günler. Bugün 14 Ekim Çarşamba. "
        "Bugün 6 etkinliğin var: 10:00'da Görüşme 9, 11:00'de Görüşme 10, 12:00'de Görüşme 11 ve 3 tane daha. "
        "3 anımsatıcın var: A, B ve 1 tane daha."
    )


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (10, 0, "10:00'da"),
        (11, 0, "11:00'de"),
        (13, 0, "13:00'te"),
        (16, 0, "16:00'da"),
        (15, 30, "15:30'da"),
        (15, 40, "15:40'ta"),
        (9, 20, "09:20'de"),
        (0, 0, "00:00'da"),
        (14, 45, "14:45'te"),
        (8, 50, "08:50'de"),
        (19, 9, "19:09'da"),
        (20, 0, "20:00'de"),
    ],
)
def test_the_locative_ending_follows_the_time_as_spoken(hour: int, minute: int, expected: str) -> None:
    assert text.time_locative(hour, minute) == expected
