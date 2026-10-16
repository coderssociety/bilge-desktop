"""A Wayland session: the GlobalShortcuts desktop portal (KDE Plasma 5.27+, GNOME 48+). Bilge suggests the
combination; the desktop asks the user, may let them pick another, and reports each press back over D-Bus.

Every portal request answers later with a Response signal on a path built from a token Bilge chooses, so the signal
is subscribed to before the request is sent.
"""

import contextlib
import logging
import secrets
import threading
from collections.abc import Callable

from bilge.desktop.hotkey import HotkeyError
from bilge.desktop.hotkey.shortcut import Shortcut

log = logging.getLogger(__name__)

PORTAL_NAME = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SHORTCUTS = "org.freedesktop.portal.GlobalShortcuts"
APP_ID = "io.github.coderssociety.Bilge"
SHORTCUT_ID = "listen"
# The desktop may show the user a dialog before it answers.
ANSWER_SECONDS = 300
CALL_SECONDS = 10
POLL_SECONDS = 0.5
_CANCELLED = 1


class PortalHotkey:
    def __init__(
        self,
        shortcut: Shortcut,
        pressed: Callable[[], None],
        description: str = "Bilge",
        lost: Callable[[], None] = lambda: None,
    ):
        """Blocks until the desktop has answered, which may wait on the user; call it off the window thread."""
        try:
            from jeepney.io.blocking import open_dbus_connection
        except ImportError as error:
            raise HotkeyError("unsupported", "jeepney is missing") from error
        self.shortcut = shortcut
        self._pressed = pressed
        self._lost = lost
        self._stopping = threading.Event()
        try:
            self._connection = open_dbus_connection(bus="SESSION")
        except (OSError, KeyError) as error:
            raise HotkeyError("unsupported", f"no session D-Bus: {error}") from error
        try:
            self._register_app()
            self._session = self._create_session()
            self._bind(description)
        except BaseException:
            self._connection.close()
            raise
        self._thread = threading.Thread(target=self._listen, name="bilge-hotkey", daemon=True)
        self._thread.start()

    def _call(self, path: str, interface: str, method: str, signature: str, *body):
        from jeepney import DBusAddress, new_method_call
        from jeepney.wrappers import DBusErrorResponse, unwrap_msg

        address = DBusAddress(path, bus_name=PORTAL_NAME, interface=interface)
        try:
            return unwrap_msg(self._connection.send_and_get_reply(new_method_call(address, method, signature, body),
                                                                   timeout=CALL_SECONDS))  # fmt: skip
        except DBusErrorResponse as error:
            raise HotkeyError("unsupported", f"{method}: {error.name}") from error
        except (OSError, TimeoutError) as error:
            raise HotkeyError("unsupported", f"{method}: {error}") from error

    def _register_app(self) -> None:
        """A program outside Flatpak or Snap says who it is, so the desktop can keep its shortcut; portals older
        than 1.19 have no registry and work it out themselves."""
        try:
            self._call(PORTAL_PATH, "org.freedesktop.host.portal.Registry", "Register", "sa{sv}", APP_ID, {})
        except HotkeyError as error:
            log.info("The portal registry did not take Bilge's id (%s)", error)

    def _request(self, method: str, signature: str, *body, options: dict) -> dict:
        """Sends a portal request and waits for its Response."""
        from jeepney import MatchRule
        from jeepney.bus_messages import message_bus

        token = f"bilge{secrets.token_hex(6)}"
        sender = self._connection.unique_name.lstrip(":").replace(".", "_")
        rule = MatchRule(type="signal", interface="org.freedesktop.portal.Request", member="Response",
                         path=f"{PORTAL_PATH}/request/{sender}/{token}")  # fmt: skip
        self._connection.send_and_get_reply(message_bus.AddMatch(rule), timeout=CALL_SECONDS)
        with self._connection.filter(rule) as queue:
            self._call(PORTAL_PATH, SHORTCUTS, method, signature, *body, {**options, "handle_token": ("s", token)})
            try:
                answer = self._connection.recv_until_filtered(queue, timeout=ANSWER_SECONDS)
            except TimeoutError as error:
                raise HotkeyError("unsupported", f"{method}: no answer") from error
        code, results = answer.body
        if code == _CANCELLED:
            raise HotkeyError("declined", method)
        if code != 0:
            raise HotkeyError("unsupported", f"{method} answered {code}")
        return results

    def _create_session(self) -> str:
        results = self._request("CreateSession", "a{sv}",
                                options={"session_handle_token": ("s", f"bilge{secrets.token_hex(6)}")})  # fmt: skip
        try:
            return str(results["session_handle"][1])
        except (KeyError, IndexError, TypeError) as error:
            raise HotkeyError("unsupported", "CreateSession gave no session") from error

    def _bind(self, description: str) -> None:
        wanted = [(SHORTCUT_ID, {"description": ("s", description),
                                 "preferred_trigger": ("s", self.shortcut.portal_trigger)})]  # fmt: skip
        results = self._request("BindShortcuts", "oa(sa{sv})sa{sv}", self._session, wanted, "", options={})
        bound = {shortcut_id: properties for shortcut_id, properties in results.get("shortcuts", ("", []))[1]}
        if SHORTCUT_ID not in bound:
            raise HotkeyError("declined", "BindShortcuts")
        trigger = bound[SHORTCUT_ID].get("trigger_description", ("s", ""))[1]
        log.info("The desktop bound Bilge's shortcut to %s", trigger or "a key the user chooses")

    def _listen(self) -> None:
        from jeepney import MatchRule
        from jeepney.bus_messages import message_bus

        rule = MatchRule(type="signal", interface=SHORTCUTS, member="Activated", path=PORTAL_PATH)
        try:
            self._connection.send_and_get_reply(message_bus.AddMatch(rule), timeout=CALL_SECONDS)
            with self._connection.filter(rule, bufsize=16) as queue:
                while not self._stopping.is_set():
                    try:
                        signal = self._connection.recv_until_filtered(queue, timeout=POLL_SECONDS)
                    except TimeoutError:
                        continue
                    session, shortcut_id = signal.body[0], signal.body[1]
                    if session == self._session and shortcut_id == SHORTCUT_ID:
                        try:
                            self._pressed()
                        except Exception:
                            log.exception("The shortcut's action failed")
        except Exception:  # noqa: BLE001 - whatever ends the loop ends the shortcut, which must be reported
            if not self._stopping.is_set():
                log.warning("Lost the connection to the desktop portal; the shortcut no longer works", exc_info=True)
                self._lost()

    def stop(self) -> None:
        self._stopping.set()
        self._thread.join(timeout=2)
        with contextlib.suppress(HotkeyError):
            self._call(self._session, "org.freedesktop.portal.Session", "Close", "")
        self._connection.close()
