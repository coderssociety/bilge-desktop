"""Timers and alarms. They live in Bilge, so they only go off while it is running; when one does, Bilge says so and
the desktop shows a notification."""

import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from bilge.core.language import AssistantLanguage
from bilge.core.tools import english_time_parser, timer_phrase_parser, timer_schedule
from bilge.tools.base import Tool, ToolError
from bilge.tools.desktop.common import choice, int_argument, integer, obj, string_argument, text

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScheduledTimer:
    id: str
    fires_at: datetime
    label: str | None


class TimerService:
    """One thread watches the wall clock. A countdown per timer would run on the monotonic clock, which stops while
    the computer sleeps, so a 7:00 alarm set at night would go off late by however long the lid was closed."""

    # At most this late after the computer wakes up.
    CHECK_SECONDS = 15.0

    def __init__(self, announce: Callable[[str], None], language: AssistantLanguage, clock=datetime.now):
        self._announce = announce
        self._language = language
        self._clock = clock
        self._changed = threading.Condition()
        self._timers: dict[str, ScheduledTimer] = {}
        self._thread: threading.Thread | None = None

    @property
    def timers(self) -> list[ScheduledTimer]:
        with self._changed:
            return sorted(self._timers.values(), key=lambda t: t.fires_at)

    def schedule(self, fires_at: datetime, label: str | None, now: datetime | None = None) -> ScheduledTimer:
        timer = ScheduledTimer(uuid.uuid4().hex, fires_at, label)
        with self._changed:
            self._timers[timer.id] = timer
            if self._thread is None:
                self._thread = threading.Thread(target=self._watch, name="bilge-timers", daemon=True)
                self._thread.start()
            self._changed.notify()
        return timer

    def cancel_all(self) -> int:
        with self._changed:
            count = len(self._timers)
            self._timers.clear()
            self._changed.notify()
        return count

    def _watch(self) -> None:
        while True:
            with self._changed:
                now = self._clock()
                due = [t for t in self._timers.values() if t.fires_at <= now]
                for timer in due:
                    del self._timers[timer.id]
                if not due:
                    upcoming = min((t.fires_at for t in self._timers.values()), default=None)
                    wait = self.CHECK_SECONDS if upcoming is None else (upcoming - now).total_seconds()
                    self._changed.wait(max(0.05, min(wait, self.CHECK_SECONDS)))
                    continue
            for timer in sorted(due, key=lambda t: t.fires_at):
                self._fire(timer)

    def _fire(self, timer: ScheduledTimer) -> None:
        english = self._language is AssistantLanguage.ENGLISH
        if timer.label:
            message = f"Reminder: {timer.label}." if english else f"Hatırlatma: {timer.label}."
        else:
            message = "Your timer is done." if english else "Zamanlayıcı doldu."
        try:
            self._announce(message)
        except Exception:  # noqa: BLE001 - one failed announcement must not stop the other timers
            log.exception("Announcing a timer failed")


class TimerAction(StrEnum):
    LIST = "list"
    CANCEL_ALL = "cancelAll"


_TEXTS = {
    AssistantLanguage.TURKISH: {
        "set": "Zamanlayıcı ya da alarm kurar. Süre için 'minutes'/'seconds', belirli bir saat için 'hour'/'minute' kullan.",
        "minutes": "Kaç dakika sonra (süre)",
        "seconds": "Kaç saniye sonra (süre)",
        "hour": "Belirli saat, 24 saat biçiminde. 'sabah yedi' → 7, 'akşam altı' → 18",
        "minute": "Belirli saatin dakikası. 'yedi buçuk' → 30",
        "label": "Bir-üç kelimeyle ne için olduğu, örn. 'çay'. Söylenmediyse boş bırak.",
        "unclear": "Süre ya da saat anlaşılamadı.",
        "today": "Tamam, saat {time} için kurdum.",
        "tomorrow": "Tamam, yarın saat {time} için kurdum.",
        "manage": "Bilge'de kurulu zamanlayıcı ve alarmları listeler, sayar ya da hepsini iptal eder.",
        "none": "Kurulu zamanlayıcı yok.",
        "list": "Zamanlayıcılar: {timers}",
        "none_to_cancel": "İptal edilecek zamanlayıcı yoktu.",
        "cancelled": "{count} zamanlayıcı iptal edildi.",
    },
    AssistantLanguage.ENGLISH: {
        "set": "Sets a timer or an alarm. Use 'minutes'/'seconds' for a duration, 'hour'/'minute' for a time of day.",
        "minutes": "In how many minutes (duration)",
        "seconds": "In how many seconds (duration)",
        "hour": "A time of day, 24-hour clock. '7 am' → 7, '6 pm' → 18",
        "minute": "The minute of that time. 'half past seven' → 30",
        "label": "What it's for in one to three words, e.g. 'tea'. Leave empty if not said.",
        "unclear": "I didn't get the duration or the time.",
        "today": "OK, it's set for {time}.",
        "tomorrow": "OK, it's set for {time} tomorrow.",
        "manage": "Lists, counts or cancels all the timers and alarms set in Bilge.",
        "none": "There are no timers.",
        "list": "Timers: {timers}",
        "none_to_cancel": "There were no timers to cancel.",
        "cancelled": "Cancelled {count} timers.",
    },
}


def timer_tools(
    service: TimerService, language: AssistantLanguage, clock: Callable[[], datetime] = datetime.now
) -> list[Tool]:
    texts = _TEXTS[language]
    english = language is AssistantLanguage.ENGLISH

    def refine(arguments: dict[str, Any], command: str) -> dict[str, Any]:
        # The model reliably picks this tool but sometimes garbles numbers ("20:00" → 19), so precise times and
        # durations come from the text itself.
        parsed = (
            english_time_parser.parse(command, appointment=False) if english else timer_phrase_parser.parse(command)
        )
        if parsed is None:
            return arguments
        if parsed.hour is not None:
            return {**arguments, "hour": parsed.hour, "minute": parsed.minute, "minutes": None, "seconds": None}
        if parsed.duration_seconds is not None:
            minutes, seconds = divmod(parsed.duration_seconds, 60)
            return {**arguments, "minutes": minutes, "seconds": seconds, "hour": None, "minute": None}
        return arguments

    def set_timer(arguments: dict[str, Any]) -> str:
        now = clock()
        fires_at = timer_schedule.fire_date(
            int_argument(arguments, "minutes"), int_argument(arguments, "seconds"),
            int_argument(arguments, "hour"), int_argument(arguments, "minute"), now,
        )  # fmt: skip
        if fires_at is None:
            raise ToolError(texts["unclear"])
        timer = service.schedule(fires_at, timer_schedule.clean_label(string_argument(arguments, "label")), now)
        same_day = timer.fires_at.date() == now.date()
        return texts["today" if same_day else "tomorrow"].format(time=f"{timer.fires_at:%H:%M}")

    def manage(arguments: dict[str, Any]) -> str:
        if string_argument(arguments, "action") == TimerAction.CANCEL_ALL:
            count = service.cancel_all()
            return texts["cancelled"].format(count=count) if count else texts["none_to_cancel"]
        timers = service.timers
        if not timers:
            return texts["none"]
        listed = "; ".join(f"{t.fires_at:%H:%M}" + (f" {t.label}" if t.label else "") for t in timers)
        return texts["list"].format(timers=listed)

    parameters = obj(
        minutes=integer(texts["minutes"], 0, 1440), seconds=integer(texts["seconds"], 0, 3600),
        hour=integer(texts["hour"], 0, 23), minute=integer(texts["minute"], 0, 59), label=text(texts["label"]),
    )  # fmt: skip
    return [
        Tool("setTimer", texts["set"], run=set_timer, parameters=parameters, refine=refine),
        Tool("manageTimers", texts["manage"], run=manage, parameters=obj(["action"], action=choice(TimerAction, ""))),
    ]
