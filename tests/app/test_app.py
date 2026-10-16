import json
import threading
import time

from bilge import config
from bilge.app import texts
from bilge.app.controller import AssistantController
from bilge.core.language import AssistantLanguage


def wait(condition, qapp, limit=3.0):
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline and not condition():
        qapp.processEvents()
        time.sleep(0.01)
    return condition()


class FakeAssistant:
    def __init__(self, on_event):
        self.on_event = on_event
        self.answers = []
        self.stopped = False

    def start(self):
        self.on_event("status", "listening")

    def stop(self):
        self.stopped = True
        self.on_event("status", "off")

    def answer(self, confirmed):
        self.answers.append(confirmed)

    def shortcut_pressed(self):
        self.on_event("status", "awake")


class FakeFrontEnd:
    def start(self):
        pass

    def stop(self):
        pass


def controller(built=None, gate=None):
    built = built if built is not None else []

    def build(settings, on_event):
        if gate is not None:
            gate.wait(2)
        assistant = FakeAssistant(on_event)
        built.append(assistant)
        return assistant, FakeFrontEnd()

    return AssistantController(build=build, load=config.Settings, prepare=lambda settings, cancelled: None), built


def test_the_controller_starts_reports_and_stops(qapp):
    found, built = controller()
    statuses, heard = [], []
    found.status_changed.connect(statuses.append)
    found.heard.connect(heard.append)
    found.start()
    assert wait(lambda: statuses[-1:] == ["listening"], qapp)
    built[0].on_event("heard", "saat kaç")
    found.answer(True)
    assert wait(lambda: heard == ["saat kaç"], qapp) and built[0].answers == [True]
    found.stop()
    assert built[0].stopped and wait(lambda: statuses[-1] == "off", qapp) and not found.is_on


def test_a_start_finished_after_a_stop_is_shut_down(qapp):
    gate = threading.Event()
    found, built = controller(gate=gate)
    statuses = []
    found.status_changed.connect(statuses.append)
    found.start()
    found.stop()
    gate.set()
    assert wait(lambda: built and built[0].stopped, qapp)
    assert not found.is_on and statuses[-1] == "off"


def test_a_failed_start_is_reported(qapp):
    def broken(settings, on_event):
        raise RuntimeError("No model chosen")

    found = AssistantController(build=broken, load=config.Settings, prepare=lambda settings, cancelled: None)
    failures = []
    found.failed.connect(failures.append)
    found.start()
    assert wait(lambda: failures == ["No model chosen"], qapp) and found.status == "failed"


def test_settings_are_saved_with_keys_in_the_key_store(qapp, isolated, tmp_path):
    from bilge.app.settings import SettingsWindow

    texts.use(AssistantLanguage.TURKISH)
    settings = config.Settings(model=config.ModelSettings("lmstudio", "qwen"))
    window = SettingsWindow(settings, tmp_path / "settings.json")
    saved = []
    window.saved.connect(saved.append)
    model = window.pages["model"]
    model.provider.setCurrentIndex(model.provider.findData("groq"))
    model.model.setCurrentText("llama-3.3-70b")
    model.key.setText("gsk-secret")
    window.pages["general"].city.setText("İzmir")
    window.pages["voice"].voice.setCurrentText("M2")
    window.pages["recognition"].buttons["groq"].setChecked(True)
    window.save()
    stored = config.load_settings(tmp_path / "settings.json")
    assert (stored.model.provider, stored.model.model, stored.weather_city) == ("groq", "llama-3.3-70b", "İzmir")
    assert (stored.voice.voice, stored.voice.recognizer) == ("M2", "groq")
    assert isolated == {"groq": "gsk-secret"}
    assert "gsk-secret" not in (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert saved and settings.model.provider == "lmstudio"


def test_setup_collects_every_choice(qapp, isolated, tmp_path):
    from bilge.app.setup import SetupWizard

    wizard = SetupWizard(config.Settings(), tmp_path / "settings.json")
    wizard.language.setCurrentIndex(wizard.language.findData("en"))
    wizard.model.provider.setCurrentIndex(wizard.model.provider.findData("ollama"))
    wizard.model.model.setCurrentText("qwen3:8b")
    wizard.recognition.buttons["openai"].setChecked(True)
    wizard.input.select("Mikrofon A")
    collected = wizard.collect()
    assert collected.setup_done and collected.language == "en"
    assert (collected.model.provider, collected.model.model) == ("ollama", "qwen3:8b")
    assert (collected.voice.recognizer, collected.voice.input_device) == ("openai", "Mikrofon A")


def test_the_corner_window_asks_and_answers(qapp):
    from bilge.app.hud import Hud

    hud = Hud()
    answers = []
    hud.answered.connect(answers.append)
    hud.show_status("confirming")
    assert not hud.buttons.isHidden()
    hud.yes.click()
    assert answers == [True] and hud.buttons.isHidden()
    hud.enabled = False
    hud.hide()
    hud.show_reply("Saat 14:05.")
    assert not hud.isVisible()


def test_tray_icons_and_the_listen_switch(qapp):
    from bilge.app.tray import Tray, status_icon

    assert not status_icon("thinking").isNull()
    tray = Tray()
    toggles = []
    tray.listen_toggled.connect(toggles.append)
    tray.show_status("listening")
    assert tray.listen.isChecked() and toggles == []
    tray.listen.setChecked(False)
    assert toggles == [False]


def test_autostart_on_linux_is_an_autostart_entry(isolated, tmp_path, monkeypatch):
    import sys

    from bilge.app import autostart

    monkeypatch.setattr(sys, "platform", "linux")
    autostart.set_enabled(True)
    entry = tmp_path / "xdg" / "autostart" / "bilge.desktop"
    assert autostart.is_enabled() and "-m bilge.app" in entry.read_text(encoding="utf-8")
    autostart.set_enabled(False)
    assert not entry.exists()


def test_history_and_memory_pages(qapp, isolated, tmp_path):
    from bilge.app.settings.records import MemoryPage, recent_actions
    from bilge.tools.memory_store import MemoryStore

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "actions.jsonl").write_text(
        "\n".join(json.dumps({"time": f"2026-10-15T10:0{i}", "tool": "setVolume"}) for i in range(3)) + "\nbozuk\n",
        encoding="utf-8",
    )
    assert [a["time"] for a in recent_actions()] == ["2026-10-15T10:02", "2026-10-15T10:01", "2026-10-15T10:00"]
    store = MemoryStore(tmp_path / "data" / "memory.json")
    store.remember("Eşimin adı Ayşe")
    page = MemoryPage(store)
    page.entries.setCurrentRow(0)
    page._forget()
    assert not store.book.entries


def test_first_start_opens_setup_and_later_ones_listen(qapp, isolated, tmp_path, monkeypatch):
    from bilge.app.shell import Shell

    path = tmp_path / "settings.json"
    started = []
    found, _ = controller()
    monkeypatch.setattr(found, "start", lambda: started.append(True))
    shell = Shell(qapp, found, path)
    shell.begin()
    assert shell.wizard is not None and started == []
    shell.wizard.close()
    config.save_settings(config.Settings(setup_done=True), path)
    shell.begin()
    assert started == [True]


def test_a_key_typed_for_one_provider_is_cleared_when_the_provider_changes(qapp, isolated):
    from bilge.app.settings.model import ModelChooser

    chooser = ModelChooser()
    chooser.load(config.Settings(model=config.ModelSettings("openai", "gpt")))
    chooser.key.setText("sk-openai")
    chooser.provider.setCurrentIndex(chooser.provider.findData("anthropic"))
    chooser.save_secrets()
    assert isolated == {}


def test_opening_the_settings_does_not_open_the_microphone(qapp, isolated, tmp_path, monkeypatch):
    from bilge.app.settings import SettingsWindow, voice

    opened = []
    monkeypatch.setattr(voice.LevelMeter, "listen", lambda self, device: opened.append(device))
    settings = config.Settings()
    settings.voice.input_device = "Mikrofon A"
    SettingsWindow(settings, tmp_path / "settings.json")
    assert opened == []


def test_saving_settings_does_not_switch_listening_on(qapp):
    found, built = controller()
    found.restart()
    assert not found.is_on and built == []


def test_a_start_that_fails_at_the_microphone_stops_what_it_began(qapp):
    class BrokenMicrophone(FakeFrontEnd):
        def start(self):
            raise OSError("No input device")

    assistants = []

    def build(settings, on_event):
        assistant = FakeAssistant(on_event)
        assistants.append(assistant)
        return assistant, BrokenMicrophone()

    found = AssistantController(build=build, load=config.Settings, prepare=lambda settings, cancelled: None)
    found.start()
    assert wait(lambda: found.status == "failed", qapp)
    assert not found.is_on


def test_running_setup_again_keeps_bilge_paused(qapp, isolated, tmp_path, monkeypatch):
    from bilge.app.shell import Shell

    path = tmp_path / "settings.json"
    config.save_settings(config.Settings(setup_done=True), path)
    calls = []
    found, _ = controller()
    monkeypatch.setattr(found, "start", lambda: calls.append("start"))
    monkeypatch.setattr(found, "stop", lambda: calls.append("stop"))
    # Listening was on when the setup was opened again.
    monkeypatch.setattr(AssistantController, "is_on", property(lambda self: True))
    shell = Shell(qapp, found, path)
    shell.open_setup()
    shell._setup_language("en")
    assert "start" not in calls
    shell.wizard.reject()
    assert calls[-1] == "start"


def test_desktop_entry_commands_are_quoted_as_the_spec_says():
    from bilge.app.autostart import exec_line

    assert exec_line(["/usr/bin/python3", "-m", "bilge.app"]) == "/usr/bin/python3 -m bilge.app"
    assert exec_line(["/home/ayşe/My Apps/Bilge 100%.AppImage"]) == '"/home/ayşe/My Apps/Bilge 100%%.AppImage"'


def test_programs_started_by_the_packaged_app_get_the_systems_libraries(monkeypatch):
    import sys

    from bilge.desktop import process

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI123")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/opt/lib")
    assert process.child_environment()["LD_LIBRARY_PATH"] == "/opt/lib"
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG")
    assert "LD_LIBRARY_PATH" not in process.child_environment()


def test_the_shortcut_switches_listening_on_and_then_listens(qapp):
    found, built = controller()
    statuses = []
    found.status_changed.connect(statuses.append)
    found.shortcut_pressed()
    assert wait(lambda: statuses[-1:] == ["awake"], qapp)
    assert found.is_on and len(built) == 1
    found.stop()


def test_the_shortcut_and_wake_word_are_saved(qapp, isolated, tmp_path):
    from PySide6.QtGui import QKeySequence

    from bilge.app.settings import SettingsWindow

    texts.use(AssistantLanguage.TURKISH)
    window = SettingsWindow(config.Settings(), tmp_path / "settings.json")
    general = window.pages["general"]
    general.wake_word.setChecked(False)
    window.save()
    assert window.message.text() == texts.t("general.no_way_to_wake")
    general.hotkey.setKeySequence(QKeySequence("Shift+B"))
    window.save()
    assert "Shift+B" in window.message.text()
    assert not (tmp_path / "settings.json").exists()
    general.hotkey.setKeySequence(QKeySequence("Shift+Ctrl+B"))
    window.pages["recognition"].placement.accelerator.setCurrentIndex(2)
    window.pages["recognition"].placement.unload.setCurrentIndex(1)
    window.save()
    voice = config.load_settings(tmp_path / "settings.json").voice
    assert (voice.hotkey, voice.wake_word, voice.accelerator) == ("Ctrl+Shift+B", False, "gpu")
    assert voice.unload_minutes == 10


def test_a_newer_release_is_offered_in_the_menu(qapp):
    from bilge.app.tray import Tray
    from bilge.update import Release

    tray = Tray()
    notified = []
    tray.notify = notified.append
    assert not tray.update.isVisible()
    release = Release("0.2.0", "https://github.com/coderssociety/bilge-desktop/releases/tag/v0.2.0")
    tray.show_update(release, announce=True)
    tray.show_update(release, announce=False)
    assert tray.update.isVisible() and "0.2.0" in tray.update.text()
    assert len(notified) == 1


def test_the_shortcut_is_ignored_while_the_settings_are_open(qapp, isolated, tmp_path, monkeypatch):
    from bilge.app.shell import Shell

    found, _ = controller()
    pressed = []
    monkeypatch.setattr(found, "shortcut_pressed", lambda: pressed.append(True))
    shell = Shell(qapp, found, tmp_path / "settings.json")
    shell.open_settings()
    shell.shortcut_pressed()
    assert pressed == []
    shell.settings_window.reject()
    shell.shortcut_pressed()
    assert pressed == [True]


def test_a_shortcut_that_fails_brings_the_wake_word_back(qapp, isolated, tmp_path, monkeypatch):
    from bilge.app.shell import Shell

    path = tmp_path / "settings.json"
    settings = config.Settings(setup_done=True)
    settings.voice.wake_word, settings.voice.hotkey = False, "Ctrl+Shift+B"
    config.save_settings(settings, path)
    found, _ = controller()
    shell = Shell(qapp, found, path)
    messages = []
    monkeypatch.setattr(shell, "_failed", messages.append)
    shell._shortcut_failed("taken")
    assert config.load_settings(path).voice.wake_word
    assert "Ctrl+Shift+B" in messages[0] and texts.t("hotkey.wake_word_back") in messages[0]
    assert texts.status("listening") == texts.t("status.listening")


def test_garbage_is_collected_on_the_window_thread(qapp):
    import gc

    from bilge.app.collector import WindowThreadCollector

    collector = WindowThreadCollector()
    collector.start()
    try:
        assert not gc.isenabled()
        for _ in range(20_000):
            cycle = []
            cycle.append(cycle)
        collector.collect_if_due()
        assert gc.get_count()[0] < 1000
    finally:
        collector.stop()
    assert gc.isenabled()
