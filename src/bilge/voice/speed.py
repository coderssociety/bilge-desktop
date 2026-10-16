"""Timing Whisper on this computer, on the processor and on the graphics card, for the settings' measure button: the
numbers show which to choose, and a card that is no faster than the processor shows itself too."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soxr

from bilge.core.language import AssistantLanguage
from bilge.voice import models, placement
from bilge.voice.recognizers import SAMPLE_RATE, Recognizer, WhisperRecognizer

log = logging.getLogger(__name__)

ROUNDS = 2
# A request of the usual length, said in Bilge's own voice.
SENTENCES = {
    AssistantLanguage.TURKISH: "Bilge, yarın sabah saat dokuzda toplantı ekle ve hava durumunu söyle.",
    AssistantLanguage.ENGLISH: "Bilge, add a meeting tomorrow at nine and tell me the weather.",
}


@dataclass(frozen=True)
class Timing:
    # "processor", or the graphics card's name.
    where: str
    # The time for one request, the faster of the rounds after a first warm-up run; None when it couldn't be timed.
    seconds: float | None
    # Why it couldn't: "missing" (the model isn't downloaded), or the error.
    problem: str = ""


def spoken_sample(models_dir: Path, language: AssistantLanguage) -> np.ndarray:
    from bilge.voice.supertonic import Supertonic

    voice = Supertonic(models_dir / models.SUPERTONIC.name)
    audio = voice.synthesize(SENTENCES[language], language, "M1", seed=1)
    return soxr.resample(audio, voice.sample_rate, SAMPLE_RATE).astype(np.float32)


def measure(models_dir: Path, language: AssistantLanguage, sample: np.ndarray | None = None) -> list[Timing]:
    """Each place Whisper could run here; loads each model in turn, so it takes some seconds."""
    if sample is None:
        # Before setup has downloaded the voice there is nothing to say the sample with, nor anything to time.
        if not (models_dir / models.SUPERTONIC.name).is_dir():
            return [Timing("processor", None, "missing")]
        sample = spoken_sample(models_dir, language)
    turbo = models_dir / models.WHISPER_TURBO.name
    timings = [_timed("processor", turbo.is_dir(), lambda: WhisperRecognizer(str(turbo), language, "cpu"), sample)]
    card = placement.choose("gpu")
    if card.where is placement.Where.CUDA:
        timings.append(_timed(card.description, turbo.is_dir(),
                              lambda: WhisperRecognizer(str(turbo), language, "cuda"), sample))  # fmt: skip
    elif card.where is placement.Where.VULKAN:
        from bilge.voice.whisper_cpp import WhisperServer, server_program

        model = models_dir / models.WHISPER_TURBO_GGML.name / models.WHISPER_TURBO_GGML_FILE

        def server() -> Recognizer:
            started = WhisperServer(server_program(), model, language, card.gpu)
            started.start()
            return started

        timings.append(_timed(card.description, model.is_file(), server, sample))
    return timings


def _timed(where: str, available: bool, load: Callable[[], Recognizer], sample: np.ndarray) -> Timing:
    if not available:
        return Timing(where, None, "missing")
    recognizer = None
    try:
        recognizer = load()
        # The first run includes one-off work (allocations, compiling the card's shaders).
        recognizer.transcribe(sample)
        times = []
        for _ in range(ROUNDS):
            started = time.perf_counter()
            recognizer.transcribe(sample)
            times.append(time.perf_counter() - started)
        return Timing(where, min(times))
    except Exception as error:  # noqa: BLE001 - shown next to the place it happened
        log.info("Could not time Whisper on %s", where, exc_info=True)
        return Timing(where, None, str(error) or type(error).__name__)
    finally:
        close = getattr(recognizer, "close", None)
        if close is not None:
            close()
