"""The user's calendar and reminders: a CalDAV account (Nextcloud, iCloud, Fastmail, Radicale and others) or a
read-only iCal address (Google Calendar's "secret address in iCal format")."""

import ipaddress
import logging
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Protocol
from urllib.parse import urlsplit

import httpx

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 15
MAX_ICS_BYTES = 10_000_000


class CalendarError(Exception):
    pass


class NotConfigured(CalendarError):
    pass


class ReadOnly(CalendarError):
    pass


@dataclass(frozen=True)
class CalendarEvent:
    title: str
    # Local time, timezone-aware; midnight for all-day events.
    start: datetime
    all_day: bool


@dataclass(frozen=True)
class Reminder:
    title: str
    due: datetime | None


class CalendarSource(Protocol):
    writable: bool

    def events(self, start: datetime, end: datetime) -> list[CalendarEvent]: ...

    def add_event(self, title: str, start: datetime, end: datetime) -> None: ...

    def open_reminders(self) -> list[Reminder]: ...

    def add_reminder(self, title: str, due: datetime | None) -> None: ...

    def complete_reminder(self, title: str) -> bool:
        """Marks the open reminder with exactly this title done; False when there is none."""
        ...


def local(moment: date | datetime) -> tuple[datetime, bool]:
    """(local aware time, all day) for an iCalendar DTSTART, which may be a date, a naive or an aware datetime."""
    if not isinstance(moment, datetime):
        return datetime.combine(moment, time()).astimezone(), True
    # astimezone() without a zone picks the local offset for that instant, so summer events keep summer time.
    return moment.astimezone(), False


def _summary(component) -> str:
    return str(component.get("SUMMARY") or "").strip()


def _event(component) -> CalendarEvent | None:
    """None for an event without a start, which some servers keep."""
    start = component.get("DTSTART")
    if start is None:
        return None
    begins, all_day = local(start.dt)
    return CalendarEvent(_summary(component), begins, all_day)


def _sorted(events: list[CalendarEvent]) -> list[CalendarEvent]:
    return sorted(events, key=lambda e: (e.start, not e.all_day, e.title))


class CalDAVSource:
    writable = True

    def __init__(self, url: str, username: str, password: str, calendar_name: str = ""):
        self.url = url
        self.username = username
        self.password = password
        self.calendar_name = calendar_name

    def _client(self):
        import caldav

        # A password never goes over plain HTTP, except to a server on this computer. caldav's require_tls only
        # covers its own discovery, so an http:// address is refused here.
        if not is_secure_address(self.url):
            raise CalendarError("A CalDAV address must start with https://")
        return caldav.DAVClient(url=self.url, username=self.username or None, password=self.password or None,
                                timeout=TIMEOUT_SECONDS, require_tls=not _is_loopback_http(self.url))  # fmt: skip

    def _calendars(self, client) -> list:
        from caldav.lib.error import DAVError

        try:
            calendars = client.principal().calendars()
        except DAVError:
            # The address may point at one calendar rather than the account.
            calendars = [client.calendar(url=self.url)]
        if not calendars:
            raise CalendarError("The account has no calendars")
        return calendars

    def _run(self, action):
        from caldav.lib.error import AuthorizationError, DAVError

        try:
            with self._client() as client:
                return action(client)
        except AuthorizationError as error:
            raise CalendarError("The calendar server refused the user name or password") from error
        except (DAVError, OSError, ValueError) as error:
            raise CalendarError(f"Calendar server: {type(error).__name__}: {error}") from error

    def events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        def read(client) -> list[CalendarEvent]:
            from caldav.lib.error import DAVError

            found = []
            for calendar in self._calendars(client):
                try:
                    results = calendar.search(start=start, end=end, event=True, expand=True)
                except DAVError:
                    # A task-only list can refuse event searches; the others still count.
                    log.info("Skipping a calendar that refused the search", exc_info=True)
                    continue
                for result in results:
                    event = _event(result.icalendar_component)
                    if event is not None:
                        found.append(event)
            return _sorted(found)

        return self._run(read)

    def _target(self, client, component: str):
        calendars = self._calendars(client)
        if self.calendar_name:
            for calendar in calendars:
                if (calendar.get_display_name() or "").strip().lower() == self.calendar_name.strip().lower():
                    return calendar
        for calendar in calendars:
            try:
                if component in calendar.get_supported_components():
                    return calendar
            except Exception:  # noqa: BLE001 - servers that don't answer this simply take everything
                return calendar
        return calendars[0]

    def add_event(self, title: str, start: datetime, end: datetime) -> None:
        self._run(lambda client: self._target(client, "VEVENT").save_event(dtstart=start, dtend=end, summary=title))

    def _open_todos(self, client) -> list:
        from caldav.lib.error import DAVError

        todos = []
        for calendar in self._calendars(client):
            try:
                todos.extend(calendar.search(todo=True, include_completed=False))
            except DAVError:
                continue
        return todos

    def open_reminders(self) -> list[Reminder]:
        def read(client) -> list[Reminder]:
            reminders = []
            for todo in self._open_todos(client):
                component = todo.icalendar_component
                due = component.get("DUE")
                reminders.append(Reminder(_summary(component), local(due.dt)[0] if due else None))
            return reminders

        return self._run(read)

    def add_reminder(self, title: str, due: datetime | None) -> None:
        details = {"summary": title, **({"due": due} if due else {})}
        self._run(lambda client: self._target(client, "VTODO").save_todo(**details))

    def complete_reminder(self, title: str) -> bool:
        def complete(client) -> bool:
            for todo in self._open_todos(client):
                if _summary(todo.icalendar_component) == title:
                    todo.complete()
                    return True
            return False

        return self._run(complete)


class ICSSource:
    """A published calendar address; it can be read but not changed."""

    writable = False

    def __init__(self, url: str, client: httpx.Client | None = None):
        self.url = url
        self._client = client

    def _calendar(self):
        import icalendar

        client = self._client or httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True)
        try:
            with client.stream("GET", self.url) as response:
                # A redirect must not carry the secret address over to plain HTTP.
                if response.url.scheme != "https" and not _is_loopback_http(str(response.url)):
                    raise CalendarError("The calendar address left HTTPS")
                if response.status_code != 200:
                    raise CalendarError(f"Calendar address answered {response.status_code}")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_ICS_BYTES:
                        raise CalendarError("Calendar too large")
        except httpx.HTTPError as error:
            raise CalendarError(f"Calendar address: {type(error).__name__}") from error
        finally:
            if self._client is None:
                client.close()
        try:
            return icalendar.Calendar.from_ical(bytes(body))
        except (ValueError, IndexError, KeyError) as error:
            raise CalendarError("Not an iCalendar file") from error

    def events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        import recurring_ical_events

        found = []
        for component in recurring_ical_events.of(self._calendar()).between(start, end):
            event = _event(component) if component.name == "VEVENT" else None
            if event is not None:
                found.append(event)
        return _sorted(found)

    def add_event(self, title: str, start: datetime, end: datetime) -> None:
        raise ReadOnly("An iCal address is read-only")

    def open_reminders(self) -> list[Reminder]:
        return []

    def add_reminder(self, title: str, due: datetime | None) -> None:
        raise ReadOnly("An iCal address is read-only")

    def complete_reminder(self, title: str) -> bool:
        raise ReadOnly("An iCal address is read-only")


def is_secure_address(url: str) -> bool:
    return urlsplit(url).scheme.lower() == "https" or _is_loopback_http(url)


def _is_loopback_http(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme != "http" or not parts.hostname:
        return False
    if parts.hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(parts.hostname).is_loopback
    except ValueError:
        return False
