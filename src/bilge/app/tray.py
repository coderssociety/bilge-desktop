"""The notification-area icon: its colour shows what Bilge is doing, its menu turns listening on and off and opens
the settings."""

from importlib import resources

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from bilge.app import texts
from bilge.app.texts import t
from bilge.update import Release

# The dot drawn on the owl for each state.
_COLOURS = {
    "listening": "#4caf50", "awake": "#2196f3", "transcribing": "#2196f3", "thinking": "#ff9800",
    "speaking": "#9c27b0", "confirming": "#ffc107", "starting": "#9e9e9e", "failed": "#f44336", "off": "#616161",
}  # fmt: skip


def app_icon() -> QIcon:
    return QIcon(str(resources.files("bilge.app") / "resources" / "bilge.png"))


def status_icon(status: str) -> QIcon:
    base = QPixmap(str(resources.files("bilge.app") / "resources" / "bilge-64.png"))
    if base.isNull():
        return app_icon()
    painter = QPainter(base)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(_COLOURS.get(status, "#616161")))
    size = base.width() // 3
    painter.drawEllipse(base.width() - size - 2, base.height() - size - 2, size, size)
    painter.end()
    return QIcon(base)


class Tray(QObject):
    listen_toggled = Signal(bool)
    settings_requested = Signal()
    setup_requested = Signal()
    quit_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.icon = QSystemTrayIcon(status_icon("off"))
        menu = QMenu()
        self.state = QAction(t("status.off"), menu, enabled=False)
        self.listen = QAction(t("menu.listen"), menu, checkable=True)
        self.listen.toggled.connect(self.listen_toggled.emit)
        menu.addAction(self.state)
        menu.addSeparator()
        menu.addAction(self.listen)
        menu.addAction(t("menu.settings"), self.settings_requested.emit)
        menu.addAction(t("menu.setup"), self.setup_requested.emit)
        self.update = QAction(menu, visible=False)
        self.update.triggered.connect(self._open_release)
        menu.addAction(self.update)
        self._release: Release | None = None
        menu.addSeparator()
        menu.addAction(t("menu.quit"), self.quit_requested.emit)
        self.menu = menu
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._activated)
        self.show_status("off")

    def show(self) -> None:
        self.icon.show()

    def show_status(self, status: str) -> None:
        label = texts.status(status)
        self.icon.setIcon(status_icon(status))
        self.icon.setToolTip(f"Bilge — {label}")
        self.state.setText(label)
        on = status not in ("off", "failed")
        if self.listen.isChecked() != on:
            self.listen.blockSignals(True)
            self.listen.setChecked(on)
            self.listen.blockSignals(False)

    def notify(self, message: str) -> None:
        self.icon.showMessage("Bilge", message, app_icon())

    def show_update(self, release: Release, announce: bool) -> None:
        """A newer Bilge is out: the menu offers its download page; `announce` also says so, once per version."""
        self._release = release
        self.update.setText(t("menu.update", version=release.version))
        self.update.setVisible(True)
        if announce:
            self.notify(t("update.notice", version=release.version))

    def _open_release(self) -> None:
        if self._release is not None:
            QDesktopServices.openUrl(QUrl(self._release.url))

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.settings_requested.emit()
