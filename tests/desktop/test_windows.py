"""Windows desktop logic with the Windows API, COM and WinRT replaced by stand-ins, so it runs on any system."""

import asyncio
import contextlib
import json
import zlib
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from bilge import calendars
from bilge.core.language import AssistantLanguage
from bilge.core.spreadsheet.cell_reference import CellReference, SpreadsheetNumber, SpreadsheetText
from bilge.desktop import image
from bilge.desktop.base import MediaCommand, ScreenshotArea
from bilge.desktop.calc import CalcError, Location
from bilge.desktop.windows import com, office
from bilge.desktop.windows.apps import Process, StartApp, WindowsApps, belongs_to, parse_start_apps
from bilge.desktop.windows.input import WindowsClipboard, WindowsKeyboard
from bilge.desktop.windows.sound import WindowsMedia, player_name
from bilge.desktop.windows.system import WindowsScreenshots, WindowsSession, WindowsSettings
from bilge.tools.base import ToolError
from bilge.tools.desktop.mail import mail_tools

from .fakes import FakeRunner

TR = AssistantLanguage.TURKISH


def test_png_and_clipboard_bitmaps_round_trip():
    pixels = image.Pixels(2, 2, bytes([255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 10, 20, 30, 255]))
    encoded = image.png(pixels)
    assert encoded.startswith(b"\x89PNG\r\n\x1a\n")
    raw = zlib.decompress(encoded[encoded.index(b"IDAT") + 4 : encoded.index(b"IEND") - 8])
    # Each row starts with filter 0, then red, green, blue.
    assert raw == b"\x00\x00\x00\xff\x00\xff\x00" + b"\x00\xff\x00\x00\x1e\x14\x0a"
    assert image.from_dib(image.dib(pixels)) == pixels


def test_a_24_bit_snip_is_read_too():
    header = image._HEADER.pack(40, 1, 1, 1, 24, 0, 4, 0, 0, 0, 0)
    assert image.from_dib(header + bytes([1, 2, 3, 0])) == image.Pixels(1, 1, bytes([1, 2, 3, 255]))
    with pytest.raises(ValueError):
        image.from_dib(b"short")


START_APPS = json.dumps([
    {"Name": "Hesap Makinesi", "AppID": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"},
    {"Name": "Not Defteri", "AppID": "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\notepad.exe"},
    {"Name": "BENIOKU", "AppID": "{7C5A40EF-A0FB-4BFC-874A-C0F2E0B9FA8E}\\TelShop\\BENIOKU.txt"},
])  # fmt: skip


def test_start_menu_programs_without_documents():
    apps = parse_start_apps(START_APPS)
    assert [a.name for a in apps] == ["Hesap Makinesi", "Not Defteri"]
    calculator, notepad = apps
    assert calculator.package == "Microsoft.WindowsCalculator_8wekyb3d8bbwe" and calculator.program is None
    assert notepad.program == "notepad"
    store = Process(1, "CalculatorApp.exe",
                    r"C:\Program Files\WindowsApps\Microsoft.WindowsCalculator_11.2_x64__8wekyb3d8bbwe\CalculatorApp.exe")  # fmt: skip
    assert belongs_to(calculator, store) and not belongs_to(notepad, store)
    assert belongs_to(notepad, Process(2, "Notepad.exe", r"C:\Windows\notepad.exe"))


class Api:
    VK_CONTROL, VK_C, VK_SHIFT, VK_RETURN, VK_BACK = 0x11, 0x43, 0x10, 0x0D, 0x08

    def __init__(self):
        self.windows = []
        self.closed = []
        self.clipboard = "kullanıcının panosu"
        self.sequence = 1
        self.pressed = []
        self.typed = []
        self.selected = "seçili metin"

    def app_windows(self):
        return self.windows

    def close(self, window):
        self.closed.append(window)

    def clipboard_text(self):
        return self.clipboard

    def set_clipboard_text(self, text):
        self.clipboard = text
        self.sequence += 1

    def clipboard_sequence(self):
        return self.sequence

    def press(self, *keys):
        self.pressed.append(keys)
        if keys == (self.VK_CONTROL, self.VK_C) and self.selected:
            self.set_clipboard_text(self.selected)

    def type_unicode(self, text):
        self.typed.append(text)

    def foreground(self):
        return SimpleNamespace(handle=5, pid=42, title="Adsız - Not Defteri", class_name="Notepad")


def test_apps_open_through_the_start_menu_and_close_through_their_windows():
    api = Api()
    runner = FakeRunner({"powershell", "explorer.exe"}, {"powershell": START_APPS})
    windows = SimpleNamespace(handle=7, pid=99, title="Hesap Makinesi")
    processes = [Process(10, "Notepad.exe", r"C:\Windows\notepad.exe")]
    apps = WindowsApps(runner, api, processes=lambda: processes)
    calculator = next(a for a in apps.installed() if a.display_name == "Hesap Makinesi")
    apps.launch(calculator)
    assert runner.spawned == [["explorer.exe", "shell:AppsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"]]
    assert apps.running() == [] and not apps.quit(calculator)
    # A Store app's window belongs to ApplicationFrameHost but carries the app's name.
    api.windows = [windows, SimpleNamespace(handle=8, pid=10, title="Adsız - Not Defteri")]
    assert {a.display_name for a in apps.running()} == {"Hesap Makinesi", "Not Defteri"}
    assert apps.quit(calculator) and api.closed == [windows]


def test_selection_is_copied_and_the_clipboard_put_back():
    api = Api()
    clipboard = WindowsClipboard(api, process_name=lambda pid: "notepad")
    assert clipboard.selection() == "seçili metin"
    assert api.clipboard == "kullanıcının panosu"
    api.selected = ""
    assert clipboard.selection() == ""


def test_selection_is_never_copied_from_a_console():
    from bilge.desktop.process import DesktopError

    api = Api()
    with pytest.raises(DesktopError):
        WindowsClipboard(api, process_name=lambda pid: "windowsterminal").selection()
    assert api.pressed == []


def test_keyboard_types_unicode_and_names_the_front_program():
    api = Api()
    keyboard = WindowsKeyboard(api, process_name=lambda pid: "notepad")
    keyboard.type("Şeker Ünal")
    keyboard.new_line()
    keyboard.backspace(2)
    assert api.typed == ["Şeker Ünal"]
    assert api.pressed == [(Api.VK_SHIFT, Api.VK_RETURN), (Api.VK_BACK,), (Api.VK_BACK,)]
    front = keyboard.front_window()
    assert (front.name, front.app_class) == ("notepad", "notepad")


def test_media_controls_pick_the_playing_session():
    class Session:
        def __init__(self, app, status, title):
            self.source_app_user_model_id = app
            self.status, self.title, self.calls = status, title, []

        def get_playback_info(self):
            return SimpleNamespace(playback_status=self.status)

        async def try_get_media_properties_async(self):
            return SimpleNamespace(title=self.title, artist="Sezen Aksu")

        async def try_pause_async(self):
            self.calls.append("pause")
            return True

    paused, playing = Session("MSEdge", 5, "Haber"), Session("Spotify.exe", 4, "Gülümse")
    media = WindowsMedia(sessions=lambda: [paused, playing])
    now = media.now_playing()
    assert (now.player, now.playing, now.title) == ("Spotify", True, "Gülümse")
    assert media.send(MediaCommand.PAUSE) == "Spotify" and playing.calls == ["pause"]
    assert WindowsMedia(sessions=lambda: []).now_playing() is None
    assert player_name("Microsoft.ZuneMusic_8wekyb3d8bbwe!Microsoft.ZuneMusic") == "ZuneMusic"
    asyncio.set_event_loop(asyncio.new_event_loop())


class Registry:
    HKEY_CURRENT_USER, REG_DWORD = "HKCU", 4

    def __init__(self):
        self.values = {"AppsUseLightTheme": 1}

    @contextlib.contextmanager
    def OpenKey(self, root, path):  # noqa: N802 - the winreg API
        yield None

    CreateKey = OpenKey  # noqa: N815

    def QueryValueEx(self, key, name):  # noqa: N802
        return self.values[name], self.REG_DWORD

    def SetValueEx(self, key, name, _, kind, value):  # noqa: N802
        self.values[name] = value


def test_dark_mode_is_the_apps_and_system_theme_and_windows_are_told():
    told = []
    api = SimpleNamespace(announce_setting_change=told.append)
    session = WindowsSession(api, Registry())
    assert session.dark_mode() is False
    session.set_dark_mode(True)
    assert session.dark_mode() is True and told == ["ImmersiveColorSet"]
    assert session.registry.values["SystemUsesLightTheme"] == 0


def test_settings_pages_open_as_ms_settings_addresses():
    opened = []
    settings = WindowsSettings(SimpleNamespace(open=opened.append))
    assert settings.open("wifi") and not settings.open("printers")
    assert opened == ["ms-settings:network-wifi", "ms-settings:"]


def test_screenshots_and_copying_them(tmp_path):
    pixels = image.Pixels(1, 1, bytes([1, 2, 3, 255]))
    copied = []
    api = SimpleNamespace(use_physical_pixels=lambda: None, screen_rect=lambda: (0, 0, 1, 1),
                          capture=lambda *rect: pixels, set_clipboard_bitmap=copied.append)  # fmt: skip
    shots = WindowsScreenshots(SimpleNamespace(open=lambda _: None), api)
    target = tmp_path / "s.png"
    assert shots.capture(ScreenshotArea.WHOLE_SCREEN, target)
    assert target.read_bytes().startswith(b"\x89PNG")
    shots.copy_image(target)
    assert copied == [image.dib(pixels)]


@pytest.fixture
def no_com(monkeypatch):
    def call(acquire, action, keep=()):
        try:
            return action(acquire())
        except keep:
            raise
        except Exception as error:
            raise com.ComFailure(str(error)) from None

    monkeypatch.setattr(com, "call", call)


class Cell:
    def __init__(self, sheet, address):
        self.sheet, self.address = sheet, address

    @property
    def Formula(self):  # noqa: N802 - Excel's names
        return self.sheet.cells.get(self.address, "")

    @Formula.setter
    def Formula(self, value):  # noqa: N802
        self.sheet.cells[self.address] = value

    @property
    def Value2(self):  # noqa: N802
        if ":" in self.address:
            return tuple((self.sheet.number(f"B{row}"),) for row in (1, 2))
        return self.sheet.number(self.address)

    @Value2.setter
    def Value2(self, value):  # noqa: N802
        self.sheet.cells[self.address] = value

    @property
    def Text(self):  # noqa: N802
        return str(self.sheet.cells.get(self.address, ""))

    PrefixCharacter = ""  # noqa: N815

    @property
    def CountLarge(self):  # noqa: N802
        return 2 if ":" in self.address else 1

    def ClearContents(self):  # noqa: N802
        self.sheet.cells.pop(self.address, None)

    def Copy(self, destination):  # noqa: N802
        destination.Formula = self.Formula


class Sheet:
    Name = "Sayfa1"

    def __init__(self):
        self.cells = {"B1": 10.0, "B2": 2.5}
        self.UsedRange = SimpleNamespace(Row=1, Rows=SimpleNamespace(Count=2))

    def number(self, address):
        return self.cells.get(address)

    def Range(self, address):  # noqa: N802
        return Cell(self, address)


def excel_app(sheet):
    workbook = SimpleNamespace(FullName=r"C:\Users\ayse\bütçe.xlsx", Name="bütçe.xlsx",
                               Worksheets=SimpleNamespace(Item=lambda name: sheet))  # fmt: skip
    return SimpleNamespace(ActiveWorkbook=workbook, ActiveSheet=sheet,
                           Workbooks=SimpleNamespace(Item=lambda name: workbook))  # fmt: skip


def test_excel_cells_through_com(no_com):
    sheet = Sheet()
    excel = office.ExcelSheets(application=lambda: excel_app(sheet), running=lambda: True)
    at = excel.location()
    assert at == Location(r"C:\Users\ayse\bütçe.xlsx", "bütçe.xlsx", "Sayfa1", "excel")
    d1 = CellReference.parse("D1")
    excel.set_formula(at, d1, "=AVERAGE(B1,B2)")
    assert sheet.cells["D1"] == "=AVERAGE(B1,B2)"
    excel.set_value(at, d1, SpreadsheetText("007"))
    assert sheet.cells["D1"] == "'007"
    excel.set_value(at, d1, SpreadsheetNumber(1250.0))
    assert excel.formula(at, d1) == "1250"
    assert excel.values(at, "B:B") == ["10", "2.5"]
    excel.clear(at, d1)
    assert excel.shown(at, d1) == ""


def test_the_open_spreadsheet_program_is_used_and_closed_ones_are_reported(no_com):
    sheet = Sheet()
    excel = office.ExcelSheets(application=lambda: excel_app(sheet), running=lambda: True)
    closed = SimpleNamespace(is_running=lambda: False)
    apps = office.SpreadsheetApps({"excel": excel, "calc": closed})
    at = apps.location()
    assert at.app == "excel" and apps.formula(at, CellReference.parse("B2")) == "2.5"
    with pytest.raises(CalcError) as error:
        office.SpreadsheetApps({"calc": closed}).location()
    assert error.value.reason == "not_running"


class Items(list):
    def __init__(self, items):
        super().__init__(items)
        self.queries = []
        self.IncludeRecurrences = False

    def Sort(self, *args):  # noqa: N802
        pass

    def Restrict(self, query):  # noqa: N802
        self.queries.append(query)
        return Items([i for i in self if not getattr(i, "Complete", False)])

    def GetFirst(self):  # noqa: N802
        self.position = 0
        return self.GetNext()

    def GetNext(self):  # noqa: N802
        if self.position >= len(self):
            return None
        self.position += 1
        return self[self.position - 1]

    @property
    def Count(self):  # noqa: N802
        return len(self)


class Outlook:
    def __init__(self):
        start = datetime(2026, 10, 16, 10, 0)
        self.calendar = Items([SimpleNamespace(Subject="Diş hekimi", Start=start, End=start + timedelta(hours=1),
                                               AllDayEvent=False)])  # fmt: skip
        self.tasks = Items([SimpleNamespace(Subject="Süt al", DueDate=datetime(4501, 1, 1), Complete=False,
                                            MarkComplete=lambda: None)])  # fmt: skip
        self.inbox = Items([SimpleNamespace(SenderName="Ahmet", Subject="Toplantı")])
        self.sent = []

    def GetNamespace(self, _):  # noqa: N802
        folders = {office.CALENDAR: self.calendar, office.TASKS: self.tasks, office.INBOX: self.inbox}
        return SimpleNamespace(GetDefaultFolder=lambda kind: SimpleNamespace(Items=folders[kind]))

    def CreateItem(self, kind):  # noqa: N802
        outlook = self

        class Mail:
            def __init__(self):
                self.Recipients = SimpleNamespace(Add=lambda to: SimpleNamespace(
                    Resolve=lambda: to == "Ahmet", Name="Ahmet Yılmaz", Address="ahmet@example.org"))  # fmt: skip

            def Send(self):  # noqa: N802
                outlook.sent.append((self.To, self.Subject, self.Body))

            def Save(self):  # noqa: N802
                outlook.sent.append(("saved", self.Subject))

        return Mail()


def test_outlook_calendar_and_tasks(no_com):
    app = Outlook()
    source = office.OutlookCalendar(office.Outlook(application=lambda: app, date_text=lambda d: f"{d:%d.%m.%Y %H:%M}"))
    start = datetime(2026, 10, 16).astimezone()
    events = source.events(start, start + timedelta(days=1))
    assert [(e.title, e.start.hour) for e in events] == [("Diş hekimi", 10)]
    assert app.calendar.queries == ["[Start] < '17.10.2026 00:00' AND [End] > '16.10.2026 00:00'"]
    # Outlook marks "no due date" as the year 4501.
    assert source.open_reminders() == [calendars.Reminder("Süt al", None)]
    assert source.complete_reminder("Süt al") and not source.complete_reminder("Yok")


def test_outlook_not_open_is_a_calendar_error(no_com):
    source = office.OutlookCalendar(office.Outlook(application=lambda: None, running=lambda name: False))
    with pytest.raises(calendars.CalendarError):
        source.open_reminders()


def test_mail_is_read_as_untrusted_and_sent_only_to_the_resolved_recipient(no_com):
    app = Outlook()
    tools = {t.name: t for t in mail_tools(office.Outlook(application=lambda: app), TR)}
    assert tools["readMail"].untrusted_output
    assert tools["readMail"].run({}) == "1 okunmamış e-postan var. En yeniler: Ahmet: Toplantı"
    send = tools["sendEmail"]
    arguments = {"to": "Ahmet", "subject": "Yarın", "body": "Toplantı 10'da."}
    assert send.question(arguments) == (
        "Ahmet Yılmaz (ahmet@example.org) adresine 'Yarın' konulu e-postayı göndereyim mi? Metin: Toplantı 10'da."
    )
    assert send.run(arguments) == "E-postayı Ahmet Yılmaz adresine gönderdim."
    assert app.sent == [("ahmet@example.org", "Yarın", "Toplantı 10'da.")]
    assert send.question({"to": "Bilinmeyen", "body": "x"}) is None
    with pytest.raises(ToolError, match="Bilinmeyen"):
        send.run({"to": "Bilinmeyen", "body": "x"})


def test_office_start_menu_ids_name_their_program():
    assert StartApp("Excel", "Microsoft.Office.EXCEL.EXE.15").program == "excel"
    assert StartApp("Dosya Gezgini", "Microsoft.Windows.Explorer").program is None
