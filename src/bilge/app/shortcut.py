"""Keeps the listening shortcut registered with the system while Bilge runs, and names the command a desktop
shortcut can run instead where Bilge cannot have one of its own."""

import os
import shlex
import sys
import threading

from PySide6.QtCore import QObject, Signal

from bilge.app import worker
from bilge.desktop import hotkey


def listen_command() -> str:
    """How to run `Bilge --listen` on this computer."""
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        program = appimage
    elif getattr(sys, "frozen", False):
        program = sys.executable
    else:
        return "bilge-app --listen"
    if sys.platform == "win32":
        return f'"{program}" --listen'
    return f"{shlex.quote(program)} --listen"


class ListeningShortcut(QObject):
    pressed = Signal()
    # The HotkeyError reason: "invalid", "taken", "unsupported", "declined".
    failed = Signal(str)
    # From the shortcut's own thread: the desktop stopped delivering it.
    _lost = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._hotkey: hotkey.GlobalHotkey | None = None
        self.text = ""
        self._registering = False
        # Bumped by every change, so a registration that finishes after a newer one is let go.
        self._generation = 0
        self._lost.connect(self._on_lost)

    @property
    def is_active(self) -> bool:
        return self._hotkey is not None

    def apply(self, text: str) -> None:
        """Registers `text` ("Ctrl+Alt+B") in place of the current shortcut; empty removes it. Registering may wait
        on the desktop's approval dialog, so it happens off the window thread, and the same shortcut is not asked
        for twice."""
        if text and text == self.text and (self._hotkey is not None or self._registering):
            return
        self.release()
        self.text = text
        if not text:
            return
        generation = self._generation
        self._registering = True

        def register():
            try:
                return hotkey.register(text, self.pressed.emit, lambda: self._lost.emit(generation)), ""
            except hotkey.HotkeyError as error:
                return None, error.reason

        def done(result) -> None:
            found, reason = result
            if generation != self._generation:
                if found is not None:
                    found.stop()
                return
            self._registering = False
            if found is None:
                self.failed.emit(reason)
                return
            self._hotkey = found

        def broken(_: str) -> None:
            if generation == self._generation:
                self._registering = False
                self.failed.emit("unsupported")

        worker.run(register, done, broken, owner=self)

    def _on_lost(self, generation: int) -> None:
        if generation == self._generation and self._hotkey is not None:
            self._hotkey = None
            self.failed.emit("unsupported")

    def release(self) -> None:
        self._generation += 1
        self._registering = False
        self.text = ""
        found, self._hotkey = self._hotkey, None
        if found is not None:
            # Stopping waits on the shortcut's thread, and on the desktop portal; not on the window thread.
            threading.Thread(target=found.stop, name="bilge-hotkey-stop", daemon=True).start()
