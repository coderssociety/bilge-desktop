import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
    # Qt torn down by Python's own exit, in no particular order, sometimes crashes the process after every test
    # has passed; the app is shut down here instead, as Bilge itself does.
    for window in app.topLevelWidgets():
        window.close()
    app.processEvents()
    app.shutdown()


@pytest.fixture(autouse=True)
def collect_on_the_test_thread():
    """As in the app (bilge.app.collector): windows a test leaves behind are collected here, on the test's own
    thread, never by a background thread that happens to allocate (which crashes Qt)."""
    import gc

    gc.disable()
    yield
    gc.collect()
    gc.enable()


@pytest.fixture(autouse=True)
def quiet_microphone(monkeypatch):
    """The level meter would open the real microphone."""
    from bilge.app.settings import voice

    monkeypatch.setattr(voice.LevelMeter, "listen", lambda self, device: None)
    monkeypatch.setattr(voice, "devices", lambda kind: ["Mikrofon A", "Hoparlör B"])


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Settings, keys and data in a temporary place."""
    from bilge import config

    keys = {}
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(config, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(config, "api_key", lambda name: keys.get(name))
    monkeypatch.setattr(config, "store_api_key", lambda name, key: keys.__setitem__(name, key))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return keys
