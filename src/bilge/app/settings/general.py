"""Language, how Bilge is called and how the conversation flows, the corner window, starting with the computer,
updates, and the weather city."""

import contextlib
import html
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from bilge import config, update
from bilge.app import autostart, worker
from bilge.app.shortcut import listen_command
from bilge.app.texts import t
from bilge.core.language import AssistantLanguage
from bilge.desktop.hotkey.shortcut import InvalidShortcut, parse


class GeneralPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.language = QComboBox()
        self.language.addItem("Türkçe", AssistantLanguage.TURKISH.value)
        self.language.addItem("English", AssistantLanguage.ENGLISH.value)
        self.wake_word = QCheckBox(t("general.wake_word"))
        self.hotkey = QKeySequenceEdit()
        self.hotkey.setMaximumSequenceLength(1)
        clear = QPushButton(t("general.hotkey_clear"))
        clear.clicked.connect(self.hotkey.clear)
        hotkey_row = QHBoxLayout()
        hotkey_row.addWidget(self.hotkey, 1)
        hotkey_row.addWidget(clear)
        self.follow_up = QCheckBox(t("general.follow_up"))
        self.barge_in = QCheckBox(t("general.barge_in"))
        self.hud = QCheckBox(t("general.hud"))
        self.autostart = QCheckBox(t("general.autostart"))
        self.updates = QCheckBox(t("general.updates"))
        self.check_now = QPushButton(t("general.check_now"))
        self.check_now.clicked.connect(self._check_now)
        self.update_state = QLabel(wordWrap=True, openExternalLinks=True)
        self.city = QLineEdit()
        form = QFormLayout(self)
        form.addRow(t("general.language"), self.language)
        form.addRow("", QLabel(t("general.language_note")))
        form.addRow("", self.wake_word)
        form.addRow(t("general.hotkey"), hotkey_row)
        form.addRow("", QLabel(t("general.hotkey_note"), wordWrap=True))
        if sys.platform.startswith("linux"):
            command = QLabel(f"{t('general.listen_command')}<br><code>{html.escape(listen_command())}</code>",
                             wordWrap=True)  # fmt: skip
            command.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow("", command)
        for box in (self.follow_up, self.barge_in, self.hud, self.autostart, self.updates):
            form.addRow("", box)
        updates_row = QHBoxLayout()
        updates_row.addWidget(self.check_now)
        updates_row.addWidget(self.update_state, 1)
        form.addRow("", updates_row)
        form.addRow(t("general.city"), self.city)

    def load(self, settings: config.Settings) -> None:
        self.language.setCurrentIndex(max(0, self.language.findData(settings.language)))
        self.wake_word.setChecked(settings.voice.wake_word)
        self.hotkey.setKeySequence(QKeySequence(settings.voice.hotkey))
        self.follow_up.setChecked(settings.voice.follow_up)
        self.barge_in.setChecked(settings.voice.barge_in)
        self.hud.setChecked(settings.show_hud)
        self.autostart.setChecked(autostart.is_enabled())
        self.updates.setChecked(settings.check_updates)
        self.city.setText(settings.weather_city)

    def _hotkey_text(self) -> str:
        return self.hotkey.keySequence().toString(QKeySequence.SequenceFormat.PortableText)

    def problem(self) -> str | None:
        """Why the page can't be saved as it is."""
        text = self._hotkey_text()
        if text:
            try:
                parse(text)
            except InvalidShortcut:
                return t("hotkey.invalid", shortcut=text)
        if not self.wake_word.isChecked() and not text:
            return t("general.no_way_to_wake")
        return None

    def apply(self, settings: config.Settings) -> None:
        settings.language = self.language.currentData()
        text = self._hotkey_text()
        # An invalid one was already pointed out by problem(); the saved shortcut then stays.
        with contextlib.suppress(InvalidShortcut):
            settings.voice.hotkey = parse(text).text if text else ""
        settings.voice.wake_word = self.wake_word.isChecked() or not settings.voice.hotkey
        settings.voice.follow_up = self.follow_up.isChecked()
        settings.voice.barge_in = self.barge_in.isChecked()
        settings.show_hud = self.hud.isChecked()
        settings.check_updates = self.updates.isChecked()
        settings.weather_city = self.city.text().strip() or settings.weather_city

    def save_secrets(self) -> None:
        pass

    def after_save(self) -> None:
        if self.autostart.isChecked() != autostart.is_enabled():
            autostart.set_enabled(self.autostart.isChecked())

    def _check_now(self) -> None:
        running = update.current_version()
        if running is None:
            self.update_state.setText(t("update.dev"))
            return
        self.check_now.setEnabled(False)
        self.update_state.setText(t("update.checking"))

        def done(release: update.Release | None) -> None:
            self.check_now.setEnabled(True)
            if release is None:
                self.update_state.setText(t("update.current", version=running))
            else:
                self.update_state.setText(t("update.available", version=html.escape(release.version),
                                            url=html.escape(release.url, quote=True)))  # fmt: skip

        def failed(error: str) -> None:
            self.check_now.setEnabled(True)
            self.update_state.setText(t("update.failed", error=html.escape(error)))

        worker.run(lambda: update.newer_release(running), done, failed, owner=self)
