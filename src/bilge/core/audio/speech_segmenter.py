"""Turns a stream of (audio chunk, speech probability) pairs into complete utterances, with pre-roll so the
first syllable is not clipped and hysteresis so short dips don't split words."""

import math
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import chain


@dataclass(frozen=True)
class Configuration:
    chunk_duration: float
    start_threshold: float = 0.6
    end_threshold: float = 0.35
    min_silence: float = 0.7
    pre_roll: float = 0.5
    min_speech: float = 0.3
    max_segment: float = 12

    def __post_init__(self) -> None:
        if not (self.chunk_duration > 0 and self.end_threshold <= self.start_threshold):
            raise ValueError("Invalid segmenter configuration")


class EndReason(StrEnum):
    SILENCE = "silence"
    MAX_LENGTH = "maxLength"
    FLUSHED = "flushed"


@dataclass(frozen=True)
class Segment:
    samples: list[float]
    end_reason: EndReason


def _rounded(value: float) -> int:
    # Swift's rounded() goes half away from zero; Python's round() goes half to even.
    return int(math.copysign(math.floor(abs(value) + 0.5), value))


def _flatten(chunks: Sequence[list[float]]) -> list[float]:
    return list(chain.from_iterable(chunks))


class SpeechSegmenter:
    def __init__(self, configuration: Configuration) -> None:
        self.configuration = configuration
        duration = configuration.chunk_duration
        self._pre_roll_chunks = max(0, _rounded(configuration.pre_roll / duration))
        self._min_silence_chunks = max(1, _rounded(configuration.min_silence / duration))
        self._min_speech_chunks = max(1, _rounded(configuration.min_speech / duration))
        self._max_segment_chunks = max(1, _rounded(configuration.max_segment / duration))
        self._history: deque[list[float]] = deque(maxlen=self._pre_roll_chunks)
        self._current: list[list[float]] = []
        self._speech_chunks = 0
        self._silent_chunks = 0
        self._is_in_speech = False

    @property
    def is_in_speech(self) -> bool:
        return self._is_in_speech

    def process(self, chunk: Sequence[float], probability: float) -> list[Segment]:
        samples = list(chunk)
        if not self._is_in_speech:
            if probability >= self.configuration.start_threshold:
                self._is_in_speech = True
                self._current = [*self._history, samples]
                self._history.clear()
                self._speech_chunks = 1
                self._silent_chunks = 0
            else:
                self._history.append(samples)
            return []

        self._current.append(samples)
        if probability >= self.configuration.end_threshold:
            self._speech_chunks += 1
            self._silent_chunks = 0
        else:
            self._silent_chunks += 1

        if self._silent_chunks >= self._min_silence_chunks:
            segment = self._finish_segment(EndReason.SILENCE)
            return [segment] if segment is not None else []
        if len(self._current) >= self._max_segment_chunks:
            segment = Segment(samples=_flatten(self._current), end_reason=EndReason.MAX_LENGTH)
            self._current = []
            self._speech_chunks = 0
            self._silent_chunks = 0
            return [segment]
        return []

    def flush(self) -> Segment | None:
        if not self._is_in_speech or not self._current:
            return None
        return self._finish_segment(EndReason.FLUSHED)

    def reset(self) -> None:
        self._history.clear()
        self._current = []
        self._speech_chunks = 0
        self._silent_chunks = 0
        self._is_in_speech = False

    def _finish_segment(self, reason: EndReason) -> Segment | None:
        is_long_enough = self._speech_chunks >= self._min_speech_chunks
        samples = _flatten(self._current)
        self._is_in_speech = False
        self._history = deque(self._current, maxlen=self._pre_roll_chunks)
        self._current = []
        self._speech_chunks = 0
        self._silent_chunks = 0
        return Segment(samples=samples, end_reason=reason) if is_long_enough else None
