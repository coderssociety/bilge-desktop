from pathlib import Path

import pytest

from bilge.desktop.base import FrontWindow, ScreenshotArea
from bilge.desktop.linux import environment
from bilge.desktop.linux.clipboard import LinuxClipboard
from bilge.desktop.linux.keyboard import LinuxKeyboard, _sway_focused
from bilge.desktop.linux.system import (
    LinuxNotifier,
    LinuxOpener,
    LinuxScreenshots,
    LinuxSession,
    LinuxSettings,
    user_dir,
)
from bilge.desktop.process import Completed, DesktopError, MissingProgram

from .fakes import FakeRunner

X11 = environment.current({"DISPLAY": ":0", "XDG_CURRENT_DESKTOP": "XFCE"})
GNOME_WAYLAND = environment.current({"WAYLAND_DISPLAY": "wayland-0", "XDG_CURRENT_DESKTOP": "ubuntu:GNOME"})
KDE_WAYLAND = environment.current({"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0", "XDG_CURRENT_DESKTOP": "KDE"})
SWAY = environment.current({"WAYLAND_DISPLAY": "wayland-1", "XDG_CURRENT_DESKTOP": "sway"})


def test_environment_is_read_from_the_session():
    assert GNOME_WAYLAND.wayland and GNOME_WAYLAND.gnome and not GNOME_WAYLAND.kde
    assert KDE_WAYLAND.kde and KDE_WAYLAND.x11


def test_wayland_clipboard_uses_wl_clipboard_and_x11_uses_xclip():
    runner = FakeRunner({"wl-copy", "wl-paste", "xclip"}, {"wl-paste": "kopya"})
    clipboard = LinuxClipboard(runner, GNOME_WAYLAND)
    assert clipboard.read() == "kopya"
    clipboard.selection()
    clipboard.write("yeni")
    assert runner.calls[1][0][:3] == ["wl-paste", "--no-newline", "--primary"]
    assert runner.calls[2] == (["wl-copy", "--type", "text/plain;charset=utf-8"], "yeni")

    runner = FakeRunner({"xclip", "wl-copy"})
    LinuxClipboard(runner, X11).selection()
    assert runner.commands == [["xclip", "-selection", "primary", "-out"]]


def test_empty_clipboard_is_just_empty():
    runner = FakeRunner({"xclip"}, {"xclip": Completed(1, "", "Error: target STRING not available")})
    assert LinuxClipboard(runner, X11).read() == ""


def test_x11_typing_goes_through_xdotool_on_standard_input():
    runner = FakeRunner({"xdotool"})
    keyboard = LinuxKeyboard(runner, X11)
    keyboard.type("Merhaba dünya")
    keyboard.new_line()
    keyboard.backspace(3)
    assert runner.calls[0] == (["xdotool", "type", "--clearmodifiers", "--delay", "8", "--file", "-"], "Merhaba dünya")
    assert runner.commands[1] == ["xdotool", "key", "--clearmodifiers", "shift+Return"]
    assert runner.commands[2][-3:] == ["--repeat", "3", "BackSpace"]


def test_xdotool_pastes_capitals_it_would_type_in_lower_case():
    class Clipboard:
        content = "önceki"

        def read(self):
            return self.content

        def write(self, text):
            self.content = text

    runner = FakeRunner({"xdotool"})
    LinuxKeyboard(runner, X11, Clipboard()).type("ÜÇ harfleri")
    assert runner.commands == [["xdotool", "key", "--clearmodifiers", "ctrl+v"]]


def test_ydotool_pastes_text_it_cannot_type_and_restores_the_clipboard():
    class Clipboard:
        def __init__(self):
            self.content = "önceki"
            self.writes = []

        def read(self):
            return self.content

        def write(self, text):
            self.writes.append(text)
            self.content = text

    runner = FakeRunner({"ydotool"})
    clipboard = Clipboard()
    keyboard = LinuxKeyboard(runner, GNOME_WAYLAND, clipboard)
    keyboard.type("plain ascii")
    keyboard.type("şeker")
    assert runner.calls[0][1] == "plain ascii"
    assert runner.commands[1] == ["ydotool", "key", "29:1", "47:1", "47:0", "29:0"]
    assert clipboard.writes == ["şeker", "önceki"]


def test_wtype_is_not_tried_on_gnome_where_the_protocol_is_missing():
    with pytest.raises(MissingProgram) as error:
        LinuxKeyboard(FakeRunner({"wtype"}), GNOME_WAYLAND).type("x")
    assert error.value.programs == ("ydotool",)


def test_window_class_comes_from_xprop_where_xdotool_is_too_old():
    runner = FakeRunner({"xdotool", "xprop"}, {"xdotool getactivewindow": "77\n", "xdotool getwindowpid": "",
                                                "xprop": 'WM_CLASS(STRING) = "kgx", "Kgx"\n'})  # fmt: skip
    assert LinuxKeyboard(runner, X11).front_window().app_class == "kgx"


def test_front_window_on_x11_and_sway_but_not_gnome_wayland():
    runner = FakeRunner({"xdotool"}, {"xdotool getactivewindow": "123\n", "xdotool getwindowclassname": "Gedit\n",
                                       "xdotool getwindowpid": "", "xdotool getwindowname": "notlar.txt"})  # fmt: skip
    assert LinuxKeyboard(runner, X11).front_window() == FrontWindow("gedit", "notlar.txt", "gedit")
    assert LinuxKeyboard(FakeRunner({"xdotool"}), GNOME_WAYLAND).front_window() is None
    tree = {"type": "root", "nodes": [{"type": "output", "nodes": [
        {"type": "con", "focused": False, "app_id": "foot", "name": "a"},
        {"type": "con", "focused": True, "app_id": "org.gnome.TextEditor", "name": "b"}]}]}  # fmt: skip
    assert _sway_focused(tree) == FrontWindow("org.gnome.texteditor", "b", "org.gnome.texteditor")


def test_dark_mode_on_gnome_and_kde():
    runner = FakeRunner({"gsettings"}, {"gsettings get": "'prefer-dark'\n"})
    session = LinuxSession(runner, GNOME_WAYLAND)
    assert session.dark_mode() is True
    session.set_dark_mode(False)
    assert runner.commands[-1] == ["gsettings", "set", "org.gnome.desktop.interface", "color-scheme", "default"]
    runner = FakeRunner({"plasma-apply-colorscheme"})
    LinuxSession(runner, KDE_WAYLAND).set_dark_mode(True)
    assert runner.commands == [["plasma-apply-colorscheme", "BreezeDark"]]


def test_lock_falls_back_to_xdg_screensaver():
    runner = FakeRunner({"loginctl", "xdg-screensaver"}, {"loginctl": Completed(1, "", "no session")})
    LinuxSession(runner, X11).lock()
    assert runner.commands[-1] == ["xdg-screensaver", "lock"]


def test_screenshot_tool_follows_the_desktop(tmp_path):
    shot = tmp_path / "s.png"

    class Capturing(FakeRunner):
        def run(self, argv, input=None, timeout=15, capture=True):
            if argv[0] != "slurp":
                Path(argv[-1]).write_bytes(b"png")
            return super().run(argv, input, timeout, capture)

    runner = Capturing({"spectacle", "gnome-screenshot"})
    assert LinuxScreenshots(runner, KDE_WAYLAND).capture(ScreenshotArea.SELECTION, shot)
    assert runner.commands[-1] == ["spectacle", "-b", "-n", "-r", "-o", str(shot)]
    runner = Capturing({"grim", "slurp"}, {"slurp": "10,10 200x100"})
    assert LinuxScreenshots(runner, SWAY).capture(ScreenshotArea.SELECTION, shot)
    assert runner.commands[-1] == ["grim", "-g", "10,10 200x100", str(shot)]


def test_cancelled_selection_takes_no_screenshot(tmp_path):
    runner = FakeRunner({"grim", "slurp"}, {"slurp": Completed(1, "", "selection cancelled")})
    assert not LinuxScreenshots(runner, SWAY).capture(ScreenshotArea.SELECTION, tmp_path / "s.png")


def test_settings_pages_open_in_gnome_and_kde():
    runner = FakeRunner({"gnome-control-center"})
    assert LinuxSettings(runner, GNOME_WAYLAND).open("wifi")
    assert not LinuxSettings(runner, GNOME_WAYLAND).open("printers")
    assert runner.spawned == [["gnome-control-center", "wifi"], ["gnome-control-center"]]
    runner = FakeRunner({"systemsettings"})
    assert LinuxSettings(runner, KDE_WAYLAND).open("sound")
    assert runner.spawned == [["systemsettings", "kcm_pulseaudio"]]


class Bus:
    def __init__(self, fails=False):
        self.fails = fails
        self.calls = []

    def call(self, *args):
        if self.fails:
            raise DesktopError("no service")
        self.calls.append(args)


def test_reveal_asks_the_file_manager_or_opens_the_folder(tmp_path):
    bus = Bus()
    LinuxOpener(FakeRunner({"xdg-open"}), bus).reveal(tmp_path / "a b.sh")
    assert bus.calls[0][3] == "ShowItems" and bus.calls[0][5][0].endswith("/a%20b.sh")
    runner = FakeRunner({"xdg-open"})
    LinuxOpener(runner, Bus(fails=True)).reveal(tmp_path / "x.sh")
    assert runner.spawned == [["xdg-open", str(tmp_path)]]


def test_notifications_fall_back_to_notify_send():
    runner = FakeRunner({"notify-send"})
    LinuxNotifier(runner, Bus(fails=True)).notify("Bilge", "Çay hazır")
    assert runner.commands == [["notify-send", "--app-name", "Bilge", "Bilge", "Çay hazır"]]


def test_translated_user_folders_come_from_user_dirs(tmp_path):
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "user-dirs.dirs").write_text('XDG_DESKTOP_DIR="$HOME/Masaüstü"\n', encoding="utf-8")
    environ = {"HOME": str(tmp_path)}
    assert user_dir("DESKTOP", "Desktop", environ) == tmp_path / "Masaüstü"
    assert user_dir("DOWNLOAD", "Downloads", environ) == tmp_path / "Downloads"
