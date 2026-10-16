"""`bilge-app`: the tray app. One copy runs per user; starting it again opens the running one's settings."""

import getpass
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from bilge import config
from bilge.app import texts
from bilge.app.shell import Shell
from bilge.app.tray import app_icon

# The id the installer gives Bilge's Start menu shortcut, so Windows shows notifications under Bilge's name.
WINDOWS_APP_ID = "CodersSociety.Bilge"
LOG_BYTES = 1_000_000
# `Bilge --listen` asks the running Bilge to listen, as its shortcut does; for a shortcut set in the desktop's own
# keyboard settings where Bilge cannot have one of its own (some Wayland desktops).
LISTEN_ARGUMENT = "--listen"
LISTEN, SHOW = b"listen", b"show"
KNOCK_MS = 300


def _instance_name() -> str:
    return f"bilge-{getpass.getuser()}"


def _already_running(message: bytes) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(_instance_name())
    if not socket.waitForConnected(300):
        return False
    socket.write(message)
    socket.waitForBytesWritten(300)
    socket.disconnectFromServer()
    return True


def _listen_for_others(shell: Shell) -> QLocalServer:
    QLocalServer.removeServer(_instance_name())
    server = QLocalServer()
    # Only this user may knock.
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)

    def knocked() -> None:
        connection = server.nextPendingConnection()
        if connection is None:
            return
        if not connection.bytesAvailable():
            connection.waitForReadyRead(KNOCK_MS)
        message = bytes(connection.readAll())
        connection.disconnectFromServer()
        connection.deleteLater()
        if message == LISTEN:
            shell.shortcut_pressed()
        else:
            shell.bring_forward()

    server.newConnection.connect(knocked)
    if not server.listen(_instance_name()):
        logging.getLogger("bilge").warning("A second start won't find this one: %s", server.errorString())
    return server


def _log_to_file() -> None:
    folder = config.data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / "bilge.log", maxBytes=LOG_BYTES, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def _log_uncaught() -> None:
    """A windowed app has no console; what would have been printed goes to the log."""

    def record(kind, error, traceback) -> None:
        logging.getLogger("bilge").critical("Uncaught error", exc_info=(kind, error, traceback))

    sys.excepthook = record
    threading.excepthook = lambda hook: record(hook.exc_type, hook.exc_value, hook.exc_traceback)


def _settings_or_defaults() -> config.Settings:
    try:
        return config.load_settings()
    except RuntimeError as error:
        logging.getLogger("bilge").error("Unreadable settings: %s", error)
        QMessageBox.warning(None, "Bilge", f"{error}\n\nBilge starts with its default settings.")
        return config.Settings()


def _windows_identity() -> None:
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
        # The installer waits on this name to close Bilge before replacing its files.
        ctypes.windll.kernel32.CreateMutexW(None, False, "BilgeAppMutex")


def main(argv: list[str] | None = None) -> int:
    _log_to_file()
    _log_uncaught()
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Bilge")
    app.setWindowIcon(app_icon())
    # Closing the settings leaves Bilge running in the tray.
    app.setQuitOnLastWindowClosed(False)
    arguments = argv if argv is not None else sys.argv
    if _already_running(LISTEN if LISTEN_ARGUMENT in arguments[1:] else SHOW):
        return 0
    _windows_identity()
    texts.use(_settings_or_defaults().assistant_language)
    shell = Shell(app)
    app.aboutToQuit.connect(shell.shut_down)
    server = _listen_for_others(shell)
    shell.begin()
    code = app.exec()
    server.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
