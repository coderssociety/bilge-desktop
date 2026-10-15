from datetime import datetime, timedelta

import pytest

from bilge import calendars
from bilge.core.language import AssistantLanguage
from bilge.tools.base import ToolError
from bilge.tools.builtin.calendar import calendar_tools

TR, EN = AssistantLanguage.TURKISH, AssistantLanguage.ENGLISH
NOW = datetime(2026, 10, 15, 14, 5)


class FakeSource:
    writable = True

    def __init__(self):
        base = NOW.astimezone().replace(hour=0, minute=0)
        self.events_list = [
            calendars.CalendarEvent("Bayram", base + timedelta(days=1), True),
            calendars.CalendarEvent("Diş hekimi", base + timedelta(days=1, hours=10), False),
        ]
        self.added, self.reminders, self.completed = [], [calendars.Reminder("Süt al", None)], []

    def events(self, start, end):
        return [e for e in self.events_list if start <= e.start < end]

    def add_event(self, title, start, end):
        self.added.append((title, start, end))

    def open_reminders(self):
        return self.reminders

    def add_reminder(self, title, due):
        self.added.append((title, due))

    def complete_reminder(self, title):
        self.completed.append(title)
        return True


def tools(source, language=TR):
    return {tool.name: tool for tool in calendar_tools(lambda: source, language, clock=lambda: NOW)}


def test_reading_tomorrow_and_the_week():
    found = tools(FakeSource())
    assert found["readCalendar"].run({"range": "tomorrow"}) == "Yarın 2 etkinlik var: tüm gün: Bayram; 10:00 Diş hekimi"
    assert found["readCalendar"].run({"range": "today"}) == "Bugün takvimde etkinlik yok."
    week = found["readCalendar"].run({"range": "thisWeek"})
    assert week == "Önümüzdeki 7 günde 2 etkinlik var: Cuma tüm gün: Bayram; Cuma 10:00 Diş hekimi"
    assert found["readCalendar"].untrusted_output


def test_the_time_comes_from_the_words_not_the_model():
    add = tools(FakeSource())["addCalendarEvent"]
    refined = add.refine({"title": "Diş hekimi", "dayOffset": 0, "hour": 9}, "yarın 10:00'da diş hekimi ekle")
    assert (refined["dayOffset"], refined["hour"], refined["minute"]) == (1, 10, 0)
    # An hour the user never said is dropped.
    assert add.refine({"title": "x", "hour": 15}, "yarın toplantı ekle")["hour"] is None
    # A part of the day keeps the model's hour.
    assert add.refine({"title": "x", "hour": 19}, "yarın akşam yemek ekle")["hour"] == 19


def test_adding_an_event_asks_with_the_day_and_time():
    source = FakeSource()
    add = tools(source)["addCalendarEvent"]
    arguments = {"title": "Diş hekimi", "dayOffset": 1, "hour": 10, "minute": 0}
    assert add.question(arguments) == "Yarın saat 10:00 için 'Diş hekimi' etkinliğini takvime ekleyeyim mi?"
    assert add.run(arguments) == "Ekledim: yarın saat 10:00, Diş hekimi."
    title, start, end = source.added[0]
    assert (title, start.hour, end - start) == ("Diş hekimi", 10, timedelta(hours=1))
    later = {"title": "Konser", "dayOffset": 3, "hour": 20}
    assert tools(source, EN)["addCalendarEvent"].question(later) == (
        "Shall I add 'Konser' to your calendar for Sunday 18 October at 20:00?"
    )


def test_reminders_are_listed_added_and_completed_by_a_loose_name():
    source = FakeSource()
    found = tools(source)
    assert found["readReminders"].run({}) == "1 anımsatıcı var: Süt al"
    assert found["addReminder"].question({"title": "Ekmek al"}) == "'Ekmek al' anımsatıcısını ekleyeyim mi?"
    complete = found["completeReminder"]
    arguments = complete.refine({"title": "süt"}, "süt almayı tamamladım işaretle")
    assert complete.run(arguments) == "'Süt al' tamamlandı olarak işaretlendi."
    assert source.completed == ["Süt al"]


def test_unconfigured_read_only_and_unreachable_calendars_are_explained():
    with pytest.raises(ToolError, match="bilge calendar"):
        {t.name: t for t in calendar_tools(lambda: None, TR)}["readCalendar"].run({"range": "today"})
    read_only = FakeSource()
    read_only.writable = False
    with pytest.raises(ToolError, match="yalnızca okunabiliyor"):
        tools(read_only)["addReminder"].run({"title": "x"})

    class Down(FakeSource):
        def events(self, start, end):
            raise calendars.CalendarError("down")

    with pytest.raises(ToolError, match="Takvime ulaşamadım"):
        tools(Down())["readCalendar"].run({"range": "today"})


def test_a_date_the_parser_does_not_know_keeps_the_models_day():
    add = tools(FakeSource())["addCalendarEvent"]
    refined = add.refine({"title": "Toplantı", "dayOffset": 31, "hour": 10}, "15 Kasım'da 10:00'da toplantı ekle")
    assert (refined["dayOffset"], refined["hour"]) == (31, 10)


@pytest.mark.skipif(not hasattr(__import__("time"), "tzset"), reason="needs time.tzset to change the zone")
def test_wall_clock_times_survive_a_change_to_summer_time(monkeypatch):
    import time

    monkeypatch.setenv("TZ", "Europe/Berlin")
    time.tzset()
    try:
        from bilge.tools.builtin.calendar import Moments

        moments = Moments(EN, clock=lambda: datetime(2026, 3, 25, 12, 0))
        moment = moments.resolve(10, 9, 0)
        assert (moment.hour, moment.utcoffset()) == (9, timedelta(hours=2))
        assert calendars.local(datetime(2026, 7, 1, 8, 0, tzinfo=__import__("datetime").timezone.utc))[0].hour == 10
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()
