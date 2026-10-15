"""The Windows desktop: the Start menu, Core Audio, the system media controls, Unicode keyboard input, and Office
over COM."""

from bilge.desktop.base import Desktop
from bilge.desktop.process import Runner
from bilge.desktop.windows.apps import WindowsApps
from bilge.desktop.windows.input import WindowsClipboard, WindowsKeyboard
from bilge.desktop.windows.sound import WindowsMedia, WindowsVolume
from bilge.desktop.windows.system import (
    WindowsFolders,
    WindowsNetwork,
    WindowsNotifier,
    WindowsOpener,
    WindowsScreenshots,
    WindowsSession,
    WindowsSettings,
)


def build() -> Desktop:
    runner = Runner()
    opener = WindowsOpener(runner)
    return Desktop(
        apps=WindowsApps(runner),
        volume=WindowsVolume(),
        media=WindowsMedia(),
        clipboard=WindowsClipboard(),
        keyboard=WindowsKeyboard(),
        session=WindowsSession(),
        network=WindowsNetwork(),
        screenshots=WindowsScreenshots(opener),
        settings=WindowsSettings(opener),
        opener=opener,
        notifier=WindowsNotifier(),
        folders=WindowsFolders(),
    )
