"""The few Windows API calls the desktop tools need, through ctypes. Only imported on Windows."""

import ctypes
import time
import uuid
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from bilge.desktop.image import Pixels
from bilge.desktop.process import DesktopError

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
ole32 = ctypes.WinDLL("ole32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

CF_UNICODETEXT, CF_DIB = 13, 8
GMEM_MOVEABLE = 0x0002
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004
VK_SHIFT, VK_CONTROL, VK_RETURN, VK_BACK = 0x10, 0x11, 0x0D, 0x08
VK_C, VK_V = 0x43, 0x56
WM_CLOSE = 0x0010
GWL_EXSTYLE, WS_EX_TOOLWINDOW = -20, 0x00000080
GW_OWNER = 4
SRCCOPY, CAPTUREBLT = 0x00CC0020, 0x40000000
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79
HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x001A, 0x0002
_CLIPBOARD_ATTEMPTS = 10
DWMWA_EXTENDED_FRAME_BOUNDS, DWMWA_CLOAKED = 9, 14


class _KeyboardInput(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]  # fmt: skip


class _MouseInput(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]  # fmt: skip


class _InputUnion(ctypes.Union):
    # The mouse member is the largest; it is declared so the structure has the size SendInput expects.
    _fields_ = [("ki", _KeyboardInput), ("mi", _MouseInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _InputUnion)]


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]  # fmt: skip


class _Guid(ctypes.Structure):
    _fields_ = [("data", ctypes.c_ubyte * 16)]


def _declare() -> None:
    handle, pointer = wintypes.HANDLE, ctypes.c_void_p
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int]
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = handle
    user32.SetClipboardData.argtypes = [wintypes.UINT, handle]
    user32.SetClipboardData.restype = handle
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = handle
    user32.ReleaseDC.argtypes = [wintypes.HWND, handle]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR,
                                           wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]  # fmt: skip
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = handle
    kernel32.GlobalLock.argtypes = [handle]
    kernel32.GlobalLock.restype = pointer
    kernel32.GlobalUnlock.argtypes = [handle]
    kernel32.GlobalSize.argtypes = [handle]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalFree.argtypes = [handle]
    gdi32.CreateCompatibleDC.argtypes = [handle]
    gdi32.CreateCompatibleDC.restype = handle
    gdi32.CreateDIBSection.argtypes = [handle, ctypes.POINTER(_BitmapInfoHeader), wintypes.UINT,
                                       ctypes.POINTER(pointer), handle, wintypes.DWORD]  # fmt: skip
    gdi32.CreateDIBSection.restype = handle
    gdi32.SelectObject.argtypes = [handle, handle]
    gdi32.SelectObject.restype = handle
    gdi32.BitBlt.argtypes = [handle, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, handle, ctypes.c_int,
                             ctypes.c_int, wintypes.DWORD]  # fmt: skip
    gdi32.DeleteObject.argtypes = [handle]
    gdi32.DeleteDC.argtypes = [handle]
    shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(_Guid), wintypes.DWORD, handle,
                                             ctypes.POINTER(wintypes.LPWSTR)]  # fmt: skip
    ole32.CoTaskMemFree.argtypes = [pointer]
    dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, pointer, wintypes.DWORD]
    kernel32.GetDateFormatEx.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, pointer, wintypes.LPCWSTR, wintypes.LPWSTR,
                                         ctypes.c_int, wintypes.LPCWSTR]  # fmt: skip
    kernel32.GetTimeFormatEx.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, pointer, wintypes.LPCWSTR, wintypes.LPWSTR,
                                         ctypes.c_int]  # fmt: skip


_declare()


@dataclass(frozen=True)
class Window:
    handle: int
    pid: int
    title: str
    class_name: str = ""


def _text(handle: int) -> str:
    length = user32.GetWindowTextLengthW(handle)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(handle, buffer, length + 1)
    return buffer.value


def _pid(handle: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
    return pid.value


def foreground() -> Window | None:
    handle = user32.GetForegroundWindow()
    if not handle:
        return None
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(handle, buffer, 256)
    return Window(handle, _pid(handle), _text(handle), buffer.value)


def app_windows() -> list[Window]:
    """Visible, titled, unowned windows that aren't tool palettes: what the taskbar shows."""
    found: list[Window] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(handle, _):
        if (user32.IsWindowVisible(handle) and not user32.GetWindow(handle, GW_OWNER)
                and not user32.GetWindowLongW(handle, GWL_EXSTYLE) & WS_EX_TOOLWINDOW and not _cloaked(handle)):  # fmt: skip
            title = _text(handle)
            if title:
                found.append(Window(handle, _pid(handle), title))
        return True

    user32.EnumWindows(visit, 0)
    return found


def _cloaked(handle: int) -> bool:
    """Suspended Store apps keep a "visible" frame that Windows hides from view."""
    cloaked = wintypes.DWORD()
    found = dwmapi.DwmGetWindowAttribute(handle, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    return found == 0 and cloaked.value != 0


def close(window: Window) -> None:
    """The same as clicking the window's close button: the app can still ask to save."""
    if not user32.PostMessageW(window.handle, WM_CLOSE, 0, 0):
        raise DesktopError(f"Could not close window {window.handle}")


def _send(inputs: list[_Input]) -> None:
    array = (_Input * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), array, ctypes.sizeof(_Input))
    if sent != len(inputs):
        # Input into a window of a program running as administrator is refused while Bilge isn't.
        raise DesktopError(f"SendInput delivered {sent} of {len(inputs)} events: {ctypes.get_last_error()}")


def _key(vk: int = 0, scan: int = 0, flags: int = 0) -> _Input:
    event = _Input(type=INPUT_KEYBOARD)
    event.union.ki = _KeyboardInput(vk, scan, flags, 0, 0)
    return event


def type_unicode(text: str, pause: float = 0.008) -> None:
    """Each character as itself, whatever the keyboard layout. Characters outside the Basic Multilingual Plane
    go as their two UTF-16 halves."""
    units = text.encode("utf-16-le")
    for index in range(0, len(units), 2):
        unit = int.from_bytes(units[index : index + 2], "little")
        _send([_key(scan=unit, flags=KEYEVENTF_UNICODE), _key(scan=unit, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)])
        time.sleep(pause)


def press(*keys: int) -> None:
    """A shortcut: keys down in order, up in reverse."""
    _send([_key(vk) for vk in keys] + [_key(vk, flags=KEYEVENTF_KEYUP) for vk in reversed(keys)])


class _Clipboard:
    def __enter__(self):
        for _ in range(_CLIPBOARD_ATTEMPTS):
            if user32.OpenClipboard(None):
                return self
            # Another program has it open for a moment.
            time.sleep(0.05)
        raise DesktopError("The clipboard is busy")

    def __exit__(self, *_):
        user32.CloseClipboard()


def clipboard_sequence() -> int:
    return user32.GetClipboardSequenceNumber()


def _read(kind: int) -> bytes | None:
    with _Clipboard():
        handle = user32.GetClipboardData(kind)
        if not handle:
            return None
        address = kernel32.GlobalLock(handle)
        if not address:
            return None
        try:
            return ctypes.string_at(address, kernel32.GlobalSize(handle))
        finally:
            kernel32.GlobalUnlock(handle)


def _write(kind: int, data: bytes) -> None:
    with _Clipboard():
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise DesktopError("Out of memory for the clipboard")
        address = kernel32.GlobalLock(handle)
        if not address:
            kernel32.GlobalFree(handle)
            raise DesktopError("Could not lock clipboard memory")
        ctypes.memmove(address, data, len(data))
        kernel32.GlobalUnlock(handle)
        user32.EmptyClipboard()
        # Once set, the memory belongs to the clipboard; only a refused handle is still ours to free.
        if not user32.SetClipboardData(kind, handle):
            kernel32.GlobalFree(handle)
            raise DesktopError("Could not set the clipboard")


def clipboard_text() -> str:
    data = _read(CF_UNICODETEXT)
    return data.decode("utf-16-le", errors="replace").split("\0", 1)[0] if data else ""


def set_clipboard_text(text: str) -> None:
    _write(CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))


def clipboard_bitmap() -> bytes | None:
    return _read(CF_DIB) if user32.IsClipboardFormatAvailable(CF_DIB) else None


def set_clipboard_bitmap(data: bytes) -> None:
    _write(CF_DIB, data)


def screen_rect() -> tuple[int, int, int, int]:
    metric = user32.GetSystemMetrics
    return (metric(SM_XVIRTUALSCREEN), metric(SM_YVIRTUALSCREEN), metric(SM_CXVIRTUALSCREEN),
            metric(SM_CYVIRTUALSCREEN))  # fmt: skip


def window_rect(window: Window) -> tuple[int, int, int, int]:
    """The visible frame; GetWindowRect also counts the invisible shadow border around Windows 10 and 11 windows."""
    rect = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(window.handle, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect),
                                    ctypes.sizeof(rect)) != 0:  # fmt: skip
        user32.GetWindowRect(window.handle, ctypes.byref(rect))
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


def capture(left: int, top: int, width: int, height: int) -> Pixels:
    if width <= 0 or height <= 0:
        raise DesktopError("Nothing to capture")
    screen = user32.GetDC(None)
    memory = gdi32.CreateCompatibleDC(screen)
    # A negative height asks for top-down rows.
    header = _BitmapInfoHeader(ctypes.sizeof(_BitmapInfoHeader), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(memory, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
    try:
        if not bitmap:
            raise DesktopError("Could not make a bitmap")
        previous = gdi32.SelectObject(memory, bitmap)
        try:
            if not gdi32.BitBlt(memory, 0, 0, width, height, screen, left, top, SRCCOPY | CAPTUREBLT):
                raise DesktopError(f"Screen copy failed: {ctypes.get_last_error()}")
            data = bytearray(ctypes.string_at(bits, width * height * 4))
        finally:
            # A bitmap still selected into a DC can't be deleted.
            gdi32.SelectObject(memory, previous)
        # GDI leaves alpha at 0, which apps that honour it would paste as transparent.
        data[3::4] = b"\xff" * (width * height)
        return Pixels(width, height, bytes(data))
    finally:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory)
        user32.ReleaseDC(None, screen)


def use_physical_pixels() -> None:
    """Without this, a scaled display reports and copies a smaller, blurred screen."""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except AttributeError:
        user32.SetProcessDPIAware()


def known_folder(folder_id: str) -> Path:
    guid = _Guid()
    ctypes.memmove(guid.data, uuid.UUID(folder_id).bytes_le, 16)
    path = wintypes.LPWSTR()
    result = shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(path))
    try:
        if result != 0:
            raise DesktopError(f"No known folder {folder_id}: {result:#x}")
        return Path(path.value)
    finally:
        ole32.CoTaskMemFree(path)


def lock() -> None:
    if not user32.LockWorkStation():
        raise DesktopError(f"LockWorkStation failed: {ctypes.get_last_error()}")


def suspend() -> None:
    powrprof = ctypes.WinDLL("powrprof", use_last_error=True)
    # It returns a one-byte BOOLEAN.
    powrprof.SetSuspendState.restype = ctypes.c_ubyte
    if not powrprof.SetSuspendState(False, False, False):
        raise DesktopError(f"SetSuspendState failed: {ctypes.get_last_error()}")


def announce_setting_change(area: str) -> None:
    """Tells open windows a setting changed (the light or dark theme), as the Settings app does."""
    result = ctypes.c_size_t()
    user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, area, SMTO_ABORTIFHUNG, 2000, ctypes.byref(result))


class _SystemTime(ctypes.Structure):
    _fields_ = [(name, wintypes.WORD) for name in
                ("wYear", "wMonth", "wDayOfWeek", "wDay", "wHour", "wMinute", "wSecond", "wMilliseconds")]  # fmt: skip


def short_date_time(moment) -> str:
    """The date and time as the user's Windows writes them ("15.10.2026 14:05"), which is the form Outlook's item
    filters expect."""
    when = _SystemTime(moment.year, moment.month, 0, moment.day, moment.hour, moment.minute, 0, 0)
    date_text, time_text = ctypes.create_unicode_buffer(80), ctypes.create_unicode_buffer(80)
    # DATE_SHORTDATE and TIME_NOSECONDS for the user's own locale.
    kernel32.GetDateFormatEx(None, 1, ctypes.byref(when), None, date_text, 80, None)
    kernel32.GetTimeFormatEx(None, 2, ctypes.byref(when), None, time_text, 80)
    if not date_text.value or not time_text.value:
        raise DesktopError(f"Could not format a date: {ctypes.get_last_error()}")
    return f"{date_text.value} {time_text.value}"
