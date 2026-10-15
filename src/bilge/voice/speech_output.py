"""Speaks text sentence by sentence: the next sentence is synthesized while the current one plays, so the
first words start quickly however long the reply is."""

import logging
import queue
import threading
import time

import numpy as np
import soxr

from bilge.core.language import AssistantLanguage
from bilge.core.speech import sentence_splitter, spoken_text
from bilge.voice.audio_io import AudioDevice
from bilge.voice.supertonic import Supertonic

log = logging.getLogger(__name__)
_POLL = 0.02


class SpeechOutput:
    def __init__(self, tts: Supertonic, device: AudioDevice, language: AssistantLanguage, voice: str):
        self.tts = tts
        self.device = device
        self.language = language
        self.voice = voice
        self._stopped = threading.Event()
        self._lock = threading.Lock()

    def stop(self) -> None:
        self._stopped.set()
        self.device.clear()

    def speak(self, text: str, on_sentence=None) -> bool:
        """Blocks until everything is said; False when it was stopped first."""
        with self._lock:
            self._stopped.clear()
            sentences = sentence_splitter.split(spoken_text.normalize(text, self.language))
            ready: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=2)
            producer = threading.Thread(target=self._synthesize, args=(sentences, ready), daemon=True)
            producer.start()
            index = 0
            while (audio := ready.get()) is not None:
                if self._stopped.is_set():
                    break
                if on_sentence:
                    on_sentence(sentences[index])
                index += 1
                self.device.play(audio)
                while self.device.is_playing and not self._stopped.is_set():
                    time.sleep(_POLL)
            producer.join(timeout=5)
            return not self._stopped.is_set()

    def play(self, samples: np.ndarray) -> None:
        """Short sounds (the wake tone) at the device rate, without waiting."""
        self.device.play(samples)

    def _synthesize(self, sentences: list[str], ready: queue.Queue) -> None:
        try:
            for sentence in sentences:
                if self._stopped.is_set():
                    break
                audio = self.tts.synthesize(sentence, self.language, self.voice)
                if len(audio):
                    ready.put(soxr.resample(audio, self.tts.sample_rate, self.device.sample_rate).astype(np.float32))
        except Exception:
            log.exception("Speech synthesis failed")
        finally:
            ready.put(None)


def tone(sample_rate: int, frequencies: tuple[float, ...], length: float = 0.09, volume: float = 0.18) -> np.ndarray:
    """A soft tone or a short sequence of tones, for waking up and giving up."""
    parts = []
    for frequency in frequencies:
        t = np.arange(int(length * sample_rate)) / sample_rate
        envelope = np.sin(np.pi * t / length) ** 2
        parts.append((np.sin(2 * np.pi * frequency * t) * envelope * volume).astype(np.float32))
    return np.concatenate(parts)
