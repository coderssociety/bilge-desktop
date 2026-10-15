"""The clipboard, the selected text and typing on Windows. Typing sends each character as itself (Unicode input), so
"ŞĞÜİ" come out right on any keyboard layout."""

import time
from pathlib import PureWindowsPath

from bilge.desktop.base import FrontWindow
from bilge.desktop.process import DesktopError

# How long an app gets to put its selection on the clipboard after Ctrl+C.
_COPY_WAIT_SECONDS = 0.6
# In a console Ctrl+C stops the running program instead of copying.
CONSOLES = frozenset(
    {
        "cmd", "powershell", "pwsh", "windowsterminal", "wt", "conhost", "openconsole", "mintty", "wsl", "bash",
        "conemu64", "conemu", "cmder", "putty", "mobaxterm", "consolewindowclass", "cascadia_hosting_window_class",
    }
)  # fmt: skip


def _default_api():
    from bilge.desktop.windows import win32

    return win32


class WindowsClipboard:
    def __init__(self, api=None, process_name=None):
        self._api = api
        self._process_name = process_name or _process_name

    @property
    def api(self):
        self._api = self._api or _default_api()
        return self._api

    def _program(self, pid: int) -> str:
        try:
            return self._process_name(pid)
        except DesktopError:
            return ""

    def read(self) -> str:
        return self.api.clipboard_text()

    def write(self, text: str) -> None:
        self.api.set_clipboard_text(text)

    def selection(self) -> str:
        """Windows keeps no separate selection, so the app in front is asked to copy it; the user's clipboard is
        put back afterwards."""
        api = self.api
        window = api.foreground()
        if window is None:
            return ""
        if window.class_name.lower() in CONSOLES or self._program(window.pid) in CONSOLES:
            raise DesktopError("Ctrl+C in a console would stop the program running there")
        saved = api.clipboard_text()
        before = api.clipboard_sequence()
        api.press(api.VK_CONTROL, api.VK_C)
        deadline = time.monotonic() + _COPY_WAIT_SECONDS
        while api.clipboard_sequence() == before and time.monotonic() < deadline:
            time.sleep(0.03)
        if api.clipboard_sequence() == before:
            return ""
        copied = api.clipboard_text()
        if saved:
            api.set_clipboard_text(saved)
        return copied


class WindowsKeyboard:
    def __init__(self, api=None, process_name=None):
        self._api = api
        self._process_name = process_name or _process_name

    @property
    def api(self):
        self._api = self._api or _default_api()
        return self._api

    def front_window(self) -> FrontWindow | None:
        window = self.api.foreground()
        if window is None:
            return None
        program = self._process_name(window.pid)
        return FrontWindow(program, window.title, window.class_name.lower())

    def type(self, text: str) -> None:
        self.api.type_unicode(text)

    def new_line(self) -> None:
        self.api.press(self.api.VK_SHIFT, self.api.VK_RETURN)

    def backspace(self, count: int) -> None:
        for _ in range(max(0, count)):
            self.api.press(self.api.VK_BACK)
            time.sleep(0.008)


def _process_name(pid: int) -> str:
    """ "WindowsTerminal.exe" → "windowsterminal"."""
    import psutil

    try:
        name = psutil.Process(pid).name()
    except (psutil.Error, OSError) as error:
        raise DesktopError(f"No process {pid}") from error
    return PureWindowsPath(name).stem.lower()
