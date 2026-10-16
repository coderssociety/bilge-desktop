"""A system-wide shortcut that makes Bilge listen, as saying its name does.

Windows registers it with RegisterHotKey; an X11 session grabs the key on the root window; a Wayland session lets no
program read the keyboard, so the desktop portal is asked, and the desktop shows its own approval. Where none of these
works, `Bilge --listen` does the same, for a shortcut set in the desktop's own keyboard settings.
"""

import os
import sys
from collections.abc import Callable
from typing import Protocol

from bilge.desktop.hotkey.shortcut import InvalidShortcut, Shortcut, parse


class HotkeyError(Exception):
    """`reason`: "invalid" (not a usable combination), "taken" (another program has it), "unsupported" (this
    desktop offers no way), "declined" (the user refused it in the desktop's dialog)."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


class GlobalHotkey(Protocol):
    shortcut: Shortcut

    def stop(self) -> None: ...


def is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE") == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))


def register(text: str, pressed: Callable[[], None], lost: Callable[[], None] = lambda: None) -> GlobalHotkey:
    """`pressed` is called on a background thread each time the shortcut is pressed; `lost`, if the desktop stops
    delivering it (the portal's connection dropped)."""
    try:
        shortcut = parse(text)
    except InvalidShortcut as error:
        raise HotkeyError("invalid", text) from error
    if sys.platform == "win32":
        from bilge.desktop.hotkey.windows import WindowsHotkey

        return WindowsHotkey(shortcut, pressed)
    if sys.platform.startswith("linux"):
        if is_wayland():
            from bilge.desktop.hotkey.portal import PortalHotkey

            return PortalHotkey(shortcut, pressed, lost=lost)
        if os.environ.get("DISPLAY"):
            from bilge.desktop.hotkey.x11 import X11Hotkey

            return X11Hotkey(shortcut, pressed)
    raise HotkeyError("unsupported", sys.platform)


__all__ = ["GlobalHotkey", "HotkeyError", "Shortcut", "is_wayland", "parse", "register"]
