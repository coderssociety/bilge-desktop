"""Where speech is recognized (on this computer or through an API), with advice from the hardware, and teaching
Bilge the owner's voice."""

import psutil
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from bilge import assembly, config
from bilge.app import worker
from bilge.app.texts import t
from bilge.core.language import AssistantLanguage
from bilge.voice import enrollment

# Below this many physical cores, Whisper's large model takes seconds per command on the processor.
LOCAL_ENOUGH_CORES = 8
ENGINES = ("local", "openai", "groq")


def advice() -> str:
    cores = psutil.cpu_count(logical=False) or psutil.cpu_count() or 1
    memory = round(psutil.virtual_memory().total / (1 << 30))
    hint = t("recognition.hint_local") if cores >= LOCAL_ENOUGH_CORES else t("recognition.hint_api")
    return t("recognition.hint", cores=cores, memory=memory, advice=hint)


class RecognitionChooser(QWidget):
    def __init__(self, with_speaker: bool = True) -> None:
        super().__init__()
        self.group = QButtonGroup(self)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"<b>{t('recognition.engine')}</b>"))
        self.buttons = {}
        for engine in ENGINES:
            button = QRadioButton(t(f"recognition.{engine}"))
            self.group.addButton(button)
            self.buttons[engine] = button
            layout.addWidget(button)
        self.key = QLineEdit(echoMode=QLineEdit.EchoMode.Password, placeholderText=t("model.key_placeholder"))
        self.key_state = QLabel(wordWrap=True)
        layout.addWidget(self.key)
        layout.addWidget(self.key_state)
        layout.addWidget(QLabel(advice(), wordWrap=True))
        self.speaker = QCheckBox(t("recognition.speaker"))
        self.voice_state = QLabel(wordWrap=True)
        self.enroll = QPushButton(t("recognition.enroll"))
        self.forget = QPushButton(t("recognition.forget_voice"))
        self.enroll.clicked.connect(self._enroll)
        self.forget.clicked.connect(self._forget)
        if with_speaker:
            layout.addSpacing(12)
            layout.addWidget(self.speaker)
            row = QHBoxLayout()
            row.addWidget(self.enroll)
            row.addWidget(self.forget)
            row.addStretch()
            layout.addLayout(row)
            layout.addWidget(self.voice_state)
        layout.addStretch()
        self.group.buttonToggled.connect(lambda *_: self._engine_changed())
        self.language = AssistantLanguage.TURKISH
        self.input_device: str | None = None

    @property
    def engine(self) -> str:
        return next((name for name, button in self.buttons.items() if button.isChecked()), "local")

    def load(self, settings: config.Settings) -> None:
        self.buttons.get(settings.voice.recognizer, self.buttons["local"]).setChecked(True)
        self.speaker.setChecked(settings.voice.speaker_check)
        self.language = settings.assistant_language
        self.input_device = settings.voice.input_device
        self._engine_changed()
        self._show_voice()

    def apply(self, settings: config.Settings) -> None:
        if settings.voice.recognizer != self.engine:
            settings.voice.recognizer_model = ""
        settings.voice.recognizer = self.engine
        settings.voice.speaker_check = self.speaker.isChecked() and enrollment.voice_store().load() is not None

    def save_secrets(self) -> None:
        if self.engine != "local" and self.key.text().strip():
            config.store_api_key(self.engine, self.key.text().strip())
            self.key.clear()

    def _engine_changed(self) -> None:
        self.key.clear()
        api = self.engine != "local"
        self.key.setVisible(api)
        self.key_state.setVisible(api)
        if api:
            self.key_state.setText(t("model.key_stored") if config.api_key(self.engine) else t("model.key_missing"))

    def _show_voice(self) -> None:
        stored = enrollment.voice_store().load()
        self.voice_state.setText(
            t("recognition.enrolled", date=stored.created[:10]) if stored else t("recognition.not_enrolled")
        )
        self.forget.setEnabled(stored is not None)
        self.speaker.setEnabled(stored is not None)

    def _enroll(self) -> None:
        dialog = EnrollmentDialog(self.language, self.input_device, self)
        dialog.finished.connect(lambda result: self._enrolled(bool(result)))
        dialog.open()

    def _enrolled(self, saved: bool) -> None:
        if saved:
            self.speaker.setChecked(True)
        self._show_voice()

    def _forget(self) -> None:
        enrollment.voice_store().delete()
        self.speaker.setChecked(False)
        self._show_voice()


class EnrollmentDialog(QDialog):
    """Five sentences, one at a time; only the voice embeddings are kept."""

    def __init__(self, language: AssistantLanguage, input_device: str | None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("enroll.title"))
        self.sentences = enrollment.SENTENCES[language]
        self.input_device = input_device
        self.recordings = []
        self.sentence = QLabel(wordWrap=True)
        self.sentence.setStyleSheet("font-size: 16px; font-weight: 600; margin: 12px 0;")
        self.progress = QLabel()
        self.message = QLabel(wordWrap=True)
        self.record = QPushButton(t("enroll.record"))
        self.record.clicked.connect(self._record)
        layout = QVBoxLayout(self)
        for widget in (QLabel(t("enroll.intro"), wordWrap=True), QLabel(t("enroll.read")), self.sentence,
                       self.progress, self.record, self.message):  # fmt: skip
            layout.addWidget(widget)
        self.resize(460, 260)
        self._show_next()

    def _show_next(self) -> None:
        index = len(self.recordings)
        self.sentence.setText(f"“{self.sentences[index]}”")
        self.progress.setText(f"{index + 1} / {len(self.sentences)}")

    def _record(self) -> None:
        self.record.setEnabled(False)
        self.record.setText(t("enroll.recording"))
        worker.run(lambda: enrollment.record(self.input_device), self._recorded, self._failed, owner=self)

    def _recorded(self, samples) -> None:
        self.recordings.append(samples)
        self.record.setText(t("enroll.record"))
        if len(self.recordings) < len(self.sentences):
            self.record.setEnabled(True)
            self._show_next()
            return
        recordings = list(self.recordings)

        def save():
            from bilge.voice import models

            assembly.download_missing((models.CAMPLUS,))
            return enrollment.enroll(recordings, assembly.models_dir())

        worker.run(save, lambda _: self._saved(), self._failed, owner=self)

    def _saved(self) -> None:
        self.message.setText(t("enroll.done"))
        self.accept()

    def _failed(self, error: str) -> None:
        self.message.setText(error)
        self.recordings = []
        self.record.setText(t("enroll.record"))
        self.record.setEnabled(True)
        self._show_next()
