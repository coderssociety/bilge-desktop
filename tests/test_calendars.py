"""CalDAV against a real Radicale server on this computer, and the read-only iCal address."""

import threading
from datetime import datetime, timedelta
from wsgiref.simple_server import WSGIRequestHandler, make_server

import httpx
import pytest

from bilge import calendars


class _Quiet(WSGIRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def caldav_url(tmp_path_factory):
    import caldav
    import radicale
    import radicale.config

    configuration = radicale.config.load()
    configuration.update(
        {"auth": {"type": "none"}, "storage": {"filesystem_folder": str(tmp_path_factory.mktemp("dav"))},
         "rights": {"type": "owner_only"}},
        "test",
    )  # fmt: skip
    server = make_server("127.0.0.1", 0, radicale.Application(configuration), handler_class=_Quiet)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    with caldav.DAVClient(url=url, username="ayse", password="x", require_tls=False) as client:
        principal = client.principal()
        principal.make_calendar(name="İş", supported_calendar_component_set=["VEVENT"])
        principal.make_calendar(name="Yapılacaklar", supported_calendar_component_set=["VTODO"])
    yield url
    server.shutdown()


def test_events_round_trip_through_caldav(caldav_url):
    source = calendars.CalDAVSource(caldav_url, "ayse", "x")
    start = datetime.now().astimezone().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
    source.add_event("Diş hekimi", start, start + timedelta(hours=1))

    events = source.events(start - timedelta(hours=2), start + timedelta(hours=4))

    assert [(e.title, e.start, e.all_day) for e in events] == [("Diş hekimi", start, False)]


def test_reminders_go_to_a_task_list_and_can_be_completed(caldav_url):
    source = calendars.CalDAVSource(caldav_url, "ayse", "x")
    due = datetime.now().astimezone().replace(microsecond=0) + timedelta(hours=3)
    source.add_reminder("Süt al", due)
    source.add_reminder("Faturayı öde", None)

    open_titles = {r.title: r.due for r in source.open_reminders()}
    assert open_titles == {"Süt al": due, "Faturayı öde": None}

    assert source.complete_reminder("Süt al")
    assert not source.complete_reminder("Yok böyle bir şey")
    assert [r.title for r in source.open_reminders()] == ["Faturayı öde"]


def test_wrong_server_is_a_calendar_error():
    with pytest.raises(calendars.CalendarError):
        calendars.CalDAVSource("http://127.0.0.1:9/", "a", "b").events(datetime.now().astimezone(),
                                                                       datetime.now().astimezone())  # fmt: skip


def test_password_needs_https_except_on_this_computer():
    with pytest.raises(calendars.CalendarError):
        calendars.CalDAVSource("http://dav.example.org/", "a", "b").events(
            datetime.now().astimezone(), datetime.now().astimezone()
        )


ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:1
DTSTART:20261016T070000Z
DTEND:20261016T080000Z
SUMMARY:Standup
RRULE:FREQ=DAILY;COUNT=3
END:VEVENT
BEGIN:VEVENT
UID:2
DTSTART;VALUE=DATE:20261017
SUMMARY:Bayram
END:VEVENT
END:VCALENDAR
"""


def test_ics_address_expands_repeating_events_and_is_read_only():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=ICS)))
    source = calendars.ICSSource("https://calendar.example.org/secret.ics", client)
    start = datetime(2026, 10, 16).astimezone()

    events = source.events(start, start + timedelta(days=2))

    titles = [(e.title, e.all_day) for e in events]
    assert titles.count(("Standup", False)) == 2
    assert ("Bayram", True) in titles
    with pytest.raises(calendars.ReadOnly):
        source.add_event("x", start, start)


def test_ics_address_errors_are_calendar_errors():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404)))
    with pytest.raises(calendars.CalendarError):
        calendars.ICSSource("https://calendar.example.org/x.ics", client).events(
            datetime.now().astimezone(), datetime.now().astimezone()
        )


def test_plain_http_is_refused_before_any_password_is_sent():
    assert not calendars.is_secure_address("http://nas.lan/dav")
    assert calendars.is_secure_address("http://127.0.0.1:5232/")
    assert calendars.is_secure_address("https://cloud.example.org/dav")
