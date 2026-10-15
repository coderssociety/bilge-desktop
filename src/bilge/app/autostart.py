"""Starting Bilge with the computer: the Run key on Windows, an autostart entry on Linux."""

import contextlib
import os
import sys
from pathlib import Path

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "Bilge"


def command() -> list[str]:
    """How to start the app: the installed program, or this Python running the package."""
    # Inside an AppImage the program runs from a mount that changes every time; the AppImage file itself stays.
    if os.environ.get("APPIMAGE"):
        return [os.environ["APPIMAGE"]]
    if getattr(sys, "frozen", False):
        return [sys.executable]
    python = Path(sys.executable)
    # pythonw has no console window on Windows.
    windowless = python.with_name("pythonw.exe")
    if sys.platform == "win32" and windowless.exists():
        python = windowless
    return [str(python), "-m", "bilge.app"]


def exec_line(argv: list[str]) -> str:
    """Quoted as the Desktop Entry specification wants: double quotes, with \\ " ` $ escaped and % doubled."""

    def quoted(argument: str) -> str:
        escaped = "".join("\\" + c if c in '\\"`$' else c for c in argument).replace("%", "%%")
        plain = escaped and all(c.isalnum() or c in "/._-+=:,@" for c in argument)
        return escaped if plain else f'"{escaped}"'

    return " ".join(quoted(argument) for argument in argv)


def _desktop_entry() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "autostart" / "bilge.desktop"


def is_enabled() -> bool:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                winreg.QueryValueEx(key, _NAME)
            return True
        except OSError:
            return False
    return _desktop_entry().exists()


def set_enabled(enabled: bool) -> None:
    if sys.platform == "win32":
        import subprocess
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            if enabled:
                winreg.SetValueEx(key, _NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(command()))
            else:
                with contextlib.suppress(FileNotFoundError):
                    winreg.DeleteValue(key, _NAME)
        return
    entry = _desktop_entry()
    if not enabled:
        entry.unlink(missing_ok=True)
        return
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(
        "[Desktop Entry]\nType=Application\nName=Bilge\nComment=Voice assistant\n"
        f"Exec={exec_line(command())}\nIcon=bilge\nX-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )
