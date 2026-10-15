"""A few calls on the session D-Bus (media players, notifications, the file manager) through jeepney."""

import contextlib
import threading
from typing import Any, Protocol

from bilge.desktop.process import DesktopError

TIMEOUT_SECONDS = 5


class Bus(Protocol):
    def names(self) -> list[str]: ...

    def call(
        self, name: str, path: str, interface: str, method: str, signature: str | None = None, *args: Any
    ) -> tuple: ...

    def get(self, name: str, path: str, interface: str, prop: str) -> Any: ...


class SessionBus:
    """Connects on first use; a desktop without a session bus (a bare console) fails only the tools that need it.
    The turn and the timers share one connection, and a blocking jeepney connection reads every reply off one
    socket, so calls take turns."""

    def __init__(self) -> None:
        self._connection = None
        self._lock = threading.Lock()

    def _connect(self):
        if self._connection is None:
            try:
                from jeepney.io.blocking import open_dbus_connection

                self._connection = open_dbus_connection(bus="SESSION")
            except (ImportError, OSError, KeyError) as error:
                raise DesktopError(f"No session D-Bus: {error}") from error
        return self._connection

    def _send(self, message) -> tuple:
        from jeepney.wrappers import DBusErrorResponse, unwrap_msg

        with self._lock:
            try:
                # unwrap_msg works on every jeepney version; send_and_get_reply(unwrap=…) is gone in 0.9.
                return unwrap_msg(self._connect().send_and_get_reply(message, timeout=TIMEOUT_SECONDS))
            except DBusErrorResponse as error:
                raise DesktopError(f"D-Bus error: {error.name}") from error
            except (OSError, TimeoutError) as error:
                self._drop()
                raise DesktopError(f"D-Bus call failed: {error}") from error

    def _drop(self) -> None:
        if self._connection is not None:
            with contextlib.suppress(OSError):
                self._connection.close()
            self._connection = None

    def names(self) -> list[str]:
        from jeepney.bus_messages import message_bus

        return list(self._send(message_bus.ListNames())[0])

    def call(
        self, name: str, path: str, interface: str, method: str, signature: str | None = None, *args: Any
    ) -> tuple:
        from jeepney import DBusAddress, new_method_call

        address = DBusAddress(path, bus_name=name, interface=interface)
        return self._send(new_method_call(address, method, signature, args))

    def get(self, name: str, path: str, interface: str, prop: str) -> Any:
        from jeepney import DBusAddress, Properties

        variant = self._send(Properties(DBusAddress(path, bus_name=name, interface=interface)).get(prop))[0]
        # A variant arrives as (signature, value).
        return variant[1]
