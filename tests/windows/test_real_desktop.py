"""The Windows tools against Windows itself. Run on a Windows desktop session with BILGE_REAL_DESKTOP=1; skipped
elsewhere. It opens and closes a few windows and puts the theme back as it was."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from bilge.core.language import AssistantLanguage
from bilge.desktop.base import ScreenshotArea
from bilge.desktop.process import DesktopError

pytestmark = pytest.mark.skipif(
    not (sys.platform == "win32" and os.environ.get("BILGE_REAL_DESKTOP")), reason="needs a Windows desktop session"
)
TR = AssistantLanguage.TURKISH
EDITOR = """
import sys, tkinter as tk
from pathlib import Path
root = tk.Tk()
root.title("Bilge deneme")
text = tk.Text(root)
text.pack()
root.lift()
root.attributes("-topmost", True)
text.focus_force()
def check():
    if Path(sys.argv[1] + ".stop").exists():
        Path(sys.argv[1]).write_text(text.get("1.0", "end-1c"), encoding="utf-8")
        root.destroy()
    else:
        root.after(100, check)
root.after(100, check)
root.mainloop()
"""


def eventually(condition, limit=15.0):
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(0.2)
    return condition()


@pytest.fixture(scope="module")
def desktop():
    from bilge.desktop import current

    found = current(TR)
    assert found is not None
    return found


@pytest.fixture
def editor(tmp_path, desktop):
    script = tmp_path / "editor.py"
    script.write_text(EDITOR, encoding="utf-8")
    result = tmp_path / "typed.txt"
    process = subprocess.Popen([sys.executable, str(script), str(result)])
    assert eventually(lambda: (w := desktop.keyboard.front_window()) and w.title == "Bilge deneme")

    def finish() -> str:
        Path(f"{result}.stop").touch()
        process.wait(10)
        return result.read_text(encoding="utf-8")

    yield finish
    if process.poll() is None:
        process.kill()


def test_turkish_text_is_typed_into_the_window_in_front(desktop, editor):
    front = desktop.keyboard.front_window()
    assert front.name in ("python", "pythonw") and front.title == "Bilge deneme"
    desktop.keyboard.type("Merhaba dünya, ŞĞÜİıçö")
    desktop.keyboard.new_line()
    desktop.keyboard.type("ikinci")
    desktop.keyboard.backspace(2)
    assert editor() == "Merhaba dünya, ŞĞÜİıçö\nikin"


def test_dictation_types_what_is_said(desktop, editor):
    from bilge.tools.desktop.typing import DictationSession, front_app

    session = DictationSession(desktop.keyboard, TR)
    session.begin(front_app(desktop.keyboard))
    assert session.handle("bugün hava çok güzel") == ""
    assert session.handle("dikteyi bitir") == "Dikte bitti."
    assert editor().startswith("Bugün hava çok güzel")


def test_clipboard_round_trip(desktop):
    desktop.clipboard.write("Panoda Türkçe: şğü")
    assert desktop.clipboard.read() == "Panoda Türkçe: şğü"


def test_volume(desktop):
    before = desktop.volume.state()
    try:
        desktop.volume.set_level(35)
        assert desktop.volume.state().level == 35
        desktop.volume.set_muted(True)
        assert desktop.volume.state().muted
    finally:
        desktop.volume.set_level(before.level)
        desktop.volume.set_muted(before.muted)


def test_an_app_is_opened_seen_running_and_closed(desktop):
    from bilge.tools.desktop.apps import AppCatalog

    app = AppCatalog(desktop.apps).resolve("hesap makinesi")
    assert app is not None and app.display_name == "Hesap Makinesi"
    desktop.apps.launch(app)
    assert eventually(lambda: any(a.id == app.id for a in desktop.apps.running()), 20)
    assert desktop.apps.quit(app)
    assert eventually(lambda: not any(a.id == app.id for a in desktop.apps.running()), 10)


def test_screenshot_is_saved_and_copied(desktop, tmp_path):
    image = tmp_path / "shot.png"
    assert desktop.screenshots.capture(ScreenshotArea.WHOLE_SCREEN, image)
    assert image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and image.stat().st_size > 1000
    desktop.screenshots.copy_image(image)
    from bilge.desktop.windows import win32

    assert win32.clipboard_bitmap()


def test_dark_mode_is_switched_and_put_back(desktop):
    before = desktop.session.dark_mode()
    try:
        desktop.session.set_dark_mode(True)
        assert desktop.session.dark_mode() is True
        desktop.session.set_dark_mode(False)
        assert desktop.session.dark_mode() is False
    finally:
        if before is not None:
            desktop.session.set_dark_mode(before)


def test_notification(desktop):
    desktop.notifier.notify("Bilge", "Zamanlayıcı doldu.")


def test_known_folders(desktop):
    assert desktop.folders.desktop().is_dir() and desktop.folders.downloads().is_dir()


def test_a_file_goes_to_the_recycle_bin(desktop):
    from types import SimpleNamespace

    from bilge.tools.desktop.files import FileTools

    documents = desktop.folders.documents()
    doomed = documents / "eski fatura 2019.txt"
    doomed.write_text("x")
    folders = SimpleNamespace(home=Path.home, desktop=desktop.folders.desktop, documents=lambda: documents,
                              downloads=desktop.folders.downloads, pictures=desktop.folders.pictures)  # fmt: skip
    tools = FileTools(folders, desktop.opener, TR)
    assert "eski fatura 2019.txt" in tools.trash_question({"query": "eski fatura"})
    tools.trash({"query": "eski fatura"})
    assert not doomed.exists()


def test_without_a_wifi_radio_the_answer_is_honest(desktop):
    if desktop.network.wifi_enabled() is not None:
        pytest.skip("this computer has Wi-Fi")
    with pytest.raises(DesktopError):
        desktop.network.set_wifi(False)


def test_office_programs_that_are_closed_are_reported():
    from bilge.desktop.calc import CalcError, LibreOfficeCalc
    from bilge.desktop.process import Runner
    from bilge.desktop.windows.office import ExcelSheets, SpreadsheetApps

    with pytest.raises(CalcError) as error:
        SpreadsheetApps({"excel": ExcelSheets(), "calc": LibreOfficeCalc(Runner())}).location()
    assert error.value.reason == "not_running"


def test_an_everyday_command_runs_through_the_assembled_assistant(desktop):
    from bilge import assembly, config

    settings = config.Settings(model=config.ModelSettings("lmstudio", "not-needed-for-quick-commands"))
    agent = assembly.build_agent(settings, confirm=lambda question: True)
    before = desktop.volume.state()
    try:
        assert agent.handle("sesi yüzde 40 yap").text == "Ses seviyesi yüzde 40."
        assert desktop.volume.state().level == 40
    finally:
        desktop.volume.set_level(before.level)


def test_the_listening_shortcut_is_registered_and_pressed():
    import threading

    from bilge.desktop import hotkey
    from bilge.desktop.windows import win32

    pressed = threading.Event()
    registered = hotkey.register("Ctrl+Alt+F9", pressed.set)
    try:
        with pytest.raises(hotkey.HotkeyError) as caught:
            hotkey.register("Ctrl+Alt+F9", lambda: None)
        assert caught.value.reason == "taken"
        win32.press(win32.VK_CONTROL, 0x12, 0x78)  # Ctrl, Alt, F9
        assert pressed.wait(3)
    finally:
        registered.stop()
    hotkey.register("Ctrl+Alt+F9", lambda: None).stop()


def test_the_graphics_card_probe_answers_without_crashing_bilge():
    from bilge.voice import gpu

    found = gpu.find_gpus()
    assert isinstance(found, list)
    print("Vulkan devices:", found)
