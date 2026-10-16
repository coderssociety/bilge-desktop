"""An X11 session: the key is grabbed on the root window through Xlib, on a connection of Bilge's own that only the
shortcut's thread uses.

The grab is made once for each state of Num Lock and Caps Lock, which X counts as modifiers too: with Num Lock on,
Ctrl+Alt+B would otherwise not match.
"""

import ctypes
import logging
import select
import threading
from collections.abc import Callable

from bilge.desktop.hotkey import HotkeyError
from bilge.desktop.hotkey.shortcut import Shortcut

log = logging.getLogger(__name__)

SHIFT_MASK, LOCK_MASK, CONTROL_MASK, MOD1_MASK, MOD2_MASK, MOD4_MASK = 1, 2, 4, 8, 16, 64
_MASKS = {"shift": SHIFT_MASK, "ctrl": CONTROL_MASK, "alt": MOD1_MASK, "meta": MOD4_MASK}
_LOCK_VARIANTS = (0, LOCK_MASK, MOD2_MASK, LOCK_MASK | MOD2_MASK)
KEY_PRESS, KEY_RELEASE = 2, 3
GRAB_MODE_ASYNC = 1
BAD_ACCESS = 10
NO_SYMBOL = 0
POLL_SECONDS = 0.5
READY_SECONDS = 5
# XEvent is a union padded to 24 longs.
_EVENT_BYTES = 24 * 8


class _ErrorEvent(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("display", ctypes.c_void_p), ("resourceid", ctypes.c_ulong),
                ("serial", ctypes.c_ulong), ("error_code", ctypes.c_ubyte), ("request_code", ctypes.c_ubyte),
                ("minor_code", ctypes.c_ubyte)]  # fmt: skip


_ERROR_HANDLER = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(_ErrorEvent))
# Xlib keeps one error handler for the whole process; this one is set only while grabbing, to see which grabs failed.
_failed_grabs: set[int] = set()


@_ERROR_HANDLER
def _on_error(display, event) -> int:
    _failed_grabs.add(event.contents.error_code)
    return 0


def _load():
    try:
        xlib = ctypes.CDLL("libX11.so.6")
    except OSError as error:
        raise HotkeyError("unsupported", "libX11 is missing") from error
    xlib.XOpenDisplay.restype = ctypes.c_void_p
    xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    xlib.XDefaultRootWindow.restype = ctypes.c_ulong
    xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    xlib.XStringToKeysym.restype = ctypes.c_ulong
    xlib.XStringToKeysym.argtypes = [ctypes.c_char_p]
    xlib.XKeysymToKeycode.restype = ctypes.c_ubyte
    xlib.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    xlib.XGrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int]  # fmt: skip
    xlib.XUngrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong]
    xlib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    xlib.XPending.argtypes = [ctypes.c_void_p]
    xlib.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    xlib.XConnectionNumber.argtypes = [ctypes.c_void_p]
    xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    xlib.XkbSetDetectableAutoRepeat.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    xlib.XSetErrorHandler.argtypes = [ctypes.c_void_p]
    xlib.XSetErrorHandler.restype = ctypes.c_void_p
    return xlib


class X11Hotkey:
    def __init__(self, shortcut: Shortcut, pressed: Callable[[], None]):
        self.shortcut = shortcut
        self._pressed = pressed
        self._xlib = _load()
        self._stopping = threading.Event()
        self._ready = threading.Event()
        self._error: HotkeyError | None = None
        self._thread = threading.Thread(target=self._run, name="bilge-hotkey", daemon=True)
        self._thread.start()
        if not self._ready.wait(READY_SECONDS):
            raise HotkeyError("unsupported", "X did not answer")
        if self._error is not None:
            raise self._error

    def _fail(self, error: HotkeyError) -> None:
        self._error = error
        self._ready.set()

    def _run(self) -> None:
        xlib = self._xlib
        display = xlib.XOpenDisplay(None)
        if not display:
            self._fail(HotkeyError("unsupported", "no X display"))
            return
        try:
            self._listen(xlib, display)
        finally:
            xlib.XCloseDisplay(display)

    def _listen(self, xlib, display) -> None:
        root = xlib.XDefaultRootWindow(display)
        keysym = xlib.XStringToKeysym(self.shortcut.x11_key.encode())
        keycode = xlib.XKeysymToKeycode(display, keysym) if keysym != NO_SYMBOL else 0
        if not keycode:
            self._fail(HotkeyError("invalid", f"no key for {self.shortcut.text} on this keyboard"))
            return
        modifiers = 0
        for name in self.shortcut.modifiers:
            modifiers |= _MASKS[name]
        _failed_grabs.clear()
        previous = xlib.XSetErrorHandler(ctypes.cast(_on_error, ctypes.c_void_p))
        for extra in _LOCK_VARIANTS:
            xlib.XGrabKey(display, keycode, modifiers | extra, root, 1, GRAB_MODE_ASYNC, GRAB_MODE_ASYNC)
        xlib.XSync(display, 0)
        xlib.XSetErrorHandler(previous)
        if BAD_ACCESS in _failed_grabs:
            for extra in _LOCK_VARIANTS:
                xlib.XUngrabKey(display, keycode, modifiers | extra, root)
            xlib.XSync(display, 0)
            self._fail(HotkeyError("taken", self.shortcut.text))
            return
        # Held down, the key repeats as presses with no releases in between; only the first press counts.
        xlib.XkbSetDetectableAutoRepeat(display, 1, None)
        self._ready.set()
        event = ctypes.create_string_buffer(_EVENT_BYTES)
        connection = xlib.XConnectionNumber(display)
        held = False
        try:
            while not self._stopping.is_set():
                if not xlib.XPending(display):
                    select.select([connection], [], [], POLL_SECONDS)
                    continue
                xlib.XNextEvent(display, event)
                kind = ctypes.c_int.from_buffer(event).value
                if kind == KEY_RELEASE:
                    held = False
                elif kind == KEY_PRESS and not held:
                    held = True
                    try:
                        self._pressed()
                    except Exception:
                        log.exception("The shortcut's action failed")
        finally:
            for extra in _LOCK_VARIANTS:
                xlib.XUngrabKey(display, keycode, modifiers | extra, root)
            xlib.XSync(display, 0)

    def stop(self) -> None:
        self._stopping.set()
        self._thread.join(timeout=2)
