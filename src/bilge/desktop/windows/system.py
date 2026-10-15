"""Locking, sleep, light and dark theme, Wi-Fi, settings pages, screenshots, notifications, folders and opening
things on Windows."""

import asyncio
import contextlib
import os
import time
from pathlib import Path
from xml.sax.saxutils import escape

from bilge.desktop import image
from bilge.desktop.base import ScreenshotArea
from bilge.desktop.process import DesktopError, MissingProgram, Runner

_THEME_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
# The selection is drawn by the Snipping Tool, which puts the result on the clipboard.
_SELECTION_SECONDS = 30
# Until the installer registers Bilge's own, notifications go out under PowerShell's app id, which every Windows has.
POWERSHELL_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
_FOLDERS = {
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
}
_SETTINGS_PAGES = {
    "wifi": "network-wifi", "bluetooth": "bluetooth", "network": "network-status", "sound": "sound",
    "displays": "display", "battery": "batterysaver", "notifications": "notifications", "focus": "quiethours",
    "privacy": "privacy", "keyboard": "typing", "general": "about", "wallpaper": "personalization-background",
    "softwareUpdate": "windowsupdate", "storage": "storagesense", "accessibility": "easeofaccess",
    "mouse": "mousetouchpad", "trackpad": "devices-touchpad",
}  # fmt: skip


def _api():
    from bilge.desktop.windows import win32

    return win32


class WindowsSession:
    def __init__(self, api=None, registry=None):
        self._api = api
        self._registry = registry

    @property
    def api(self):
        self._api = self._api or _api()
        return self._api

    @property
    def registry(self):
        if self._registry is None:
            import winreg

            self._registry = winreg
        return self._registry

    def lock(self) -> None:
        self.api.lock()

    def suspend(self) -> None:
        self.api.suspend()

    def dark_mode(self) -> bool | None:
        reg = self.registry
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, _THEME_KEY) as key:
                return reg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
        except OSError:
            return None

    def set_dark_mode(self, dark: bool) -> None:
        reg = self.registry
        try:
            with reg.CreateKey(reg.HKEY_CURRENT_USER, _THEME_KEY) as key:
                for name in ("AppsUseLightTheme", "SystemUsesLightTheme"):
                    reg.SetValueEx(key, name, 0, reg.REG_DWORD, 0 if dark else 1)
        except OSError as error:
            raise DesktopError(f"Could not change the theme: {error}") from error
        self.api.announce_setting_change("ImmersiveColorSet")


class WindowsNetwork:
    """Wi-Fi through the radio switch Windows shows in its quick settings; it needs no administrator rights."""

    def __init__(self, radios=None):
        self._radios = radios

    async def _wifi(self):
        if self._radios is not None:
            return list(self._radios())
        try:
            from winrt.windows.devices.radios import Radio, RadioKind
        except ImportError as error:
            raise MissingProgram("winrt-Windows.Devices.Radios") from error
        await Radio.request_access_async()
        return [radio for radio in await Radio.get_radios_async() if radio.kind == RadioKind.WI_FI]

    def wifi_enabled(self) -> bool | None:
        async def read():
            radios = await self._wifi()
            return int(radios[0].state) == 1 if radios else None

        try:
            return asyncio.run(read())
        except (DesktopError, OSError):
            return None

    def set_wifi(self, enabled: bool) -> None:
        async def change():
            radios = await self._wifi()
            if not radios:
                raise DesktopError("No Wi-Fi radio")
            for radio in radios:
                # RadioState: 1 is on, 2 is off.
                result = await radio.set_state_async(1 if enabled else 2)
                if int(result) != 1:
                    raise DesktopError(f"Wi-Fi refused the change: {int(result)}")

        try:
            asyncio.run(change())
        except OSError as error:
            raise DesktopError(f"Wi-Fi: {error}") from error


class WindowsScreenshots:
    def __init__(self, opener, api=None):
        self._opener = opener
        self._api = api
        # The last capture's pixels, so copying it needs no PNG decoder.
        self._last: tuple[Path, image.Pixels] | None = None

    @property
    def api(self):
        self._api = self._api or _api()
        return self._api

    def capture(self, area: ScreenshotArea, destination: Path) -> bool:
        api = self.api
        api.use_physical_pixels()
        if area is ScreenshotArea.SELECTION:
            pixels = self._snip()
            if pixels is None:
                return False
        else:
            window = api.foreground() if area is ScreenshotArea.FRONT_WINDOW else None
            rect = api.window_rect(window) if window is not None else api.screen_rect()
            pixels = api.capture(*rect)
        destination.write_bytes(image.png(pixels))
        self._last = (destination, pixels)
        return True

    def _snip(self) -> image.Pixels | None:
        api = self.api
        before = api.clipboard_sequence()
        self._opener.open("ms-screenclip:")
        deadline = time.monotonic() + _SELECTION_SECONDS
        while time.monotonic() < deadline:
            time.sleep(0.25)
            if api.clipboard_sequence() != before:
                data = api.clipboard_bitmap()
                if not data:
                    # Something other than a picture was copied meanwhile: the snip was given up.
                    return None
                try:
                    return image.from_dib(data)
                except ValueError as error:
                    raise DesktopError(f"Unreadable snip: {error}") from error
        return None

    def copy_image(self, picture: Path) -> None:
        if self._last is None or self._last[0] != picture:
            raise DesktopError("Only the screenshot just taken can be copied")
        pixels, self._last = self._last[1], None
        self.api.set_clipboard_bitmap(image.dib(pixels))


class WindowsSettings:
    def __init__(self, opener):
        self._opener = opener

    def open(self, pane: str) -> bool:
        page = _SETTINGS_PAGES.get(pane)
        self._opener.open(f"ms-settings:{page or ''}")
        return page is not None


class WindowsOpener:
    def __init__(self, runner: Runner, start=None):
        self._runner = runner
        self._start = start or getattr(os, "startfile", None)

    def open(self, target: str) -> None:
        if self._start is None:
            raise MissingProgram("os.startfile")
        try:
            self._start(target)
        except OSError as error:
            raise DesktopError(f"Could not open: {error}") from error

    def reveal(self, path: Path) -> None:
        # One argument, as Explorer expects it: "/select,C:\path\file".
        self._runner.spawn(["explorer.exe", f"/select,{path}"])


class WindowsNotifier:
    def __init__(self, app_id: str = POWERSHELL_APP_ID):
        self._app_id = app_id

    def notify(self, title: str, body: str) -> None:
        try:
            from winrt.windows.data.xml.dom import XmlDocument
            from winrt.windows.ui.notifications import ToastNotification, ToastNotificationManager
        except ImportError as error:
            raise MissingProgram("winrt-Windows.UI.Notifications") from error
        document = XmlDocument()
        try:
            document.load_xml(
                "<toast><visual><binding template='ToastGeneric'>"
                f"<text>{escape(_printable(title))}</text><text>{escape(_printable(body))}</text>"
                "</binding></visual></toast>"
            )
            # pywinrt names the overload that takes an app id on its own.
            notifier = ToastNotificationManager.create_toast_notifier_with_id(self._app_id)
            notifier.show(ToastNotification(document))
        except OSError as error:
            raise DesktopError(f"Notification: {error}") from error


def _printable(text: str) -> str:
    """XML can't carry control characters, which a reminder's text may hold."""
    return "".join(c if c.isprintable() or c == " " else " " for c in text)


class WindowsFolders:
    def __init__(self, api=None):
        self._api = api

    def _known(self, name: str, fallback: str) -> Path:
        self._api = self._api or _api()
        with contextlib.suppress(DesktopError):
            return self._api.known_folder(_FOLDERS[name])
        return Path.home() / fallback

    def home(self) -> Path:
        return Path.home()

    def desktop(self) -> Path:
        return self._known("desktop", "Desktop")

    def downloads(self) -> Path:
        return self._known("downloads", "Downloads")

    def documents(self) -> Path:
        return self._known("documents", "Documents")

    def pictures(self) -> Path:
        return self._known("pictures", "Pictures")
