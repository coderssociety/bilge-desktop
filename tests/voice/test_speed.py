import numpy as np

from bilge.voice import placement, speed
from bilge.voice.gpu import Gpu, Kind


class Fake:
    def __init__(self, *_, **__):
        self.calls = 0

    def transcribe(self, samples):
        self.calls += 1
        return "tamam"


def test_times_the_processor_and_reports_a_missing_card_model(monkeypatch, tmp_path):
    (tmp_path / "whisper-large-v3-turbo").mkdir()
    monkeypatch.setattr(speed, "WhisperRecognizer", Fake)
    monkeypatch.setattr(
        placement,
        "choose",
        lambda _: placement.Placement(placement.Where.VULKAN, Gpu(1, "AMD Radeon RX 6600", Kind.DISCRETE, (1, 3))),
    )
    timings = speed.measure(tmp_path, None, sample=np.zeros(16_000, dtype=np.float32))
    assert [t.where for t in timings] == ["processor", "AMD Radeon RX 6600"]
    assert timings[0].seconds is not None and timings[0].seconds >= 0
    assert (timings[1].seconds, timings[1].problem) == (None, "missing")


def test_a_failure_is_shown_for_its_place(monkeypatch, tmp_path):
    (tmp_path / "whisper-large-v3-turbo").mkdir()

    class Broken(Fake):
        def transcribe(self, samples):
            raise RuntimeError("cuBLAS failed")

    monkeypatch.setattr(speed, "WhisperRecognizer", Broken)
    monkeypatch.setattr(placement, "choose", lambda _: placement.Placement(placement.Where.PROCESSOR))
    [timing] = speed.measure(tmp_path, None, sample=np.zeros(16_000, dtype=np.float32))
    assert timing.seconds is None and "cuBLAS" in timing.problem


def test_nothing_is_timed_before_the_models_are_downloaded(tmp_path):
    assert speed.measure(tmp_path, None) == [speed.Timing("processor", None, "missing")]
