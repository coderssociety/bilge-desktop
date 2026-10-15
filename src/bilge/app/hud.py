"""A small window in the corner of the screen: what Bilge heard, its answer, and Yes/No buttons while it waits
for a confirmation. It never takes the keyboard focus away from the app in front."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from bilge.app.texts import t

HIDE_AFTER_MS = 7000
WIDTH = 380
MARGIN = 16
_STYLE = """
QFrame#panel { background: rgba(28, 30, 36, 235); border-radius: 14px; }
QLabel { color: #f2f2f2; }
QLabel#status { color: #9aa4b2; font-size: 11px; }
QLabel#heard { color: #c8d0dc; font-style: italic; }
QPushButton { background: #3b4252; color: white; border: none; border-radius: 8px; padding: 6px 18px; }
QPushButton:hover { background: #4c566a; }
"""


class Hud(QWidget):
    answered = Signal(bool)

    def __init__(self) -> None:
        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(_STYLE)
        self.setFixedWidth(WIDTH)
        self.status = QLabel(objectName="status")
        self.heard = QLabel(objectName="heard", wordWrap=True)
        self.reply = QLabel(wordWrap=True)
        self.yes, self.no = QPushButton(t("hud.yes")), QPushButton(t("hud.no"))
        self.yes.clicked.connect(lambda: self._answer(True))
        self.no.clicked.connect(lambda: self._answer(False))
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.no)
        buttons.addWidget(self.yes)
        self.buttons = QWidget()
        self.buttons.setLayout(buttons)
        # The window itself is see-through; the rounded panel inside it is what shows.
        panel = QFrame(objectName="panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 12, 16, 12)
        for widget in (self.status, self.heard, self.reply, self.buttons):
            layout.addWidget(widget)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)
        self.buttons.hide()
        self._hide_timer = QTimer(self, singleShot=True, interval=HIDE_AFTER_MS, timeout=self.hide)
        self.enabled = True

    def show_status(self, status: str) -> None:
        self.status.setText(t(f"status.{status}") if status else "")
        asking = status == "confirming"
        self.buttons.setVisible(asking)
        if status in ("awake", "transcribing", "thinking", "speaking", "confirming"):
            self._pop()
        elif status == "listening":
            self._hide_timer.start()

    def show_heard(self, text: str) -> None:
        self.heard.setText(f"“{text}”")
        self.reply.clear()
        self._pop()

    def show_reply(self, text: str) -> None:
        self.reply.setText(text)
        self._pop()

    def _answer(self, confirmed: bool) -> None:
        self.buttons.hide()
        self.answered.emit(confirmed)

    def _pop(self) -> None:
        if not self.enabled:
            return
        self._hide_timer.stop()
        self.adjustSize()
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(area.right() - self.width() - MARGIN, area.bottom() - self.height() - MARGIN)
        self.show()
