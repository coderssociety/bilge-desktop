"""The Linux desktop: freedesktop.org standards first (D-Bus, .desktop files, MPRIS), then the usual tools of GNOME,
KDE and the wlroots compositors."""

from bilge.desktop.base import Desktop
from bilge.desktop.linux import environment
from bilge.desktop.linux.apps import LinuxApps
from bilge.desktop.linux.audio import LinuxVolume
from bilge.desktop.linux.clipboard import LinuxClipboard
from bilge.desktop.linux.dbus import SessionBus
from bilge.desktop.linux.keyboard import LinuxKeyboard
from bilge.desktop.linux.media import MprisMedia
from bilge.desktop.linux.system import (
    LinuxFolders,
    LinuxNetwork,
    LinuxNotifier,
    LinuxOpener,
    LinuxScreenshots,
    LinuxSession,
    LinuxSettings,
)
from bilge.desktop.process import Runner


def build(languages: tuple[str, ...]) -> Desktop:
    runner = Runner()
    env = environment.current()
    bus = SessionBus()
    clipboard = LinuxClipboard(runner, env)
    return Desktop(
        apps=LinuxApps(runner, languages),
        volume=LinuxVolume(runner),
        media=MprisMedia(bus),
        clipboard=clipboard,
        keyboard=LinuxKeyboard(runner, env, clipboard),
        session=LinuxSession(runner, env),
        network=LinuxNetwork(runner),
        screenshots=LinuxScreenshots(runner, env),
        settings=LinuxSettings(runner, env),
        opener=LinuxOpener(runner, bus),
        notifier=LinuxNotifier(runner, bus),
        folders=LinuxFolders(),
    )
