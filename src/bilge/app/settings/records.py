"""What Bilge remembers (and forgetting it), what it has done, and who made it."""

import json
from collections import deque

from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bilge import config
from bilge.app.texts import t
from bilge.tools.memory_store import MemoryStore

HISTORY_ROWS = 200


class MemoryPage(QWidget):
    def __init__(self, store: MemoryStore | None = None) -> None:
        super().__init__()
        self.store = store or MemoryStore(config.data_dir() / "memory.json")
        self.entries = QListWidget()
        forget, forget_all = QPushButton(t("memory.forget")), QPushButton(t("memory.forget_all"))
        forget.clicked.connect(self._forget)
        forget_all.clicked.connect(self._forget_all)
        buttons = QHBoxLayout()
        buttons.addWidget(forget)
        buttons.addWidget(forget_all)
        buttons.addStretch()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(t("memory.intro")))
        layout.addWidget(self.entries)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self) -> None:
        self.entries.clear()
        for entry in self.store.book.entries:
            item = QListWidgetItem(entry.text)
            item.setData(256, entry.id)
            self.entries.addItem(item)
        if not self.store.book.entries:
            self.entries.addItem(t("memory.empty"))

    def _forget(self) -> None:
        item = self.entries.currentItem()
        if item is not None and item.data(256) is not None:
            self.store.forget(item.data(256))
            self.refresh()

    def _forget_all(self) -> None:
        self.store.forget_all()
        self.refresh()


def recent_actions(limit: int = HISTORY_ROWS) -> list[dict]:
    path = config.data_dir() / "actions.jsonl"
    try:
        with path.open(encoding="utf-8") as file:
            lines = deque(file, maxlen=limit)
    except FileNotFoundError:
        return []
    actions = []
    for line in reversed(lines):
        try:
            actions.append(json.loads(line))
        except ValueError:
            continue
    return actions


class HistoryPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        columns = ("history.time", "history.tool", "history.decision", "history.result")
        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels([t(c) for c in columns])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(t("history.intro")))
        layout.addWidget(self.table)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt's name
        actions = recent_actions()
        self.table.setRowCount(len(actions))
        for row, action in enumerate(actions):
            values = (action.get("time", "").replace("T", " "), action.get("tool", ""), action.get("decision", ""),
                      action.get("result", ""))  # fmt: skip
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        super().showEvent(event)


class AboutPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        from importlib.metadata import PackageNotFoundError, version

        try:
            found = version("bilge")
        except PackageNotFoundError:
            found = "dev"
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(t("about.text", version=found), wordWrap=True))
        link = QLabel(
            '<a href="https://github.com/coderssociety/bilge-desktop">github.com/coderssociety/bilge-desktop</a>'
        )
        link.setOpenExternalLinks(True)
        layout.addWidget(link)
        layout.addStretch()
