"""Reading and adding calendar events and reminders. The day and clock time come from the user's own words where
they say them; the model's numbers only fill gaps."""

from collections.abc import Callable
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from bilge import calendars
from bilge.brain.instructions import month_name, weekday_name
from bilge.core.language import AssistantLanguage
from bilge.core.text import folded
from bilge.core.tools import english_time_parser, phrase_matcher, relative_day_parser, timer_phrase_parser
from bilge.tools.base import Risk, Tool, ToolError
from bilge.tools.desktop.common import choice, int_argument, integer, obj, string_argument, text

EN, TR = AssistantLanguage.ENGLISH, AssistantLanguage.TURKISH
DEFAULT_DURATION_MINUTES = 60
# A day mentioned without a time ("yarın") means a reminder in the morning.
DEFAULT_HOUR = 9
MAX_EVENTS = 12
MAX_REMINDERS = 10
_PARTS_OF_DAY = ("sabah", "ogle", "aksam", "gece")


class Range(StrEnum):
    TODAY = "today"
    TOMORROW = "tomorrow"
    THIS_WEEK = "thisWeek"


_TEXTS = {
    TR: {
        "not_configured": "Takvim bağlı değil. Bağlamak için bilgisayarda 'bilge calendar' komutunu çalıştır.",
        "read_only": "Bu takvim adresi yalnızca okunabiliyor, değişiklik yapamam.",
        "failed": "Takvime ulaşamadım.",
        "read": "Takvimdeki etkinlikleri okur: bugün, yarın ya da bu hafta.",
        "labels": {"today": "Bugün", "tomorrow": "Yarın", "thisWeek": "Önümüzdeki 7 günde"},
        "no_events": "{label} takvimde etkinlik yok.",
        "events": "{label} {count} etkinlik var: {list}",
        "all_day": "tüm gün: {title}",
        "add": "Takvime yeni bir etkinlik ya da randevu ekler.",
        "title": "Etkinliğin kısa adı, örn. 'Diş hekimi'",
        "day_offset": "Bugünden kaç gün sonra: bugün 0, yarın 1",
        "hour": "Başlangıç saati, 24 saat biçiminde",
        "minute": "Başlangıç dakikası",
        "duration": "Süre (dakika); söylenmediyse boş bırak",
        "add_question": "{when} için '{title}' etkinliğini takvime ekleyeyim mi?",
        "add_question_undated": "'{title}' etkinliğini ekleyeyim mi?",
        "no_time": "Etkinliğin günü ya da saati anlaşılamadı.",
        "no_title": "Ne ekleyeceğimi anlayamadım.",
        "added": "Ekledim: {when}, {title}.",
        "today": "bugün", "tomorrow": "yarın", "at": "{day} saat {time}",
        "reminders": "Anımsatıcılardaki tamamlanmamış yapılacakları listeler (zamanlayıcı ve alarmlar değil).",
        "no_reminders": "Bekleyen anımsatıcı yok.",
        "reminder_list": "{count} anımsatıcı var: {list}",
        "add_reminder": "Anımsatıcılara yeni bir yapılacak ekler; istenirse belirli gün ve saatte hatırlatır.",
        "reminder_title": "Yapılacak iş, örn. 'Ekmek al'",
        "reminder_question": "'{title}' anımsatıcısını {when} için ekleyeyim mi?",
        "reminder_question_undated": "'{title}' anımsatıcısını ekleyeyim mi?",
        "reminder_added": "Ekledim, {when} hatırlatacağım.",
        "reminder_added_undated": "'{title}' anımsatıcılara eklendi.",
        "complete": "Anımsatıcılardaki bir yapılacağı tamamlandı olarak işaretler ('faturayı ödedim, işaretle', 'ilacı aldım, listeden düş').",
        "complete_title": "Tamamlanan işin adı, örn. 'Süt al'",
        "not_found": "Anımsatıcılarında '{title}' diye tamamlanmamış bir iş bulamadım.",
        "completed": "'{title}' tamamlandı olarak işaretlendi.",
    },
    EN: {
        "not_configured": "No calendar is connected. Run 'bilge calendar' on the computer to connect one.",
        "read_only": "This calendar address is read-only; I can't change it.",
        "failed": "I couldn't reach the calendar.",
        "read": "Reads calendar events: today, tomorrow or this week.",
        "labels": {"today": "Today", "tomorrow": "Tomorrow", "thisWeek": "In the next 7 days"},
        "no_events": "{label} there's nothing on the calendar.",
        "events": "{label} there are {count} events: {list}",
        "all_day": "all day: {title}",
        "add": "Adds a new event or appointment to the calendar.",
        "title": "A short name for the event, e.g. 'Dentist'",
        "day_offset": "Days from today: today 0, tomorrow 1",
        "hour": "Start hour, 24-hour clock",
        "minute": "Start minute",
        "duration": "Length in minutes; leave empty if not said",
        "add_question": "Shall I add '{title}' to your calendar for {when}?",
        "add_question_undated": "Shall I add the event '{title}'?",
        "no_time": "I didn't get the day or time of the event.",
        "no_title": "I didn't get what to add.",
        "added": "Added: {title}, {when}.",
        "today": "today", "tomorrow": "tomorrow", "at": "{day} at {time}",
        "reminders": "Lists the open to-dos in the reminders list (not timers or alarms).",
        "no_reminders": "There are no open reminders.",
        "reminder_list": "{count} reminders: {list}",
        "add_reminder": "Adds a to-do to the reminders list, optionally with a day and time to be reminded.",
        "reminder_title": "The to-do, e.g. 'Buy bread'",
        "reminder_question": "Shall I add the reminder '{title}' for {when}?",
        "reminder_question_undated": "Shall I add the reminder '{title}'?",
        "reminder_added": "Added; I'll remind you {when}.",
        "reminder_added_undated": "Added '{title}' to your reminders.",
        "complete": "Marks a to-do in the reminders list as done ('I paid the bill, tick it off').",
        "complete_title": "The finished to-do, e.g. 'Buy milk'",
        "not_found": "I couldn't find an open to-do called '{title}'.",
        "completed": "Marked '{title}' as done.",
    },
}  # fmt: skip


class Moments:
    """When a spoken event or reminder happens, in the assistant's language."""

    def __init__(self, language: AssistantLanguage, clock: Callable[[], datetime]):
        self.language = language
        self.clock = clock
        self.texts = _TEXTS[language]

    def now(self) -> datetime:
        return self.clock().astimezone()

    def resolve(self, day_offset: int | None, hour: int | None, minute: int | None) -> datetime | None:
        # Wall-clock arithmetic on a naive time, given its zone last, so "in ten days at 9" stays 9 across a DST change.
        day = self.clock().replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        day += timedelta(days=day_offset or 0)
        if hour is None:
            return None if day_offset is None else day.replace(hour=DEFAULT_HOUR).astimezone()
        if not 0 <= hour < 24 or not 0 <= (minute or 0) < 60:
            return None
        return day.replace(hour=hour, minute=minute or 0).astimezone()

    def describe(self, moment: datetime) -> str:
        days = (moment.date() - self.now().date()).days
        if days == 0:
            day = self.texts["today"]
        elif days == 1:
            day = self.texts["tomorrow"]
        elif self.language is EN:
            day = f"{weekday_name(moment, EN)} {moment.day} {month_name(moment.month, EN)}"
        else:
            day = f"{moment.day} {month_name(moment.month, TR)} {weekday_name(moment, TR)}"
        return self.texts["at"].format(day=day, time=f"{moment:%H:%M}")

    def refine(self, arguments: dict[str, Any], command: str) -> dict[str, Any]:
        """Day and clock time said in the command override the model's. A model hour is kept only when a part of
        the day was said ("yarın akşam"); otherwise it was invented, so it is dropped."""
        english = self.language is EN
        now = self.now()
        parsed = (
            english_time_parser.day_offset(command, now) if english else relative_day_parser.day_offset(command, now)
        )
        # A date the parser doesn't know ("15 Kasım'da") keeps the model's day.
        day = parsed if parsed is not None else arguments.get("dayOffset")
        clock = english_time_parser.parse(command) if english else timer_phrase_parser.parse(command)
        if clock is not None and clock.hour is not None:
            return {**arguments, "dayOffset": day, "hour": clock.hour, "minute": clock.minute}
        parts = english_time_parser.PART_OF_DAY_WORDS if english else _PARTS_OF_DAY
        if any(part in folded(command) for part in parts):
            return {**arguments, "dayOffset": day}
        return {**arguments, "dayOffset": day, "hour": None, "minute": None}

    def of(self, arguments: dict[str, Any]) -> datetime | None:
        return self.resolve(
            int_argument(arguments, "dayOffset"), int_argument(arguments, "hour"), int_argument(arguments, "minute")
        )


def calendar_tools(
    source: Callable[[], calendars.CalendarSource | None],
    language: AssistantLanguage,
    clock: Callable[[], datetime] = datetime.now,
) -> list[Tool]:
    texts = _TEXTS[language]
    moments = Moments(language, clock)

    def connected(writing: bool = False) -> calendars.CalendarSource:
        found = source()
        if found is None:
            raise ToolError(texts["not_configured"])
        if writing and not found.writable:
            raise ToolError(texts["read_only"])
        return found

    def guarded(action):
        try:
            return action()
        except calendars.ReadOnly as error:
            raise ToolError(texts["read_only"]) from error
        except calendars.CalendarError as error:
            raise ToolError(texts["failed"]) from error

    def read(arguments: dict[str, Any]) -> str:
        try:
            span = Range(string_argument(arguments, "range"))
        except ValueError:
            span = Range.TODAY
        days = 7 if span is Range.THIS_WEEK else 1
        first = 1 if span is Range.TOMORROW else 0
        start, end = moments.resolve(first, 0, 0), moments.resolve(first + days, 0, 0)
        calendar = connected()
        events = guarded(lambda: calendar.events(start, end))
        label = texts["labels"][span.value]
        if not events:
            return texts["no_events"].format(label=label)
        listed = "; ".join(_describe_event(event, days > 1, language) for event in events[:MAX_EVENTS])
        return texts["events"].format(label=label, count=len(events), list=listed)

    def add_question(arguments: dict[str, Any]) -> str:
        title = string_argument(arguments, "title")
        start = moments.of(arguments)
        if start is None:
            return texts["add_question_undated"].format(title=title)
        when = moments.describe(start)
        return texts["add_question"].format(when=when[:1].upper() + when[1:] if language is TR else when, title=title)

    def add(arguments: dict[str, Any]) -> str:
        title = string_argument(arguments, "title")
        if not title:
            raise ToolError(texts["no_title"])
        start = moments.of(arguments)
        if start is None:
            raise ToolError(texts["no_time"])
        minutes = int_argument(arguments, "durationMinutes") or DEFAULT_DURATION_MINUTES
        calendar = connected(writing=True)
        guarded(lambda: calendar.add_event(title, start, start + timedelta(minutes=max(5, min(minutes, 720)))))
        return texts["added"].format(when=moments.describe(start), title=title)

    def reminders(_: dict[str, Any]) -> str:
        calendar = connected()
        titles = [r.title for r in guarded(calendar.open_reminders) if r.title]
        if not titles:
            return texts["no_reminders"]
        return texts["reminder_list"].format(count=len(titles), list="; ".join(titles[:MAX_REMINDERS]))

    def reminder_question(arguments: dict[str, Any]) -> str:
        title = string_argument(arguments, "title")
        due = moments.of(arguments)
        if due is None:
            return texts["reminder_question_undated"].format(title=title)
        return texts["reminder_question"].format(title=title, when=moments.describe(due))

    def add_reminder(arguments: dict[str, Any]) -> str:
        title = string_argument(arguments, "title")
        if not title:
            raise ToolError(texts["no_title"])
        due = moments.of(arguments)
        calendar = connected(writing=True)
        guarded(lambda: calendar.add_reminder(title, due))
        if due is None:
            return texts["reminder_added_undated"].format(title=title)
        return texts["reminder_added"].format(when=moments.describe(due))

    def complete_refine(arguments: dict[str, Any], command: str) -> dict[str, Any]:
        # The matcher finds "Süt al" in "süt almayı tamamladım, işaretle" by itself, so the whole command is kept
        # alongside the model's title in case the model shortened it badly.
        return {**arguments, "command": command}

    def complete(arguments: dict[str, Any]) -> str:
        title = string_argument(arguments, "title")
        calendar = connected(writing=True)
        titles = [r.title for r in guarded(calendar.open_reminders) if r.title]
        match = phrase_matcher.best_match(title, titles) or phrase_matcher.best_match(
            string_argument(arguments, "command"), titles
        )
        if match is None or not guarded(lambda: calendar.complete_reminder(match)):
            raise ToolError(texts["not_found"].format(title=title))
        return texts["completed"].format(title=match)

    event_schema = obj(
        ["title"],
        title=text(texts["title"]),
        dayOffset=integer(texts["day_offset"], 0, 60),
        hour=integer(texts["hour"], 0, 23),
        minute=integer(texts["minute"], 0, 59),
        durationMinutes=integer(texts["duration"], 5, 720),
    )
    reminder_schema = obj(
        ["title"],
        title=text(texts["reminder_title"]),
        dayOffset=integer(texts["day_offset"], 0, 60),
        hour=integer(texts["hour"], 0, 23),
        minute=integer(texts["minute"], 0, 59),
    )
    return [
        # Titles in a shared calendar or an invitation are written by other people.
        Tool(
            "readCalendar",
            texts["read"],
            run=read,
            parameters=obj(["range"], range=choice(Range, "")),
            untrusted_output=True,
        ),
        Tool(
            "addCalendarEvent",
            texts["add"],
            run=add,
            parameters=event_schema,
            risk=Risk.CONFIRM,
            confirmation=add_question,
            refine=moments.refine,
        ),
        Tool("readReminders", texts["reminders"], run=reminders, untrusted_output=True),
        Tool(
            "addReminder",
            texts["add_reminder"],
            run=add_reminder,
            parameters=reminder_schema,
            risk=Risk.CONFIRM,
            confirmation=reminder_question,
            refine=moments.refine,
        ),
        Tool(
            "completeReminder",
            texts["complete"],
            run=complete,
            refine=complete_refine,
            parameters=obj(["title"], title=text(texts["complete_title"])),
        ),
    ]


def _describe_event(event: calendars.CalendarEvent, include_day: bool, language: AssistantLanguage) -> str:
    texts = _TEXTS[language]
    day = weekday_name(event.start, language)
    if event.all_day:
        all_day = texts["all_day"].format(title=event.title)
        return f"{day} {all_day}" if include_day else all_day
    clock = f"{event.start:%H:%M}"
    return f"{day} {clock} {event.title}" if include_day else f"{clock} {event.title}"
