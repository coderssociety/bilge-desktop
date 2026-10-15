"""Language, how the conversation flows, the corner window, starting with the computer, and the weather city."""

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QLineEdit, QWidget

from bilge import config
from bilge.app import autostart
from bilge.app.texts import t
from bilge.core.language import AssistantLanguage


class GeneralPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.language = QComboBox()
        self.language.addItem("Türkçe", AssistantLanguage.TURKISH.value)
        self.language.addItem("English", AssistantLanguage.ENGLISH.value)
        self.follow_up = QCheckBox(t("general.follow_up"))
        self.barge_in = QCheckBox(t("general.barge_in"))
        self.hud = QCheckBox(t("general.hud"))
        self.autostart = QCheckBox(t("general.autostart"))
        self.city = QLineEdit()
        form = QFormLayout(self)
        form.addRow(t("general.language"), self.language)
        form.addRow("", QLabel(t("general.language_note")))
        for box in (self.follow_up, self.barge_in, self.hud, self.autostart):
            form.addRow("", box)
        form.addRow(t("general.city"), self.city)

    def load(self, settings: config.Settings) -> None:
        self.language.setCurrentIndex(max(0, self.language.findData(settings.language)))
        self.follow_up.setChecked(settings.voice.follow_up)
        self.barge_in.setChecked(settings.voice.barge_in)
        self.hud.setChecked(settings.show_hud)
        self.autostart.setChecked(autostart.is_enabled())
        self.city.setText(settings.weather_city)

    def apply(self, settings: config.Settings) -> None:
        settings.language = self.language.currentData()
        settings.voice.follow_up = self.follow_up.isChecked()
        settings.voice.barge_in = self.barge_in.isChecked()
        settings.show_hud = self.hud.isChecked()
        settings.weather_city = self.city.text().strip() or settings.weather_city

    def save_secrets(self) -> None:
        pass

    def after_save(self) -> None:
        if self.autostart.isChecked() != autostart.is_enabled():
            autostart.set_enabled(self.autostart.isChecked())
