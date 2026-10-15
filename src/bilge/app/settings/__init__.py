"""The settings window: one tab per area, saved together."""

import copy
import logging

from keyring.errors import KeyringError
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTabWidget, QVBoxLayout

from bilge import config
from bilge.app.settings.calendar import CalendarPage
from bilge.app.settings.general import GeneralPage
from bilge.app.settings.model import ModelChooser
from bilge.app.settings.recognition import RecognitionChooser
from bilge.app.settings.records import AboutPage, HistoryPage, MemoryPage
from bilge.app.settings.voice import VoicePage
from bilge.app.texts import t
from bilge.app.tray import app_icon

log = logging.getLogger(__name__)


class SettingsWindow(QDialog):
    # The saved settings; the app restarts the assistant with them.
    saved = Signal(object)

    def __init__(self, settings: config.Settings, path=None) -> None:
        super().__init__()
        self.path = path
        self.setWindowTitle(t("settings.title"))
        self.setWindowIcon(app_icon())
        self.original = settings
        self.pages = {
            "general": GeneralPage(), "model": ModelChooser(), "voice": VoicePage(),
            "recognition": RecognitionChooser(), "calendar": CalendarPage(),
        }  # fmt: skip
        tabs = QTabWidget()
        for name, page in self.pages.items():
            page.load(settings)
            tabs.addTab(page, t(f"tab.{name}"))
        tabs.addTab(MemoryPage(), t("tab.memory"))
        tabs.addTab(HistoryPage(), t("tab.history"))
        tabs.addTab(AboutPage(), t("tab.about"))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(t("settings.save"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("settings.cancel"))
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        self.message = QLabel(wordWrap=True)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(self.message)
        layout.addWidget(buttons)
        self.resize(620, 520)

    def collect(self) -> config.Settings:
        """The settings as the window shows them; the loaded ones are left as they were."""
        updated = copy.deepcopy(self.original)
        for page in self.pages.values():
            page.apply(updated)
        return updated

    def save(self) -> None:
        updated = self.collect()
        try:
            for page in self.pages.values():
                page.save_secrets()
            config.save_settings(updated, self.path)
            self.pages["general"].after_save()
        except KeyringError:
            self.message.setText(t("settings.no_keyring"))
            return
        except OSError as error:
            self.message.setText(t("settings.failed", error=error))
            return
        self.saved.emit(updated)
        self.accept()
