"""Where local Whisper runs (processor or graphics card), how fast it is in each place, and whether the large model
is let go while Bilge isn't being talked to."""

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from bilge import assembly, config
from bilge.app import worker
from bilge.app.texts import t
from bilge.core.language import AssistantLanguage


class PlacementPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.language = AssistantLanguage.TURKISH
        self.accelerator = QComboBox()
        for name in config.ACCELERATORS:
            self.accelerator.addItem(t(f"recognition.{name}"), name)
        self.find_gpu = QPushButton(t("recognition.find_gpu"))
        self.find_gpu.clicked.connect(self._find_gpu)
        self.measure = QPushButton(t("recognition.measure"))
        self.measure.clicked.connect(self._measure)
        self.state = QLabel(wordWrap=True)
        self.unload = QComboBox()
        for minutes in config.UNLOAD_MINUTES:
            self.unload.addItem(t("recognition.keep_loaded") if not minutes else t("recognition.unload_after",
                                                                                   minutes=minutes), minutes)  # fmt: skip
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(t("recognition.accelerator")))
        row = QHBoxLayout()
        row.addWidget(self.accelerator, 1)
        row.addWidget(self.find_gpu)
        row.addWidget(self.measure)
        layout.addLayout(row)
        layout.addWidget(self.state)
        layout.addWidget(QLabel(t("recognition.memory")))
        layout.addWidget(self.unload)
        layout.addWidget(QLabel(t("recognition.memory_note"), wordWrap=True))
        self.accelerator.currentIndexChanged.connect(lambda _: self.state.clear())

    def load(self, settings: config.Settings) -> None:
        self.language = settings.assistant_language
        self.accelerator.setCurrentIndex(max(0, self.accelerator.findData(settings.voice.accelerator)))
        self.unload.setCurrentIndex(max(0, self.unload.findData(settings.voice.unload_minutes)))

    def apply(self, settings: config.Settings) -> None:
        settings.voice.accelerator = self.accelerator.currentData()
        settings.voice.unload_minutes = self.unload.currentData()

    def _busy(self, busy: bool, message: str = "") -> None:
        self.find_gpu.setEnabled(not busy)
        self.measure.setEnabled(not busy)
        if message:
            self.state.setText(message)

    def _find_gpu(self) -> None:
        from bilge.voice import placement

        self._busy(True, t("recognition.gpu_checking"))
        # Asked as "the graphics card" even while the processor is chosen: the button is for finding out.
        wanted = "auto" if self.accelerator.currentData() == "auto" else "gpu"

        def look() -> placement.Placement:
            placement.forget()
            return placement.choose(wanted)

        def done(found: placement.Placement) -> None:
            self._busy(False)
            if found.where is placement.Where.PROCESSOR:
                self.state.setText(t("recognition.gpu_none"))
            else:
                self.state.setText(t("recognition.gpu_found", name=found.description))

        worker.run(look, done, lambda error: self._busy(False, error), owner=self)

    def _measure(self) -> None:
        from bilge.voice import speed

        self._busy(True, t("recognition.measuring"))
        language = self.language

        def done(timings: list[speed.Timing]) -> None:
            self._busy(False)
            self.state.setText(" · ".join(_described(timing) for timing in timings))

        worker.run(lambda: speed.measure(assembly.models_dir(), language), done,
                   lambda error: self._busy(False, error), owner=self)  # fmt: skip


def _described(timing) -> str:
    where = t("recognition.processor") if timing.where == "processor" else timing.where
    if timing.seconds is not None:
        return t("recognition.took", where=where, seconds=f"{timing.seconds:.2f}")
    if timing.problem == "missing":
        return t("recognition.not_downloaded", where=where)
    return t("recognition.measure_failed", where=where, error=timing.problem)
