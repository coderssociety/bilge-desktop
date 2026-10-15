import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


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
