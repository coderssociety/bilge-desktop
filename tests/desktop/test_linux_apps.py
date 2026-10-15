import signal
import sys

import pytest

from bilge.desktop.linux import apps as linux_apps
from bilge.desktop.linux.apps import LinuxApps, launch_command, parse

from .fakes import FakeRunner

CALCULATOR = """[Desktop Entry]
Name=Calculator
Name[tr]=Hesap Makinesi
GenericName=Calculator
Exec=gnome-calculator %U
Type=Application

[Desktop Action new-window]
Name=New Window
Exec=gnome-calculator --new-window
"""


def write(folder, name, text):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


def test_entry_is_named_in_the_users_language_and_by_its_program(tmp_path):
    path = write(tmp_path, "org.gnome.Calculator.desktop", CALCULATOR)
    entry = parse(path, "org.gnome.Calculator.desktop", ("tr_TR", "tr"))
    assert entry.name == "Hesap Makinesi"
    assert {"Hesap Makinesi", "Calculator"} <= set(entry.names)
    assert entry.binaries == frozenset({"gnome-calculator"})
    assert launch_command(entry) == ["gnome-calculator"]


def test_hidden_terminal_and_non_app_entries_are_skipped(tmp_path):
    for flags in ("Type=Application\nNoDisplay=true", "Type=Application\nHidden=true",
                  "Type=Application\nTerminal=true", "Type=Link"):  # fmt: skip
        text = f"[Desktop Entry]\nName=X\nExec=x\n{flags}\n"
        assert parse(write(tmp_path, "x.desktop", text), "x.desktop", ("tr",)) is None


def test_flatpak_and_interpreted_apps_are_matched_by_what_identifies_them(tmp_path):
    flatpak = parse(write(tmp_path, "s.desktop", "[Desktop Entry]\nName=Spotify\nType=Application\n"
                          "Exec=/usr/bin/flatpak run --branch=stable --command=spotify com.spotify.Client --uri=%U\n"),
                    "com.spotify.Client.desktop", ())  # fmt: skip
    assert flatpak.flatpak == "com.spotify.Client"
    script = parse(write(tmp_path, "m.desktop", "[Desktop Entry]\nName=Meld\nType=Application\n"
                         "Exec=python3 /usr/bin/meld %F\n"), "meld.desktop", ())  # fmt: skip
    # Matching on "python3" would close every Python program.
    assert script.binaries == frozenset({"meld"})


def test_users_own_entry_overrides_the_systems(tmp_path):
    user, system = tmp_path / "user", tmp_path / "system"
    write(user, "firefox.desktop", "[Desktop Entry]\nName=My Firefox\nType=Application\nExec=firefox\n")
    write(system, "firefox.desktop", "[Desktop Entry]\nName=Firefox\nType=Application\nExec=firefox\n")
    apps = LinuxApps(FakeRunner(), (), dirs=lambda: [user, system])
    assert [a.display_name for a in apps.installed()] == ["My Firefox"]


def test_launch_prefers_gio_and_falls_back_to_the_exec_line(tmp_path):
    write(tmp_path, "calc.desktop", CALCULATOR)
    runner = FakeRunner({"gnome-calculator"})
    apps = LinuxApps(runner, ("tr",), dirs=lambda: [tmp_path])
    app = apps.installed()[0]
    apps.launch(app)
    assert runner.spawned == [["gnome-calculator"]]

    runner.installed.add("gio")
    apps.launch(app)
    assert runner.commands[-1] == ["gio", "launch", str(tmp_path / "calc.desktop")]


def test_running_apps_and_quitting_send_terminate_to_their_processes(tmp_path, monkeypatch):
    write(tmp_path, "calc.desktop", CALCULATOR)
    write(tmp_path, "gedit.desktop", "[Desktop Entry]\nName=Text Editor\nType=Application\nExec=gedit %U\n")
    processes = [(101, "gnome-calculator"), (102, "gnome-calculator"), (300, "bash")]
    apps = LinuxApps(FakeRunner(), ("tr",), dirs=lambda: [tmp_path], processes=lambda: processes)
    assert [a.display_name for a in apps.running()] == ["Hesap Makinesi"]
    killed = []
    monkeypatch.setattr(linux_apps.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    calculator = next(a for a in apps.installed() if a.display_name == "Hesap Makinesi")
    editor = next(a for a in apps.installed() if a.display_name == "Text Editor")
    assert apps.quit(calculator)
    assert killed == [(101, signal.SIGTERM), (102, signal.SIGTERM)]
    assert not apps.quit(editor)


def test_flatpak_apps_are_found_through_flatpak_ps(tmp_path):
    write(tmp_path, "s.desktop", "[Desktop Entry]\nName=Spotify\nType=Application\n"
          "Exec=flatpak run com.spotify.Client\n")  # fmt: skip
    runner = FakeRunner({"flatpak"}, {"flatpak ps": "4242 com.spotify.Client\n"})
    apps = LinuxApps(runner, (), dirs=lambda: [tmp_path], processes=lambda: [])
    assert [a.display_name for a in apps.running()] == ["Spotify"]


@pytest.mark.skipif(sys.platform == "win32", reason="/proc and symbolic links are Linux's")
def test_own_processes_reads_proc(tmp_path, monkeypatch):
    proc = tmp_path / "proc"
    for pid, argv, exe in [("10", b"/usr/bin/gedit\0--new\0", "/usr/bin/gedit"),
                           ("11", b"python3\0/usr/bin/meld\0", "/usr/bin/python3.12")]:  # fmt: skip
        (proc / pid).mkdir(parents=True)
        (proc / pid / "cmdline").write_bytes(argv)
        (proc / pid / "exe").symlink_to(exe)
    (proc / "self").mkdir()
    found = sorted(linux_apps.own_processes(proc))
    assert found == [(10, "gedit"), (11, "meld")]
