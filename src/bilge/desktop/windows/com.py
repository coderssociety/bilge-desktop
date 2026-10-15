"""Calling COM servers (Excel, Outlook, Core Audio) from the turn threads.

COM is set up per thread, and every turn has its own. Objects must be released before COM is closed on that thread,
and an exception's traceback would keep them alive past that point, so errors are raised again only after the
objects are gone, without their tracebacks.
"""

import gc
from collections.abc import Callable
from typing import Any

# COM was already set up on this thread in another mode (WinRT does that): use it as it is and leave it alone.
_RPC_E_CHANGED_MODE = -2147417850


class ComFailure(Exception):
    pass


def call[T](acquire: Callable[[], Any], action: Callable[[Any], T], keep: tuple[type[Exception], ...] = ()) -> T:
    """`acquire` returns the COM object; `action` uses it. Errors of the `keep` types come back as they are; any
    other failure, from comtypes or the program, becomes a ComFailure naming it."""
    import comtypes

    try:
        comtypes.CoInitialize()
        started = True
    except OSError as error:
        if getattr(error, "winerror", None) != _RPC_E_CHANGED_MODE:
            raise ComFailure(f"{type(error).__name__}: {error}") from None
        started = False
    raised: Exception | None = None
    result: Any = None
    try:
        target = acquire()
        try:
            result = action(target)
        finally:
            del target
    except Exception as error:  # noqa: BLE001 - re-raised below, once COM objects are released
        raised = error if isinstance(error, keep) else ComFailure(f"{type(error).__name__}: {error}")
        raised.__traceback__ = raised.__context__ = raised.__cause__ = None
        del error
    finally:
        gc.collect()
        if started:
            comtypes.CoUninitialize()
    if raised is not None:
        raise raised
    return result
