"""The first-run setup: language, the language model, speech recognition, the voice models, the microphone, and
starting with the computer."""

import copy

from keyring.errors import KeyringError
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from bilge import assembly, config
from bilge.app import autostart, worker
from bilge.app.settings.model import LOCAL, ModelChooser, list_models
from bilge.app.settings.recognition import RecognitionChooser
from bilge.app.settings.voice import DeviceChoice, LevelMeter
from bilge.app.texts import t
from bilge.app.tray import app_icon
from bilge.core.language import AssistantLanguage
from bilge.llm.providers import PRESETS


def page(title: str, text: str | None = None) -> tuple[QWizardPage, QVBoxLayout]:
    built = QWizardPage()
    built.setTitle(title)
    layout = QVBoxLayout(built)
    if text:
        layout.addWidget(QLabel(text, wordWrap=True))
    return built, layout


class SetupWizard(QWizard):
    finished_setup = Signal(object)
    # The language was changed on the first page; the wizard is rebuilt in it.
    language_chosen = Signal(str)

    def __init__(self, settings: config.Settings, path=None) -> None:
        super().__init__()
        self.path = path
        self.settings = copy.deepcopy(settings)
        self.setWindowTitle(t("setup.title"))
        self.setWindowIcon(app_icon())
        # Qt's own button names would stay in English.
        for button, key in ((QWizard.WizardButton.BackButton, "setup.back"), (QWizard.WizardButton.NextButton, "setup.next"),
                            (QWizard.WizardButton.FinishButton, "setup.finish"),
                            (QWizard.WizardButton.CancelButton, "setup.cancel")):  # fmt: skip
            self.setButtonText(button, t(key))
        self.addPage(self._welcome())
        self.addPage(self._model())
        self.addPage(self._recognition())
        self.addPage(self._download())
        self.microphone_page = self.addPage(self._microphone())
        self.addPage(self._done())
        # The microphone is only opened while its page is shown.
        self.currentIdChanged.connect(self._page_changed)
        self.finished.connect(lambda _: self.meter.stop())
        self.resize(640, 520)

    def _welcome(self) -> QWizardPage:
        built, layout = page(t("setup.welcome"))
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(112, 112))
        layout.addWidget(logo)
        layout.addWidget(QLabel(t("setup.welcome_text"), wordWrap=True))
        self.language = QComboBox()
        self.language.addItem("Türkçe", AssistantLanguage.TURKISH.value)
        self.language.addItem("English", AssistantLanguage.ENGLISH.value)
        self.language.setCurrentIndex(max(0, self.language.findData(self.settings.language)))
        self.language.currentIndexChanged.connect(lambda: self.language_chosen.emit(self.language.currentData()))
        layout.addWidget(QLabel(t("general.language")))
        layout.addWidget(self.language)
        layout.addStretch()
        return built

    def _model(self) -> QWizardPage:
        built, layout = page(t("setup.model"), t("setup.model_text"))
        self.model = ModelChooser()
        self.model.load(self.settings)
        self.found = QLabel(wordWrap=True)
        layout.addWidget(self.model)
        layout.addWidget(self.found)
        self._look_for_local_servers()
        return built

    def _look_for_local_servers(self) -> None:
        """A model server already running here is the private, free choice; it is picked when found."""

        def search() -> tuple[str, list[str]] | None:
            for provider in LOCAL:
                try:
                    found = list_models(provider, None, None)
                except Exception:  # noqa: BLE001 - not running
                    continue
                if found:
                    return provider, found
            return None

        def show(result) -> None:
            if not result or self.settings.model.model:
                return
            provider, found = result
            self.model.provider.setCurrentIndex(self.model.provider.findData(provider))
            self.model.model.clear()
            self.model.model.addItems(found)
            self.found.setText(t("setup.local_found", name=PRESETS[provider].name))

        worker.run(search, show, lambda _: None, owner=self)

    def _recognition(self) -> QWizardPage:
        built, layout = page(t("setup.recognition"))
        self.recognition = RecognitionChooser(with_speaker=False)
        self.recognition.load(self.settings)
        layout.addWidget(self.recognition)
        return built

    def _download(self) -> QWizardPage:
        built = _DownloadPage()
        built.setTitle(t("setup.download"))
        layout = QVBoxLayout(built)
        layout.addWidget(QLabel(t("setup.download_text"), wordWrap=True))
        self.download_page = built
        self.progress = QProgressBar(minimum=0, maximum=100)
        self.download_state = QLabel(wordWrap=True)
        self.download_button = QPushButton(t("setup.download_start"))
        self.download_button.clicked.connect(self._start_download)
        for widget in (self.download_button, self.progress, self.download_state):
            layout.addWidget(widget)
        layout.addStretch()
        return built

    def _start_download(self) -> None:
        self.recognition.apply(self.settings)
        self.download_button.setEnabled(False)
        self.download_page.set_busy(True)
        # Read now on the window thread; which Whisper model is needed depends on the graphics card, and finding it
        # out takes a moment, so that happens with the download.
        chosen = copy.deepcopy(self.settings)
        relay = _Progress()
        relay.changed.connect(self._show_progress)

        def progress(spec, done: int, total: int) -> None:
            relay.changed.emit(spec.name, int(done * 100 / max(total, 1)))

        def download() -> None:
            assembly.download_missing(assembly.voice_models(chosen), progress)

        def finished(_=None) -> None:
            self.progress.setValue(100)
            self.download_state.setText(t("setup.download_done"))
            self.download_page.set_busy(False)

        def failed(error: str) -> None:
            self.download_state.setText(error)
            self.download_button.setEnabled(True)
            self.download_page.set_busy(False)

        # Kept until the download ends, so its signal has somewhere to go.
        self._relay = relay
        worker.run(download, finished, failed, owner=self)

    def _show_progress(self, name: str, percent: int) -> None:
        self.progress.setValue(percent)
        self.download_state.setText(name)

    def _microphone(self) -> QWizardPage:
        built, layout = page(t("setup.microphone"), t("setup.microphone_text"))
        self.input = DeviceChoice("input")
        self.input.select(self.settings.voice.input_device)
        self.meter = LevelMeter()
        self.input.currentIndexChanged.connect(lambda: self.meter.listen(self.input.currentData()))
        layout.addWidget(self.input)
        layout.addWidget(self.meter)
        layout.addStretch()
        return built

    def _page_changed(self, page_id: int) -> None:
        if page_id == self.microphone_page:
            self.meter.listen(self.input.currentData())
        else:
            self.meter.stop()

    def _done(self) -> QWizardPage:
        built, layout = page(t("setup.done"), t("setup.done_text"))
        examples = QLabel(t("setup.examples"))
        examples.setStyleSheet("font-size: 15px; margin: 8px 0;")
        self.autostart = QCheckBox(t("general.autostart"))
        self.autostart.setChecked(True)
        layout.addWidget(examples)
        layout.addWidget(self.autostart)
        layout.addStretch()
        return built

    def collect(self) -> config.Settings:
        settings = copy.deepcopy(self.settings)
        settings.language = self.language.currentData()
        self.model.apply(settings)
        self.recognition.apply(settings)
        settings.voice.input_device = self.input.currentData()
        settings.setup_done = True
        return settings

    def accept(self) -> None:
        """Saves before closing; if that fails, the wizard stays open and says why."""
        settings = self.collect()
        try:
            self.model.save_secrets()
            self.recognition.save_secrets()
            config.save_settings(settings, self.path)
            if self.autostart.isChecked() != autostart.is_enabled():
                autostart.set_enabled(self.autostart.isChecked())
        except KeyringError:
            QMessageBox.warning(self, t("setup.title"), t("settings.no_keyring"))
            return
        except OSError as error:
            QMessageBox.warning(self, t("setup.title"), t("settings.failed", error=error))
            return
        super().accept()
        self.finished_setup.emit(settings)


class _DownloadPage(QWizardPage):
    """Next waits while the models download, so the assistant doesn't start a second download of the same files."""

    def __init__(self) -> None:
        super().__init__()
        self._busy = False

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.completeChanged.emit()

    def isComplete(self) -> bool:  # noqa: N802 - Qt's name
        return not self._busy


class _Progress(QObject):
    """Carries download progress from the download thread to the window."""

    changed = Signal(str, int)
