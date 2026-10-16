"""Asks GitHub about a newer Bilge once a day while the app runs, and remembers what it was told."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from PySide6.QtCore import QObject, QTimer, Signal

from bilge import config, update
from bilge.app import worker

log = logging.getLogger(__name__)

# The first check waits for the start to settle; after that the day is looked at every hour.
FIRST_CHECK_MS = 60_000
CHECK_INTERVAL_MS = 3_600_000


class UpdateWatcher(QObject):
    found = Signal(object)

    def __init__(self, enabled: Callable[[], bool], record: update.CheckRecord | None = None) -> None:
        super().__init__()
        self._enabled = enabled
        self.record = record or update.CheckRecord(config.data_dir() / "update.json")
        self._busy = False
        self._timer = QTimer(self, interval=CHECK_INTERVAL_MS, timeout=self.check_if_due)

    def start(self) -> None:
        remembered = self.record.found(update.current_version())
        if remembered is not None and self._enabled():
            self.found.emit(remembered)
        QTimer.singleShot(FIRST_CHECK_MS, self.check_if_due)
        self._timer.start()

    def check_if_due(self) -> None:
        if self._busy or not self._enabled() or not self.record.is_due(datetime.now(UTC)):
            return
        self._busy = True
        worker.run(lambda: update.newer_release(update.current_version()), self._checked, self._failed, owner=self)

    def _checked(self, release: update.Release | None) -> None:
        self._busy = False
        self.record.record(datetime.now(UTC), release)
        if release is not None:
            log.info("Bilge %s is out: %s", release.version, release.url)
            self.found.emit(release)

    def _failed(self, message: str) -> None:
        # Tried again within the hour.
        self._busy = False
        log.info("Could not check for a newer Bilge: %s", message)
