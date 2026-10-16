"""Saves the README's screenshots from the app's real windows, filled with sample settings.

Settings and keys come from a temporary folder and nothing is looked up on this computer (no key store, no sound
devices, no model servers), so no one's own data ends up in a picture. Run on the system whose look the pictures
should have, once per language:

    uv run python scripts/screenshots.py docs/images en
    uv run python scripts/screenshots.py docs/images/tr tr
"""

import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import QApplication, QTabWidget

from bilge import config
from bilge.app import texts
from bilge.app.settings import voice
from bilge.core.language import AssistantLanguage

SETTLE_SECONDS = 0.5


@dataclass(frozen=True)
class Sample:
    city: str
    confirm_heard: str
    confirm_reply: str
    answer_heard: str
    answer_reply: str


SAMPLES = {
    AssistantLanguage.ENGLISH: Sample(
        "London",
        "Bilge, add a dentist appointment on Friday at ten",
        "Shall I add “Dentist” to your calendar on Friday at 10:00?",
        "Bilge, what's the weather like tomorrow?",
        "Tomorrow in London: partly cloudy, 14 to 19 degrees, a light chance of rain in the evening.",
    ),
    AssistantLanguage.TURKISH: Sample(
        "İstanbul",
        "Bilge, cuma saat onda diş hekimi randevusu ekle",
        "Cuma 10:00'a “Diş hekimi” etkinliğini takvimine ekleyeyim mi?",
        "Bilge, yarın hava nasıl olacak?",
        "Yarın İstanbul'da parçalı bulutlu, sıcaklık 14 ile 19 derece arasında; akşam hafif yağmur ihtimali var.",
    ),
}


def settle(app: QApplication) -> None:
    deadline = time.monotonic() + SETTLE_SECONDS
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)


def sample_settings(language: AssistantLanguage) -> config.Settings:
    settings = config.Settings(language=language.value, weather_city=SAMPLES[language].city, setup_done=True)
    settings.model = config.ModelSettings("lmstudio", "qwen3-30b-a3b-instruct-2507")
    settings.voice.hotkey = "Ctrl+Shift+Space"
    return settings


def main(out: Path, language: AssistantLanguage) -> int:
    out.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="bilge-screenshots-"))
    config.config_dir = lambda: folder
    config.data_dir = lambda: folder
    config.api_key = lambda name: None
    voice.devices = lambda kind: ["Default"]
    app = QApplication(sys.argv[:1])
    texts.use(language)
    settings = sample_settings(language)
    sample = SAMPLES[language]

    from bilge.app.hud import Hud
    from bilge.app.settings import SettingsWindow
    from bilge.app.setup import SetupWizard

    wizard = SetupWizard(config.Settings(language=language.value), folder / "settings.json")
    wizard.show()
    settle(app)
    wizard.grab().save(str(out / "setup.png"))
    wizard.close()

    window = SettingsWindow(settings, folder / "settings.json")
    tabs = window.findChild(QTabWidget)
    window.show()
    for index, name in ((0, "settings-general"), (1, "settings-model"), (3, "settings-recognition")):
        tabs.setCurrentIndex(index)
        settle(app)
        window.grab().save(str(out / f"{name}.png"))
    window.close()

    hud = Hud()
    hud.show_heard(sample.confirm_heard)
    hud.show_reply(sample.confirm_reply)
    hud.show_status("confirming")
    settle(app)
    hud.grab().save(str(out / "hud-confirm.png"))
    hud.show_heard(sample.answer_heard)
    hud.show_reply(sample.answer_reply)
    hud.show_status("speaking")
    settle(app)
    hud.grab().save(str(out / "hud-answer.png"))
    hud.hide()
    app.shutdown()
    return 0


if __name__ == "__main__":
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/images")
    sys.exit(main(folder, AssistantLanguage(sys.argv[2] if len(sys.argv) > 2 else "en")))
