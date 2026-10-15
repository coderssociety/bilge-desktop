"""Microsoft Excel and Outlook, driven over COM while they are open. They are never started by Bilge."""

from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from typing import Any

from bilge import calendars
from bilge.core.spreadsheet.cell_reference import CellReference, SpreadsheetNumber, SpreadsheetValue
from bilge.desktop.calc import MAX_CELLS, CalcError, Location
from bilge.desktop.windows import com

EXCEL, OUTLOOK = "Excel.Application", "Outlook.Application"
# Outlook's default folders and item kinds.
INBOX, CALENDAR, TASKS = 6, 9, 13
MAIL_ITEM, APPOINTMENT_ITEM, TASK_ITEM = 0, 1, 3
# Outlook writes "no date" as 1 January 4501.
_NO_DATE_YEAR = 4000
_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"


class OfficeError(Exception):
    """`reason`: "not_running", "new_outlook" (the new Outlook has no COM), or "failed"."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


def active(prog_id: str):
    """The running program, or None."""
    import comtypes.client

    try:
        return comtypes.client.GetActiveObject(prog_id, dynamic=True)
    except Exception:  # noqa: BLE001 - not running, or not registered: either way there is nothing to talk to
        return None


def is_running(executable: str) -> bool:
    import psutil

    return any((p.info.get("name") or "").lower() == executable for p in psutil.process_iter(["name"]))


def cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(int(value)) if value.is_integer() and abs(value) < 1e15 else repr(value)
    return str(value)


def whole_second(moment: datetime) -> datetime:
    """COM dates arrive as fractions of a day, so 14:05 can come back as 14:04:59.999999."""
    return (moment + timedelta(milliseconds=500)).replace(microsecond=0)


def each(items) -> Iterator[Any]:
    """Outlook's own way through a collection; Python iteration over a dynamic COM object is less dependable."""
    item = items.GetFirst()
    while item is not None:
        yield item
        item = items.GetNext()


class ExcelSheets:
    """The same operations as the LibreOffice bridge, for the workbook open in Excel."""

    def __init__(self, application: Callable[[], Any] | None = None, running: Callable[[], bool] | None = None):
        self._application = application or (lambda: active(EXCEL))
        self._running = running or (lambda: is_running("excel.exe"))

    def is_running(self) -> bool:
        return self._running()

    def _call(self, action):
        def run(excel):
            if excel is None:
                raise CalcError("not_running")
            return action(excel)

        try:
            return com.call(self._application, run, keep=(CalcError,))
        except com.ComFailure as error:
            raise CalcError("failed", str(error)) from None

    def location(self) -> Location | None:
        def read(excel):
            workbook = excel.ActiveWorkbook
            if workbook is None:
                return None
            return Location(str(workbook.FullName), str(workbook.Name), str(excel.ActiveSheet.Name), "excel")

        return self._call(read)

    @staticmethod
    def _sheet(excel, at: Location):
        try:
            return excel.Workbooks.Item(at.title).Worksheets.Item(at.sheet)
        except Exception as error:  # noqa: BLE001 - a closed workbook or a renamed sheet
            raise CalcError("no_document") from error

    def _cell(self, at: Location, cell: CellReference, action):
        return self._call(lambda excel: action(self._sheet(excel, at).Range(cell.address)))

    def formula(self, at: Location, cell: CellReference) -> str:
        def read(target) -> str:
            # Text typed as "'007" keeps its apostrophe here, so undo writes it back as text, not as the number 7.
            prefix = "'" if str(target.PrefixCharacter or "") == "'" else ""
            return prefix + cell_text(target.Formula)

        return self._cell(at, cell, read)

    def shown(self, at: Location, cell: CellReference) -> str:
        return self._cell(at, cell, lambda target: str(target.Text or ""))

    def set_formula(self, at: Location, cell: CellReference, formula: str) -> None:
        # Excel takes English function names and commas here whatever its own language.
        self._cell(at, cell, lambda target: setattr(target, "Formula", formula))

    def restore(self, at: Location, cell: CellReference, content: str) -> None:
        self.set_formula(at, cell, content)

    def set_value(self, at: Location, cell: CellReference, value: SpreadsheetValue) -> None:
        # Spoken text stays text: the apostrophe keeps Excel from reading "007" as 7, "1/2" as a date or "=" as a formula.
        written: Any = value.value if isinstance(value, SpreadsheetNumber) else "'" + value.value
        self._cell(at, cell, lambda target: setattr(target, "Value2", written))

    def clear(self, at: Location, cell: CellReference) -> None:
        self._cell(at, cell, lambda target: target.ClearContents())

    def copy(self, at: Location, source: CellReference, destination: CellReference) -> None:
        def act(excel):
            sheet = self._sheet(excel, at)
            sheet.Range(source.address).Copy(Destination=sheet.Range(destination.address))

        self._call(act)

    def values(self, at: Location, reference: str) -> list[str]:
        def read(excel):
            sheet = self._sheet(excel, at)
            address = reference
            if not any(character.isdigit() for character in reference):
                used = sheet.UsedRange
                rows = int(used.Row) + int(used.Rows.Count) - 1
                first, _, last = reference.partition(":")
                address = f"{first}1:{last or first}{rows}"
            selected = sheet.Range(address)
            # Counted before reading, so a huge range is refused instead of copied over.
            if int(selected.CountLarge) > MAX_CELLS:
                raise CalcError("too_large")
            found = selected.Value2
            cells = [item for row in found for item in row] if isinstance(found, tuple) else [found]
            return [cell_text(item) for item in cells]

        return self._call(read)


class SpreadsheetApps:
    """Whichever spreadsheet program is open: Excel first, then LibreOffice Calc."""

    def __init__(self, apps: dict[str, Any]):
        self.apps = apps

    def location(self) -> Location | None:
        running = [(name, app) for name, app in self.apps.items() if app.is_running()]
        if not running:
            raise CalcError("not_running")
        for name, app in running:
            try:
                found = app.location()
            except CalcError as error:
                # Excel run as administrator can't be reached from Bilge; an open Calc still can.
                if error.reason == "not_running":
                    continue
                raise
            if found is not None:
                return Location(found.document, found.title, found.sheet, name)
        return None

    def __getattr__(self, operation: str):
        if operation not in ("formula", "shown", "set_formula", "restore", "set_value", "clear", "copy", "values"):
            raise AttributeError(operation)

        def dispatch(at: Location, *args):
            return getattr(self.apps[at.app], operation)(at, *args)

        return dispatch


class Outlook:
    def __init__(
        self,
        application: Callable[[], Any] | None = None,
        date_text: Callable[[datetime], str] | None = None,
        running: Callable[[str], bool] | None = None,
    ):
        self._application = application or (lambda: active(OUTLOOK))
        self._date_text = date_text
        self._running = running or is_running

    def call(self, action):
        def run(outlook):
            if outlook is None:
                # The new Outlook (olk.exe) can't be driven from outside at all.
                new = self._running("olk.exe") and not self._running("outlook.exe")
                raise OfficeError("new_outlook" if new else "not_running")
            return action(outlook)

        try:
            return com.call(self._application, run, keep=(OfficeError,))
        except com.ComFailure as error:
            raise OfficeError("failed", str(error)) from None

    def folder(self, outlook, kind: int):
        return outlook.GetNamespace("MAPI").GetDefaultFolder(kind)

    def filter_date(self, moment: datetime) -> str:
        if self._date_text is None:
            from bilge.desktop.windows import win32

            self._date_text = win32.short_date_time
        return self._date_text(moment)


def smtp_address(recipient) -> str | None:
    """An Exchange recipient's Address is an internal name ("/o=ExchangeLabs/…"); what the user must hear is the
    e-mail address."""
    address = str(recipient.Address or "")
    if "@" in address:
        return address
    entry = recipient.AddressEntry
    for get in (lambda: entry.GetExchangeUser().PrimarySmtpAddress,
                lambda: recipient.PropertyAccessor.GetProperty(_SMTP_ADDRESS)):  # fmt: skip
        try:
            found = str(get() or "")
        except Exception:  # noqa: BLE001 - not an Exchange user, or the property isn't there
            continue
        if "@" in found:
            return found
    return None


class OutlookCalendar:
    """Outlook's calendar and tasks as the assistant's calendar and reminders."""

    writable = True

    def __init__(self, outlook: Outlook):
        self.outlook = outlook

    def _guarded(self, action):
        try:
            return self.outlook.call(action)
        except OfficeError as error:
            raise calendars.CalendarError(f"Outlook: {error}") from error

    def events(self, start: datetime, end: datetime) -> list[calendars.CalendarEvent]:
        outlook = self.outlook

        def read(app):
            items = outlook.folder(app, CALENDAR).Items
            # Repeating events are only expanded on a sorted list with IncludeRecurrences, then filtered.
            items.Sort("[Start]")
            items.IncludeRecurrences = True
            local_start, local_end = start.astimezone().replace(tzinfo=None), end.astimezone().replace(tzinfo=None)
            query = f"[Start] < '{outlook.filter_date(local_end)}' AND [End] > '{outlook.filter_date(local_start)}'"
            found = []
            for item in each(items.Restrict(query)):
                if not isinstance(item.Start, datetime):
                    continue
                begins, finishes = whole_second(item.Start).astimezone(), whole_second(item.End).astimezone()
                # Checked here as well: the filter's date format depends on Windows' regional settings.
                if begins >= end or finishes <= start:
                    continue
                found.append(calendars.CalendarEvent(str(item.Subject or ""), begins, bool(item.AllDayEvent)))
            return sorted(found, key=lambda e: (e.start, not e.all_day, e.title))

        return self._guarded(read)

    def add_event(self, title: str, start: datetime, end: datetime) -> None:
        def add(app):
            item = app.CreateItem(APPOINTMENT_ITEM)
            item.Subject = title
            item.Start = start.astimezone().replace(tzinfo=None)
            item.End = end.astimezone().replace(tzinfo=None)
            item.Save()

        self._guarded(add)

    def _open_tasks(self, app) -> list:
        return list(each(self.outlook.folder(app, TASKS).Items.Restrict("[Complete] = False")))

    def open_reminders(self) -> list[calendars.Reminder]:
        def read(app):
            reminders = []
            for task in self._open_tasks(app):
                due = task.DueDate if isinstance(task.DueDate, datetime) and task.DueDate.year < _NO_DATE_YEAR else None
                reminders.append(
                    calendars.Reminder(str(task.Subject or ""), whole_second(due).astimezone() if due else None)
                )
            return reminders

        return self._guarded(read)

    def add_reminder(self, title: str, due: datetime | None) -> None:
        def add(app):
            task = app.CreateItem(TASK_ITEM)
            task.Subject = title
            if due is not None:
                local = due.astimezone().replace(tzinfo=None)
                task.DueDate = local
                task.ReminderSet = True
                task.ReminderTime = local
            task.Save()

        self._guarded(add)

    def complete_reminder(self, title: str) -> bool:
        def complete(app) -> bool:
            for task in self._open_tasks(app):
                if str(task.Subject or "") == title:
                    task.MarkComplete()
                    return True
            return False

        return self._guarded(complete)
