"""Runs the voice assistant behind the windows: starts it on a background thread (loading models takes seconds), and
turns its events into Qt signals, which arrive on the window thread."""

import logging
import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from bilge import assembly, config

log = logging.getLogger(__name__)

STARTING, FAILED, OFF = "starting", "failed", "off"


def _shut(assistant, front_end) -> None:
    for part in (front_end, assistant):
        if part is not None:
            try:
                part.stop()
            except Exception:  # noqa: BLE001 - shutting down what half-started; the start's own error is the one to show
                log.exception("Could not stop a part that half-started")


class AssistantController(QObject):
    status_changed = Signal(str)
    heard = Signal(str)
    replied = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        build: Callable = assembly.build_voice_assistant,
        load: Callable[[], config.Settings] = config.load_settings,
        prepare: Callable[[config.Settings], None] | None = None,
    ):
        super().__init__()
        self._build = build
        self._load = load
        self._prepare = prepare or (
            lambda settings, cancelled: assembly.download_missing(assembly.voice_models(settings), cancelled=cancelled)
        )
        self._lock = threading.Lock()
        self._assistant = None
        self._front_end = None
        self._starting = False
        # Bumped by every start and stop, so a start that finishes after a stop knows it is no longer wanted.
        self._generation = 0
        # The shortcut was pressed while listening was off.
        self._wake_when_started = False
        self.status = OFF

    @property
    def is_on(self) -> bool:
        return self._assistant is not None or self._starting

    def start(self) -> None:
        with self._lock:
            if self.is_on:
                return
            self._starting = True
            self._generation += 1
            generation = self._generation
        self._set_status(STARTING)
        threading.Thread(target=self._start, args=(generation,), name="bilge-start", daemon=True).start()

    def _start(self, generation: int) -> None:
        assistant = front_end = None
        try:
            settings = self._load()
            self._prepare(settings, lambda: generation != self._generation)
            assistant, front_end = self._build(settings, lambda kind, text: self._on_event(kind, text, generation))
            # The microphone first: if it can't open, nothing else has started yet.
            front_end.start()
            assistant.start()
        except Exception as error:  # noqa: BLE001 - whatever stops the start is shown to the user
            log.exception("Bilge could not start")
            _shut(assistant, front_end)
            with self._lock:
                if generation != self._generation:
                    return
                self._starting = False
                self._wake_when_started = False
            self._set_status(FAILED)
            self.failed.emit(str(error) or type(error).__name__)
            return
        with self._lock:
            wanted = generation == self._generation
            if wanted:
                self._assistant, self._front_end = assistant, front_end
                # Only the current start may clear the flag; an older one finishing late must not.
                self._starting = False
                wake, self._wake_when_started = self._wake_when_started, False
        if not wanted:
            _shut(assistant, front_end)
            return
        log.info("Bilge is listening (%s, %s)", settings.model.provider, settings.voice.recognizer)
        if wake:
            assistant.shortcut_pressed()

    def shortcut_pressed(self) -> None:
        """The listening shortcut. With listening off it switches it on, and Bilge listens once it has started."""
        with self._lock:
            assistant = self._assistant
            if assistant is None:
                self._wake_when_started = True
        if assistant is not None:
            # Playing the wake tone may wait on the sound device; the window thread must not.
            threading.Thread(target=assistant.shortcut_pressed, name="bilge-shortcut", daemon=True).start()
            return
        self.start()

    def stop(self) -> None:
        with self._lock:
            assistant, front_end = self._assistant, self._front_end
            self._assistant = self._front_end = None
            self._generation += 1
            self._starting = False
            self._wake_when_started = False
        if front_end is not None:
            front_end.stop()
        if assistant is not None:
            assistant.stop()
        self._set_status(OFF)

    def restart(self) -> None:
        """Starts again with fresh settings, but only if it was on: saving settings doesn't switch listening on."""
        if self.is_on:
            self.stop()
            self.start()

    def answer(self, confirmed: bool) -> None:
        assistant = self._assistant
        if assistant is not None:
            assistant.answer(confirmed)

    def _on_event(self, kind: str, text: str, generation: int) -> None:
        # An assistant replaced by a restart may still report as it shuts down.
        if generation != self._generation:
            return
        if kind == "status":
            self._set_status(text)
        elif kind == "heard":
            self.heard.emit(text)
        elif kind == "reply":
            self.replied.emit(text)
        elif kind == "error":
            self.failed.emit(text)

    def _set_status(self, status: str) -> None:
        self.status = status
        self.status_changed.emit(status)
