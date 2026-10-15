"""Bilge's voice (with a preview), and which microphone and speaker it uses, with a level meter to check the
microphone."""

import logging

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget

from bilge import assembly, config
from bilge.app import worker
from bilge.app.texts import t
from bilge.voice.supertonic import VOICES

log = logging.getLogger(__name__)


def devices(kind: str) -> list[str]:
    """Names of the devices that can record ("input") or play ("output"), each once."""
    import sounddevice as sd

    channels = "max_input_channels" if kind == "input" else "max_output_channels"
    return list(dict.fromkeys(d["name"] for d in sd.query_devices() if d[channels] > 0))


def preview(voice: str, output_device: str | None, language) -> None:
    from bilge.voice import models
    from bilge.voice.audio_io import SoundDevice
    from bilge.voice.speech_output import SpeechOutput
    from bilge.voice.supertonic import Supertonic

    assembly.download_missing((models.SUPERTONIC,))
    device = SoundDevice(None, output_device)
    output = SpeechOutput(Supertonic(assembly.models_dir() / models.SUPERTONIC.name), device, language, voice)
    device.start(lambda microphone, played: None)
    try:
        # Returns once everything has been played.
        output.speak(t("voice.preview_text"))
    finally:
        device.stop()


class DeviceChoice(QComboBox):
    def __init__(self, kind: str) -> None:
        super().__init__()
        self.addItem(t("voice.default"), None)
        try:
            for name in devices(kind):
                self.addItem(name, name)
        except Exception:  # noqa: BLE001 - no audio system: only the default is offered
            log.info("Could not list audio devices", exc_info=True)

    def select(self, name: str | None) -> None:
        index = self.findData(name) if name else 0
        if index < 0:
            # A device that isn't connected now is kept as chosen.
            self.addItem(name, name)
            index = self.count() - 1
        self.setCurrentIndex(index)


class LevelMeter(QProgressBar):
    """Shows how loud the microphone hears things while it is on screen."""

    def __init__(self) -> None:
        super().__init__(minimum=0, maximum=100, textVisible=False)
        self.device: str | None = None
        self._stream = None
        self._peak = 0.0
        self._timer = QTimer(self, interval=60, timeout=self._update)

    def listen(self, device: str | None) -> None:
        self.stop()
        self.device = device
        try:
            import sounddevice as sd

            def heard(indata, frames, time, status) -> None:
                self._peak = max(self._peak, float(np.abs(indata).max(initial=0.0)))

            self._stream = sd.InputStream(device=device, channels=1, callback=heard)
            self._stream.start()
            self._timer.start()
        except Exception:  # noqa: BLE001 - the meter just stays empty
            log.info("Could not open the microphone for the level meter", exc_info=True)
            self._stream = None

    def stop(self) -> None:
        self._timer.stop()
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        self.setValue(0)

    def _update(self) -> None:
        # A gentle curve, so speech fills the bar without shouting.
        self.setValue(min(100, int((self._peak**0.5) * 140)))
        self._peak *= 0.6

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt's name
        self.stop()
        super().hideEvent(event)


class VoicePage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.voice = QComboBox()
        self.voice.addItems(VOICES)
        self.play = QPushButton(t("voice.preview"))
        self.play.clicked.connect(self._preview)
        self.input = DeviceChoice("input")
        self.output = DeviceChoice("output")
        self.meter = LevelMeter()
        self.message = QLabel(wordWrap=True)
        row = QHBoxLayout()
        row.addWidget(self.voice, 1)
        row.addWidget(self.play)
        form = QFormLayout(self)
        form.addRow(t("voice.voice"), row)
        form.addRow(t("voice.input"), self.input)
        form.addRow(t("voice.level"), self.meter)
        form.addRow(t("voice.output"), self.output)
        form.addRow("", self.message)
        self.input.currentIndexChanged.connect(self._input_changed)
        self.language = None

    def load(self, settings: config.Settings) -> None:
        self.voice.setCurrentText(settings.voice.voice)
        self.input.select(settings.voice.input_device)
        self.output.select(settings.voice.output_device)
        self.language = settings.assistant_language

    def apply(self, settings: config.Settings) -> None:
        settings.voice.voice = self.voice.currentText()
        settings.voice.input_device = self.input.currentData()
        settings.voice.output_device = self.output.currentData()

    def save_secrets(self) -> None:
        pass

    def _input_changed(self) -> None:
        # Only while the page is on screen: loading the settings must not open the microphone.
        if self.isVisible():
            self.meter.listen(self.input.currentData())

    def showEvent(self, event) -> None:  # noqa: N802
        self.meter.listen(self.input.currentData())
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self.meter.stop()
        super().hideEvent(event)

    def _preview(self) -> None:
        self.play.setEnabled(False)
        voice, output, language = self.voice.currentText(), self.output.currentData(), self.language

        def finished(_=None) -> None:
            self.play.setEnabled(True)

        def failed(error: str) -> None:
            self.message.setText(error)
            finished()

        worker.run(lambda: preview(voice, output, language), finished, failed, owner=self)
