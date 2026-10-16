"""Python's garbage collector, run only on the window thread.

Left to itself the collector runs on whichever thread happens to allocate, and when a closed window's widgets are
part of a reference cycle it may destroy them on a background thread (a model list being fetched, a download).
Qt widgets must only be destroyed on the window thread; elsewhere the process crashes. So automatic collection is
turned off while the app runs, and a timer on the window thread collects instead, with the same thresholds.
"""

import gc

from PySide6.QtCore import QObject, QTimer

INTERVAL_MS = 1000


class WindowThreadCollector(QObject):
    def __init__(self, interval_ms: int = INTERVAL_MS) -> None:
        super().__init__()
        self._thresholds = gc.get_threshold()
        self._timer = QTimer(self, interval=interval_ms, timeout=self.collect_if_due)

    def start(self) -> None:
        gc.disable()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        gc.collect()
        gc.enable()

    def collect_if_due(self) -> None:
        """What automatic collection would have done by now: the young generation when it is full, the older
        ones when they have been passed over often enough."""
        young, middle, old = gc.get_count()
        if young > self._thresholds[0]:
            gc.collect(0)
            if middle > self._thresholds[1]:
                gc.collect(1)
                if old > self._thresholds[2]:
                    gc.collect(2)
