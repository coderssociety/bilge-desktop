"""Running slow work (listing models, downloads, a test connection) off the window thread, with the result
delivered back on it."""

import logging
import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)


class _Relay(QObject):
    done = Signal(object)
    failed = Signal(str)


# Relays stay referenced until their result is delivered; Qt would otherwise drop the signal with the object.
_pending: set[_Relay] = set()


def run(
    work: Callable[[], Any],
    on_done: Callable[[Any], None],
    on_failed: Callable[[str], None],
    owner: QObject | None = None,
) -> None:
    """`owner` is the window that asked; if it was closed and deleted meanwhile, the result is dropped."""
    import shiboken6

    relay = _Relay()
    _pending.add(relay)

    def finish(handler: Callable[[Any], None], value: Any) -> None:
        _pending.discard(relay)
        if owner is None or shiboken6.isValid(owner):
            handler(value)

    relay.done.connect(lambda value: finish(on_done, value))
    relay.failed.connect(lambda message: finish(on_failed, message))

    def target() -> None:
        try:
            result = work()
        except Exception as error:  # noqa: BLE001 - shown to the user in the window that asked
            log.info("Background work failed", exc_info=True)
            relay.failed.emit(str(error) or type(error).__name__)
            return
        relay.done.emit(result)

    threading.Thread(target=target, name="bilge-work", daemon=True).start()
