"""Letting the large Whisper model go while Bilge isn't being talked to, and loading it again when it is.

The model takes 1-2 GB of memory (or of the graphics card's). The small wake word model stays loaded, so Bilge still
hears its name; the large one is loaded again as soon as it does, which delays that one answer by the loading time.
"""

import logging
import threading
import time
from collections.abc import Callable

import numpy as np

from bilge.voice.recognizers import Recognizer

log = logging.getLogger(__name__)

CHECK_SECONDS = 30.0


class IdleUnloadingRecognizer:
    def __init__(
        self,
        load: Callable[[], Recognizer],
        idle_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        check_seconds: float = CHECK_SECONDS,
    ):
        """Loads at once, so a model that can't start is reported when Bilge starts rather than at the first
        request."""
        self._load = load
        self._idle_seconds = idle_seconds
        self._clock = clock
        # Held while loading, transcribing or unloading: a model is never let go in the middle of a recording.
        self._lock = threading.Lock()
        self._recognizer: Recognizer | None = load()
        self._last_used = clock()
        self._closed = threading.Event()
        self._watcher = threading.Thread(target=self._watch, args=(check_seconds,), name="bilge-idle", daemon=True)
        self._watcher.start()

    @property
    def is_loaded(self) -> bool:
        return self._recognizer is not None

    def warm(self) -> None:
        """Bilge was just called: start loading now, while the request is still being said."""
        threading.Thread(target=self._ensure_loaded, name="bilge-warm", daemon=True).start()

    def _ensure_loaded(self) -> Recognizer:
        with self._lock:
            return self._loaded()

    def _loaded(self) -> Recognizer:
        if self._recognizer is None:
            started = self._clock()
            self._recognizer = self._load()
            log.info("Whisper loaded again in %.1f s", self._clock() - started)
        self._last_used = self._clock()
        return self._recognizer

    def transcribe(self, samples: np.ndarray) -> str:
        with self._lock:
            text = self._loaded().transcribe(samples)
            self._last_used = self._clock()
            return text

    def unload_if_idle(self) -> None:
        with self._lock:
            if self._recognizer is not None and self._clock() - self._last_used >= self._idle_seconds:
                log.info("Whisper unused for %.0f minutes; letting it go", self._idle_seconds / 60)
                self._release()

    def _release(self) -> None:
        recognizer, self._recognizer = self._recognizer, None
        close = getattr(recognizer, "close", None)
        if close is not None:
            close()

    def _watch(self, check_seconds: float) -> None:
        while not self._closed.wait(check_seconds):
            try:
                self.unload_if_idle()
            except Exception:
                log.exception("Could not let Whisper go")

    def close(self) -> None:
        self._closed.set()
        with self._lock:
            self._release()
