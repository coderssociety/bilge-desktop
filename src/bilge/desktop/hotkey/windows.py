"""RegisterHotKey on a thread of its own: Windows posts WM_HOTKEY to the message queue of the thread that registered
the key, so that thread waits on its queue for as long as the shortcut is wanted."""

import ctypes
import logging
import threading
from collections.abc import Callable
from ctypes import wintypes

from bilge.desktop.hotkey import HotkeyError
from bilge.desktop.hotkey.shortcut import Shortcut

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
PM_NOREMOVE = 0
ERROR_HOTKEY_ALREADY_REGISTERED = 1409
HOTKEY_ID = 1
READY_SECONDS = 5
_MASKS = {"alt": MOD_ALT, "ctrl": MOD_CONTROL, "shift": MOD_SHIFT, "meta": MOD_WIN}

user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
                                wintypes.UINT]  # fmt: skip
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]


class WindowsHotkey:
    def __init__(self, shortcut: Shortcut, pressed: Callable[[], None]):
        self.shortcut = shortcut
        self._pressed = pressed
        self._ready = threading.Event()
        self._error: HotkeyError | None = None
        self._thread_id = 0
        self._thread = threading.Thread(target=self._run, name="bilge-hotkey", daemon=True)
        self._thread.start()
        if not self._ready.wait(READY_SECONDS):
            raise HotkeyError("unsupported", "RegisterHotKey did not answer")
        if self._error is not None:
            raise self._error

    def _run(self) -> None:
        message = wintypes.MSG()
        # The thread has a message queue only once it asks for a message; stop() posts to that queue.
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, PM_NOREMOVE)
        self._thread_id = kernel32.GetCurrentThreadId()
        modifiers = MOD_NOREPEAT
        for name in self.shortcut.modifiers:
            modifiers |= _MASKS[name]
        if not user32.RegisterHotKey(None, HOTKEY_ID, modifiers, self.shortcut.windows_key):
            error = ctypes.get_last_error()
            reason = "taken" if error == ERROR_HOTKEY_ALREADY_REGISTERED else "unsupported"
            self._error = HotkeyError(reason, f"{self.shortcut.text} (error {error})")
            self._ready.set()
            return
        self._ready.set()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == WM_HOTKEY and message.wParam == HOTKEY_ID:
                    try:
                        self._pressed()
                    except Exception:
                        log.exception("The shortcut's action failed")
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)

    def stop(self) -> None:
        if self._thread.is_alive() and self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(timeout=2)
