"""The user's voice, from a few enrolled recordings: speaker embeddings (L2-normalized) whose mean is compared
with what is heard."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self

MINIMUM_RECORDINGS = 3
# Calibrated on synthetic voices: own 0.82-0.91, the closest other voice at most 0.72.
THRESHOLD_RANGE: tuple[float, float] = (0.55, 0.75)
# Room below the weakest enrolled recording, for a voice that is tired, distant or noisy.
_THRESHOLD_MARGIN = 0.08
_MIN_NORM = 1e-9

Vector = tuple[float, ...]


def _is_valid(embeddings: Sequence[Sequence[float]]) -> bool:
    if len(embeddings) < MINIMUM_RECORDINGS:
        return False
    dimension = len(embeddings[0])
    return dimension > 0 and all(len(embedding) == dimension for embedding in embeddings)


@dataclass(frozen=True)
class VoicePrint:
    embeddings: tuple[Vector, ...]

    def __post_init__(self) -> None:
        if not _is_valid(self.embeddings):
            raise ValueError(f"needs at least {MINIMUM_RECORDINGS} non-empty embeddings of the same length")

    @classmethod
    def create(cls, embeddings: Sequence[Sequence[float]]) -> Self | None:
        if not _is_valid(embeddings):
            return None
        return cls(embeddings=tuple(tuple(float(value) for value in embedding) for embedding in embeddings))

    @property
    def centroid(self) -> Vector:
        """The mean embedding, normalized."""
        return _mean(self.embeddings)

    def score(self, embedding: Sequence[float]) -> float:
        """Cosine similarity with the enrolled voice, from -1 to 1."""
        return cosine(self.centroid, _normalized(embedding))

    @property
    def suggested_threshold(self) -> float:
        """A threshold for this voice: just under how well each recording matches the others (each scored
        against the mean of the rest), kept within THRESHOLD_RANGE."""
        lower, upper = THRESHOLD_RANGE
        leave_one_out = [
            cosine(_mean(self.embeddings[:index] + self.embeddings[index + 1 :]), embedding)
            for index, embedding in enumerate(self.embeddings)
        ]
        weakest = min(leave_one_out, default=upper)
        return min(max(weakest - _THRESHOLD_MARGIN, lower), upper)

    @property
    def consistency(self) -> float:
        """The mean similarity between the recordings: low when they were noisy or not all the same voice."""
        scores = [
            cosine(first, second)
            for index, first in enumerate(self.embeddings)
            for second in self.embeddings[index + 1 :]
        ]
        return sum(scores) / len(scores) if scores else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"embeddings": [list(embedding) for embedding in self.embeddings]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        voice_print = cls.create(data["embeddings"])
        if voice_print is None:
            raise ValueError("invalid voice print embeddings")
        return voice_print


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


def _mean(vectors: Sequence[Sequence[float]]) -> Vector:
    return _normalized([sum(values) for values in zip(*vectors, strict=True)])


def _normalized(vector: Sequence[float]) -> Vector:
    norm = max(math.sqrt(sum(value * value for value in vector)), _MIN_NORM)
    return tuple(value / norm for value in vector)


class Decision(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    # Too little speech for a reliable embedding ("Bilge." alone); the command that follows is checked.
    TOO_SHORT = "tooShort"


MINIMUM_SECONDS = 0.8


def decide(score: float, seconds: float, threshold: float) -> Decision:
    """SpeakerCheck.decide in the Swift code."""
    if seconds < MINIMUM_SECONDS:
        return Decision.TOO_SHORT
    return Decision.ACCEPTED if score >= threshold else Decision.REJECTED
