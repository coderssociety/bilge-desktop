"""Swift EnglishSentencesTests: weather, the daily briefing and alerts in English."""

from datetime import datetime
from zoneinfo import ZoneInfo

from bilge.core.alerts import upcoming_alerts
from bilge.core.alerts.upcoming_alerts import AlertCandidate
from bilge.core.briefing.daily_briefing import DailyBriefing, is_morning_greeting, is_request
from bilge.core.language import AssistantLanguage
from bilge.core.web import weather_report

ISTANBUL = ZoneInfo("Europe/Istanbul")
ENGLISH = AssistantLanguage.ENGLISH


def date(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 15, hour, minute, tzinfo=ISTANBUL)


def test_weather() -> None:
    assert (
        weather_report.current(city="London", temperature=12.4, code=3, language=ENGLISH)
        == "In London it's overcast right now, 12 degrees."
    )
    assert (
        weather_report.daily(
            city="Paris", day_name="tomorrow", minimum=8, maximum=15.6, code=61, rain_chance=40, language=ENGLISH
        )
        == "In Paris tomorrow it will be lightly rainy, between 8 and 16 degrees. There's a 40 percent chance of rain."
    )
    assert weather_report.current(city="İzmir", temperature=20, code=0) == "İzmir'de şu an hava açık, 20 derece."


def test_daily_briefing() -> None:
    briefing = DailyBriefing(
        now=date(8),
        weather="In London it's clear right now, 10 degrees.",
        events=[DailyBriefing.Event("Standup", date(9, 30)), DailyBriefing.Event("Lunch", date(13))],
        reminders=["Buy milk"],
        unread_mail=1,
    )
    text = briefing.text(tz=ISTANBUL, language=ENGLISH)
    assert text.startswith("Good morning. Today is Thursday, October 15.")
    assert "You have 2 events today: Standup at 9:30 AM and Lunch at 1:00 PM." in text
    assert "Today's reminder: Buy milk." in text
    assert text.endswith("You have 1 unread email.")


def test_briefing_requests_and_the_morning_greeting() -> None:
    assert is_request("What does my day look like?", language=ENGLISH)
    assert is_request("Give me my daily briefing", language=ENGLISH)
    assert not is_request("What time is it", language=ENGLISH)
    assert is_morning_greeting("Bilge, good morning", language=ENGLISH)
    assert not is_morning_greeting("Good morning, what time is it", language=ENGLISH)


def test_upcoming_alerts() -> None:
    alerts = [
        AlertCandidate("a", "Standup", date(9, 10), AlertCandidate.Kind.EVENT),
        AlertCandidate("b", "Call mom", date(9), AlertCandidate.Kind.REMINDER),
    ]
    assert (
        upcoming_alerts.message(alerts, now=date(9), language=ENGLISH)
        == "Standup starts in 10 minutes. Reminder: Call mom."
    )
