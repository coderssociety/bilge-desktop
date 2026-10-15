"""Re-frames arbitrary-length audio buffers into fixed-size chunks (the VAD model needs exactly 4096 samples)."""

from collections.abc import Sequence


class SampleChunker:
    def __init__(self, chunk_size: int) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self.chunk_size = chunk_size
        self._pending: list[float] = []

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def append(self, samples: Sequence[float]) -> list[list[float]]:
        self._pending.extend(samples)
        size = self.chunk_size
        full = len(self._pending) - len(self._pending) % size
        chunks = [self._pending[start : start + size] for start in range(0, full, size)]
        if full:
            del self._pending[:full]
        return chunks

    def reset(self) -> None:
        self._pending.clear()
