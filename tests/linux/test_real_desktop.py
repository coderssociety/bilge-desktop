"""The Linux tools against the real programs, on the screenless desktop of scripts/linux-check. Skipped elsewhere."""

import os
import signal
import subprocess
import sys
import time
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from bilge.core.language import AssistantLanguage
from bilge.desktop.base import MediaCommand, ScreenshotArea

pytestmark = pytest.mark.skipif(
    not (sys.platform.startswith("linux") and os.environ.get("BILGE_REAL_DESKTOP")),
    reason="needs the desktop set up by scripts/linux-check",
)
TR = AssistantLanguage.TURKISH
SYSTEM_PYTHON = "/usr/bin/python3"
EDITOR = """
import sys, tkinter as tk
from pathlib import Path
root = tk.Tk()
root.title("Bilge deneme")
text = tk.Text(root)
text.pack()
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
def editor(tmp_path):
    """A small window with a text box in front; returns a function that closes it and gives back what it holds."""
    script = tmp_path / "editor.py"
    script.write_text(EDITOR, encoding="utf-8")
    result = tmp_path / "typed.txt"
    process = subprocess.Popen([SYSTEM_PYTHON, str(script), str(result)])
    assert eventually(lambda: subprocess.run(["xdotool", "search", "--name", "Bilge deneme"],
                                             capture_output=True).returncode == 0)  # fmt: skip
    subprocess.run(["xdotool", "search", "--name", "Bilge deneme", "windowactivate", "--sync"], check=True)

    def finish() -> str:
        Path(f"{result}.stop").touch()
        process.wait(10)
        return result.read_text(encoding="utf-8")

    yield finish
    if process.poll() is None:
        process.kill()


def test_turkish_text_is_typed_into_the_window_in_front(desktop, editor):
    front = desktop.keyboard.front_window()
    # Tk sets no process id on its window, so the window class names it.
    assert front is not None and front.name == "tk"
    desktop.keyboard.type("Merhaba dünya, ŞĞÜİıçö")
    desktop.keyboard.new_line()
    desktop.keyboard.type("ikinci")
    desktop.keyboard.backspace(2)
    assert editor() == "Merhaba dünya, ŞĞÜİıçö\nikin"


def test_dictation_types_what_is_said_and_takes_it_back(desktop, editor):
    from bilge.tools.desktop.typing import DictationSession, front_app

    session = DictationSession(desktop.keyboard, TR)
    session.begin(front_app(desktop.keyboard))
    assert session.handle("bugün hava çok güzel") == ""
    assert session.handle("yeni satır") == ""
    assert session.handle("yarın görüşürüz") == ""
    assert session.handle("son cümleyi sil") == ""
    assert session.handle("dikteyi bitir") == "Dikte bitti."
    assert editor().startswith("Bugün hava çok güzel")


def test_clipboard_and_selection(desktop):
    desktop.clipboard.write("Panoda Türkçe: şğü")
    assert eventually(lambda: desktop.clipboard.read() == "Panoda Türkçe: şğü", 3)
    subprocess.run(["xclip", "-selection", "primary", "-in"], input="seçili metin", text=True, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # fmt: skip
    assert eventually(lambda: desktop.clipboard.selection() == "seçili metin", 3)


def test_volume_through_pulseaudio(desktop):
    desktop.volume.set_level(35)
    assert desktop.volume.state().level == 35
    desktop.volume.set_muted(True)
    assert desktop.volume.state().muted
    desktop.volume.set_level(60)
    assert desktop.volume.state() == type(desktop.volume.state())(60, False)


def test_music_player_through_mpris(desktop, tmp_path):
    song = tmp_path / "song.wav"
    with wave.open(str(song), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(8000)
        file.writeframes(b"\0\0" * 8000 * 5)
    player = subprocess.Popen(["mpv", "--no-video", "--ao=null", "--loop=inf", "--force-media-title=Deneme Şarkısı",
                               str(song)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # fmt: skip
    try:
        playing = eventually(lambda: (np := desktop.media.now_playing()) and np.playing and np)
        assert playing.title == "Deneme Şarkısı"
        desktop.media.send(MediaCommand.PAUSE)
        assert eventually(lambda: not desktop.media.now_playing().playing, 5)
    finally:
        player.kill()


def test_notifications_reach_the_notification_service(desktop):
    from bilge.desktop.linux.dbus import SessionBus

    reply = SessionBus().call("org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                              "org.freedesktop.Notifications", "Notify", "susssasa{sv}i",
                              "Bilge", 0, "", "Bilge", "Çay hazır", [], {}, -1)  # fmt: skip
    assert reply[0] > 0
    desktop.notifier.notify("Bilge", "Zamanlayıcı doldu.")


def test_an_app_is_opened_seen_running_and_closed(desktop):
    from bilge.tools.desktop.apps import AppCatalog

    app = AppCatalog(desktop.apps).resolve("mousepad")
    assert app is not None
    desktop.apps.launch(app)
    try:
        assert eventually(lambda: any(a.id == app.id for a in desktop.apps.running()))
    finally:
        assert desktop.apps.quit(app)
    assert eventually(lambda: not any(a.id == app.id for a in desktop.apps.running()), 10)


def test_screenshot_is_saved_and_copied(desktop, tmp_path):
    image = tmp_path / "shot.png"
    assert desktop.screenshots.capture(ScreenshotArea.WHOLE_SCREEN, image)
    assert image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    desktop.screenshots.copy_image(image)
    targets = subprocess.run(["xclip", "-selection", "clipboard", "-target", "TARGETS", "-out"], capture_output=True,
                             text=True)  # fmt: skip
    assert "image/png" in targets.stdout


def test_dark_mode_on_gnome_settings(desktop):
    desktop.session.set_dark_mode(True)
    assert desktop.session.dark_mode() is True
    desktop.session.set_dark_mode(False)
    assert desktop.session.dark_mode() is False


def test_a_file_goes_to_the_freedesktop_trash(desktop, tmp_path, monkeypatch):
    from bilge.tools.desktop.files import FileTools

    home = Path.home()
    doomed = home / "Belgeler" / "eski fatura 2019.txt"
    doomed.parent.mkdir(exist_ok=True)
    doomed.write_text("x")
    folders = SimpleNamespace(home=lambda: home, desktop=lambda: home / "Masaüstü", documents=lambda: home / "Belgeler",
                              downloads=lambda: home / "İndirilenler", pictures=lambda: home / "Resimler")  # fmt: skip
    tools = FileTools(folders, desktop.opener, TR)
    assert "eski fatura 2019.txt" in tools.trash_question({"query": "eski fatura"})
    tools.trash({"query": "eski fatura"})
    assert not doomed.exists()
    assert (home / ".local/share/Trash/files/eski fatura 2019.txt").exists()


@pytest.fixture
def calc_document(tmp_path):
    source = tmp_path / "butce.csv"
    source.write_text("2\n3\n", encoding="utf-8")
    subprocess.run(["soffice", "--headless", "--convert-to", "ods", "--outdir", str(tmp_path), str(source)],
                   check=True, capture_output=True, timeout=120)  # fmt: skip
    office = subprocess.Popen(["soffice", "--headless", "--norestore", str(tmp_path / "butce.ods")],
                              start_new_session=True)  # fmt: skip
    yield tmp_path / "butce.ods"
    os.killpg(office.pid, signal.SIGTERM)
    office.wait(30)


def test_spreadsheet_commands_in_libreoffice_calc(calc_document):
    from bilge.desktop.calc import LibreOfficeCalc
    from bilge.desktop.process import Runner
    from bilge.tools.desktop.spreadsheet import SpreadsheetSession, SpreadsheetTool

    calc = LibreOfficeCalc(Runner())
    assert eventually(calc.is_running)
    # LibreOffice opens the document a moment after it starts.
    assert eventually(lambda: _location(calc), 60)
    tool = SpreadsheetTool(calc, SpreadsheetSession(TR), TR)

    def say(command):
        arguments = {"command": command}
        return tool.question(arguments), tool.run(arguments)

    try:
        assert say("C1'e A1 ile A2'yi topla") == (None, "C1: 5.")
        question, reply = say("C1'e 10 yaz")
        assert question.startswith("C1 dolu") and reply == "C1: 10."
        assert say("geri al") == (None, "Geri aldım, C1: 5.")
        assert say("A1'den A2'ye kadar ortalama kaç") == (None, "Sonuç 2,5.")
        model = {"command": "B1'e ortalamayı hesapla", "target": "B1", "formula": "=AVERAGE(A1,A2)"}
        assert tool.question(model).startswith("B1 hücresine")
        assert tool.run(model) in ("B1: 2.5.", "B1: 2,5.")
    finally:
        calc.close()


def _location(calc):
    from bilge.desktop.calc import CalcError

    try:
        return calc.location()
    except CalcError:
        return None


def test_the_listening_shortcut_is_grabbed_and_pressed_on_x11():
    import threading

    from bilge.desktop import hotkey

    pressed = threading.Event()
    grabbed = hotkey.register("Ctrl+Shift+B", pressed.set)
    try:
        # A second program asking for the same keys is told they are taken.
        with pytest.raises(hotkey.HotkeyError) as caught:
            hotkey.register("Ctrl+Shift+B", lambda: None)
        assert caught.value.reason == "taken"
        subprocess.run(["xdotool", "key", "ctrl+shift+b"], check=True)
        assert pressed.wait(3)
        # Num Lock on must not hide the shortcut.
        pressed.clear()
        subprocess.run(["xdotool", "key", "Num_Lock", "ctrl+shift+b", "Num_Lock"], check=True)
        assert pressed.wait(3)
    finally:
        grabbed.stop()
    again = hotkey.register("Ctrl+Shift+B", lambda: None)
    again.stop()


def test_vulkan_is_asked_about_the_graphics_cards():
    from bilge.voice import gpu

    found = gpu.find_gpus()
    # The container has only Mesa's software renderer, which Whisper must not be sent to.
    assert found, "mesa-vulkan-drivers is installed, so Vulkan lists at least llvmpipe"
    assert all(not card.is_usable for card in found if "llvmpipe" in card.name)
    assert gpu.best_gpu(found, integrated=True) is None


@pytest.mark.skipif(not os.environ.get("BILGE_WHISPER_SERVER"), reason="needs a whisper.cpp build")
def test_whisper_cpp_runs_on_a_vulkan_device(tmp_path):
    import numpy as np

    from bilge.voice.gpu import Gpu, Kind
    from bilge.voice.whisper_cpp import WhisperServer, server_program

    model = Path(os.environ["BILGE_WHISPER_MODEL"])
    software = Gpu(0, "llvmpipe", Kind.PROCESSOR, (1, 3))
    server = WhisperServer(server_program(), model, TR, software, hint="Bilge", pid_file=tmp_path / "pid")
    server.start()
    try:
        assert server.on_card
        with wave.open(os.environ["BILGE_WHISPER_AUDIO"]) as audio:
            samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").astype(np.float32) / 32768
        assert "hava" in server.transcribe(samples).lower()
    finally:
        server.close()
