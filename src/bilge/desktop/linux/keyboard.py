"""Typing into the app in front, and finding out which app that is.

X11 lets any program do both (xdotool). Wayland deliberately doesn't: wtype works on compositors with the virtual
keyboard protocol (Sway, Hyprland and other wlroots ones), ydotool works everywhere through the kernel but types by
key position, so text outside US ASCII is pasted instead. Which window is in front can be asked of Sway, Hyprland
and KDE (kdotool); GNOME on Wayland doesn't say.
"""

import json
import re
import time
from pathlib import Path

from bilge.desktop.base import FrontWindow
from bilge.desktop.linux.environment import Environment
from bilge.desktop.process import DesktopError, MissingProgram, Runner

_KEY_DELAY_MS = 8
# Linux input event codes, for ydotool.
_LEFT_SHIFT, _LEFT_CTRL, _ENTER, _BACKSPACE, _V = 42, 29, 28, 14, 47
_PASTE_SETTLE_SECONDS = 0.3
# WM_CLASS(STRING) = "gnome-terminal-server", "Gnome-terminal": the first is the instance, closest to the program.
_WM_CLASS = re.compile(r'WM_CLASS\(\w+\) = "([^"]*)"')


class LinuxKeyboard:
    def __init__(self, runner: Runner, environment: Environment, clipboard=None):
        self._runner = runner
        self._environment = environment
        self._clipboard = clipboard

    def _typist(self) -> str:
        if self._environment.wayland:
            # wtype fails at once where the protocol is missing, and ydotool needs its daemon; both are tried in turn.
            order = ["wtype", "ydotool"] if not self._environment.gnome else ["ydotool"]
        else:
            order = ["xdotool"]
        for program in order:
            if self._runner.has(program):
                return program
        raise MissingProgram(*order)

    def front_window(self) -> FrontWindow | None:
        env = self._environment
        try:
            if env.sway and self._runner.has("swaymsg"):
                return _sway_focused(json.loads(self._runner.check(["swaymsg", "-t", "get_tree"])))
            if env.hyprland and self._runner.has("hyprctl"):
                window = json.loads(self._runner.check(["hyprctl", "activewindow", "-j"]))
                app_class = str(window.get("class", "")).lower()
                pid = window.get("pid")
                program = _program_name(pid) if isinstance(pid, int) else None
                return FrontWindow(program or app_class, str(window.get("title", "")), app_class)
            if env.kde and env.wayland and self._runner.has("kdotool"):
                return self._xdotool_style("kdotool")
            if not env.wayland and self._runner.has("xdotool"):
                return self._xdotool_style("xdotool")
        except (DesktopError, ValueError) as error:
            raise DesktopError(f"Could not read the front window: {error}") from error
        return None

    def _xdotool_style(self, program: str) -> FrontWindow | None:
        window = self._runner.run([program, "getactivewindow"])
        if not window.ok or not window.stdout.strip():
            return None
        window_id = window.stdout.split()[0]
        app_class = self._window_class(program, window_id)
        pid = self._runner.run([program, "getwindowpid", window_id]).stdout.strip()
        name = (_program_name(int(pid)) if pid.isdigit() else None) or app_class
        title = self._runner.run([program, "getwindowname", window_id]).stdout.strip()
        return FrontWindow(name, title, app_class) if name else None

    def _window_class(self, program: str, window_id: str) -> str:
        """xprop on X11: the xdotool many distributions ship (3.2016) has no getwindowclassname."""
        if program == "xdotool" and self._runner.has("xprop"):
            found = _WM_CLASS.search(self._runner.run(["xprop", "-id", window_id, "WM_CLASS"]).stdout)
            if found:
                return found.group(1).lower()
        done = self._runner.run([program, "getwindowclassname", window_id])
        return done.stdout.strip().lower() if done.ok else ""

    def type(self, text: str) -> None:
        """The text goes in on standard input, which keeps what the user dictates out of the process list."""
        typist = self._typist()
        delay = str(_KEY_DELAY_MS)
        if typist == "xdotool" and not _has_foreign_capital(text):
            self._runner.check(["xdotool", "type", "--clearmodifiers", "--delay", delay, "--file", "-"], input=text)
        elif typist == "wtype":
            self._runner.check(["wtype", "-d", delay, "-"], input=text)
        elif typist == "ydotool" and text.isascii():
            self._runner.check(["ydotool", "type", "-d", delay, "--file", "-"], input=text)
        else:
            self._paste(text, typist)

    def _paste(self, text: str, typist: str) -> None:
        """For text the typing tool gets wrong: ydotool presses keys by their place on a US layout, so "ş" can't be
        typed, and the xdotool most distributions ship (3.2016) types "Ü" and "Ç" in lower case when they are not
        on the keyboard layout. Ctrl+V is the same keys everywhere. The user's clipboard is put back afterwards."""
        if self._clipboard is None:
            raise MissingProgram("wl-clipboard", "xclip")
        saved = self._clipboard.read()
        self._clipboard.write(text)
        try:
            if typist == "xdotool":
                self._runner.check(["xdotool", "key", "--clearmodifiers", "ctrl+v"])
            else:
                self._ydotool_keys((_LEFT_CTRL, _V))
            time.sleep(_PASTE_SETTLE_SECONDS)
        finally:
            # An image on the clipboard reads as no text; writing that back would replace the image with nothing.
            if saved:
                self._clipboard.write(saved)

    def new_line(self) -> None:
        typist = self._typist()
        if typist == "xdotool":
            self._runner.check(["xdotool", "key", "--clearmodifiers", "shift+Return"])
        elif typist == "wtype":
            self._runner.check(["wtype", "-M", "shift", "-k", "Return", "-m", "shift"])
        else:
            self._ydotool_keys((_LEFT_SHIFT, _ENTER))

    def backspace(self, count: int) -> None:
        if count <= 0:
            return
        typist = self._typist()
        if typist == "xdotool":
            self._runner.check(
                [
                    "xdotool",
                    "key",
                    "--clearmodifiers",
                    "--delay",
                    str(_KEY_DELAY_MS),
                    "--repeat",
                    str(count),
                    "BackSpace",
                ]
            )
        elif typist == "wtype":
            self._runner.check(["wtype", "-d", str(_KEY_DELAY_MS), *(["-k", "BackSpace"] * count)])
        else:
            self._runner.check(
                ["ydotool", "key", "-d", str(_KEY_DELAY_MS), *[f"{_BACKSPACE}:1", f"{_BACKSPACE}:0"] * count]
            )

    def _ydotool_keys(self, keys: tuple[int, ...]) -> None:
        """Presses the keys in order and releases them in reverse, as a shortcut."""
        events = [f"{key}:1" for key in keys] + [f"{key}:0" for key in reversed(keys)]
        self._runner.check(["ydotool", "key", *events])


def _has_foreign_capital(text: str) -> bool:
    return any(not c.isascii() and c != c.lower() for c in text)


def _sway_focused(node: dict) -> FrontWindow | None:
    if node.get("focused") and node.get("type") in ("con", "floating_con"):
        app_class = str(node.get("app_id") or (node.get("window_properties") or {}).get("class") or "").lower()
        pid = node.get("pid")
        program = _program_name(pid) if isinstance(pid, int) else None
        return FrontWindow(program or app_class, str(node.get("name") or ""), app_class)
    for child in [*node.get("nodes", []), *node.get("floating_nodes", [])]:
        found = _sway_focused(child)
        if found:
            return found
    return None


def _program_name(pid: int) -> str | None:
    try:
        return Path(f"/proc/{pid}/exe").readlink().name.lower()
    except OSError:
        return None
