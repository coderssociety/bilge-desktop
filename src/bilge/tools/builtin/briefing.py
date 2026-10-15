"""The day at a glance ("günün özeti", and the first "günaydın" of a morning): weather, today's remaining events and
the reminders due. The parts are gathered at once; one that is slow or unavailable is left out."""

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import date, datetime, timedelta
from typing import Any

from bilge import calendars
from bilge.core.briefing import daily_briefing
from bilge.core.briefing.daily_briefing import DailyBriefing
from bilge.core.language import AssistantLanguage
from bilge.tools.base import Tool, ToolError

log = logging.getLogger(__name__)

PART_SECONDS = 5
# "Günaydın" after noon is a greeting, not a request for the morning summary.
MORNING_ENDS = 12


class Briefing:
    def __init__(
        self,
        language: AssistantLanguage,
        weather: Tool,
        calendar: Callable[[], calendars.CalendarSource | None],
        wake_phrase: str,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self.language = language
        self.weather = weather
        self.calendar = calendar
        self.wake_phrase = wake_phrase
        self.clock = clock
        self._last: date | None = None

    def claims(self, command: str) -> bool:
        if daily_briefing.is_request(command, self.language):
            return True
        now = self.clock()
        return (
            daily_briefing.is_morning_greeting(command, self.wake_phrase, self.language)
            and now.hour < MORNING_ENDS
            and self._last != now.date()
        )

    def run(self, _: dict[str, Any]) -> str:
        now = self.clock().astimezone()
        self._last = now.date()
        end_of_day = (
            now.replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        ).astimezone()
        pool = ThreadPoolExecutor(max_workers=3)
        weather = pool.submit(self._weather)
        events = pool.submit(self._events, now, end_of_day)
        reminders = pool.submit(self._reminders, end_of_day)
        deadline = time.monotonic() + PART_SECONDS
        briefing = DailyBriefing(
            now=now, weather=_bounded(weather, deadline), events=_bounded(events, deadline) or [],
            reminders=_bounded(reminders, deadline) or [], unread_mail=None,
        )  # fmt: skip
        # Parts still running after their time are dropped, not awaited.
        pool.shutdown(wait=False, cancel_futures=True)
        return briefing.text(language=self.language)

    def _weather(self) -> str | None:
        try:
            return self.weather.run({})
        except ToolError:
            return None

    def _events(self, now: datetime, end: datetime) -> list[DailyBriefing.Event]:
        source = self.calendar()
        if source is None:
            return []
        return [
            DailyBriefing.Event(event.title, event.start)
            for event in source.events(now, end)
            if not event.all_day and event.start >= now
        ]

    def _reminders(self, end: datetime) -> list[str]:
        source = self.calendar()
        if source is None:
            return []
        return [r.title for r in source.open_reminders() if r.due is not None and r.due < end]


def _bounded(future, deadline: float):
    try:
        return future.result(timeout=max(0.0, deadline - time.monotonic()))
    except FutureTimeout:
        return None
    except Exception:  # noqa: BLE001 - a missing part only shortens the summary
        log.info("A briefing part failed", exc_info=True)
        return None


def briefing_tool(briefing: Briefing) -> Tool:
    english = briefing.language is AssistantLanguage.ENGLISH
    description = (
        "Gives a summary of the day: weather, today's events and reminders."
        if english
        else "Günün özetini söyler: hava durumu, bugünkü etkinlikler ve anımsatıcılar."
    )
    # Event and reminder titles in shared calendars are written by other people.
    return Tool("dailyBriefing", description, run=briefing.run, untrusted_output=True)
