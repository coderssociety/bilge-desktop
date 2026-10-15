"""Installed applications from the Start menu (desktop programs and Store apps alike), opened the way the Start
menu does, and closed like clicking their close button, so they can still ask to save."""

import json
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import PureWindowsPath

from bilge.core.text import folded
from bilge.desktop.base import AppEntry
from bilge.desktop.process import DesktopError, Runner

# Start menu entries that are documents or links, not programs.
_DOCUMENT_SUFFIXES = (".txt", ".url", ".pdf", ".htm", ".html", ".chm", ".rtf", ".lnk", ".ini")
_KNOWN_FOLDER = re.compile(r"^\{[0-9A-Fa-f-]{36}\}\\")
REFRESH_SECONDS = 300
_LIST_APPS = "[Console]::OutputEncoding = [Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"


@dataclass(frozen=True)
class StartApp:
    name: str
    app_id: str

    @property
    def is_store_app(self) -> bool:
        return "!" in self.app_id and "\\" not in self.app_id

    @property
    def program(self) -> str | None:
        """The program's file name without .exe ("notepad"), for desktop programs."""
        if self.is_store_app:
            return None
        name = PureWindowsPath(_KNOWN_FOLDER.sub("", self.app_id)).name.lower()
        if name.endswith(".exe"):
            return name.removesuffix(".exe")
        # Office registers ids like "Microsoft.Office.EXCEL.EXE.15".
        parts = self.app_id.lower().split(".")
        return parts[parts.index("exe") - 1] if "exe" in parts[1:] else None

    @property
    def package(self) -> str | None:
        """ "Microsoft.WindowsCalculator_8wekyb3d8bbwe" for Store apps; their processes run from a folder named after
        it ("…\\WindowsApps\\Microsoft.WindowsCalculator_11.2_x64__8wekyb3d8bbwe")."""
        return self.app_id.split("!", 1)[0] if self.is_store_app else None


@dataclass(frozen=True)
class Process:
    pid: int
    name: str
    path: str


def parse_start_apps(output: str) -> list[StartApp]:
    data = json.loads(output) if output.strip() else []
    if isinstance(data, dict):
        data = [data]
    apps = []
    for item in data:
        name, app_id = str(item.get("Name") or "").strip(), str(item.get("AppID") or "").strip()
        if name and app_id and not app_id.lower().endswith(_DOCUMENT_SUFFIXES):
            apps.append(StartApp(name, app_id))
    return apps


def belongs_to(app: StartApp, process: Process) -> bool:
    if app.package:
        family, _, publisher = app.package.partition("_")
        folder = PureWindowsPath(process.path).parent.name
        return folder.startswith(family + "_") and folder.endswith("_" + publisher)
    return app.program is not None and process.name.lower().removesuffix(".exe") == app.program


class WindowsApps:
    def __init__(
        self,
        runner: Runner,
        api=None,
        processes: Callable[[], Iterable[Process]] | None = None,
    ):
        self._runner = runner
        self._api = api
        self._processes = processes or _processes
        self._apps: dict[str, StartApp] | None = None
        self._read_at = 0.0

    @property
    def api(self):
        if self._api is None:
            from bilge.desktop.windows import win32

            self._api = win32
        return self._api

    def _start_apps(self) -> dict[str, StartApp]:
        # Read again now and then, so newly installed apps are found without restarting Bilge.
        if self._apps is None or time.monotonic() - self._read_at > REFRESH_SECONDS:
            self._read_at = time.monotonic()
            output = self._runner.check(["powershell", "-NoProfile", "-NonInteractive", "-Command", _LIST_APPS],
                                        timeout=30)  # fmt: skip
            try:
                self._apps = {app.app_id: app for app in parse_start_apps(output)}
            except ValueError as error:
                raise DesktopError(f"Unreadable Start menu list: {error}") from error
        return self._apps

    def installed(self) -> list[AppEntry]:
        return [self._entry(app) for app in self._start_apps().values()]

    @staticmethod
    def _entry(app: StartApp) -> AppEntry:
        names = tuple(dict.fromkeys(n for n in (app.name, app.program) if n))
        return AppEntry(app.app_id, app.name, names)

    def launch(self, app: AppEntry) -> None:
        # The Start menu's own way of starting anything it lists, Store apps included.
        self._runner.spawn(["explorer.exe", f"shell:AppsFolder\\{app.id}"])

    def _windows_of(self, app: StartApp) -> list:
        processes = {p.pid: p for p in self._processes()}
        windows = []
        for window in self.api.app_windows():
            process = processes.get(window.pid)
            # Store apps draw inside ApplicationFrameHost, whose window carries the app's name as its title.
            if (process and belongs_to(app, process)) or folded(window.title) == folded(app.name):
                windows.append(window)
        return windows

    def running(self) -> list[AppEntry]:
        return [self._entry(app) for app in self._start_apps().values() if self._windows_of(app)]

    def quit(self, app: AppEntry) -> bool:
        found = self._start_apps().get(app.id)
        windows = self._windows_of(found) if found else []
        for window in windows:
            self.api.close(window)
        return bool(windows)


def _processes() -> Iterable[Process]:
    import psutil

    for process in psutil.process_iter(["pid", "name", "exe"]):
        info = process.info
        yield Process(info["pid"], info.get("name") or "", info.get("exe") or "")
