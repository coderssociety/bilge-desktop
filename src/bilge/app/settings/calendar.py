"""Connecting a calendar from the window, as `bilge calendar` does: the secret goes to the key store only once the
calendar has answered."""

import sys
from datetime import datetime, timedelta

from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QLineEdit, QPushButton, QWidget

from bilge import assembly, calendars, config
from bilge.app import worker
from bilge.app.texts import t


class CalendarPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.kind = QComboBox()
        kinds = [("", "calendar.none"), ("caldav", "calendar.caldav"), ("ics", "calendar.ics")]
        if sys.platform == "win32":
            kinds.append(("outlook", "calendar.outlook"))
        for value, key in kinds:
            self.kind.addItem(t(key), value)
        self.url = QLineEdit(placeholderText="https://")
        self.user = QLineEdit()
        self.secret = QLineEdit(echoMode=QLineEdit.EchoMode.Password)
        self.name = QLineEdit()
        self.test = QPushButton(t("calendar.test"))
        self.test.clicked.connect(self._test)
        self.message = QLabel(wordWrap=True)
        form = QFormLayout(self)
        form.addRow(t("calendar.kind"), self.kind)
        self.rows = {
            "url": (QLabel(t("calendar.url")), self.url),
            "user": (QLabel(t("calendar.user")), self.user),
            "secret": (QLabel(t("calendar.password")), self.secret),
            "name": (QLabel(t("calendar.name")), self.name),
        }
        for label, field in self.rows.values():
            form.addRow(label, field)
        form.addRow("", self.test)
        form.addRow("", self.message)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        # A secret that has passed the test, waiting for Save; changing any field means testing again.
        self._verified: tuple[str, str] | None = None
        for field in (self.url, self.user, self.secret, self.name):
            field.textEdited.connect(self._forget_test)

    def _forget_test(self) -> None:
        self._verified = None

    def load(self, settings: config.Settings) -> None:
        calendar = settings.calendar
        self.kind.setCurrentIndex(max(0, self.kind.findData(calendar.kind)))
        self._verified = None
        self.url.setText(calendar.url)
        self.user.setText(calendar.username)
        self.name.setText(calendar.name)
        self._kind_changed()

    def _chosen(self) -> config.CalendarSettings:
        kind = self.kind.currentData()
        if kind == "caldav":
            return config.CalendarSettings("caldav", self.url.text().strip(), self.user.text().strip(),
                                           self.name.text().strip())  # fmt: skip
        return config.CalendarSettings(kind)

    def apply(self, settings: config.Settings) -> None:
        settings.calendar = self._chosen()

    def save_secrets(self) -> None:
        if self._verified is not None:
            config.store_api_key(*self._verified)
            self._verified = None
            self.secret.clear()

    def _kind_changed(self) -> None:
        kind = self.kind.currentData()
        visible = {"caldav": ("url", "user", "secret", "name"), "ics": ("secret",)}.get(kind, ())
        for key, (label, field) in self.rows.items():
            label.setVisible(key in visible)
            field.setVisible(key in visible)
        self.rows["secret"][0].setText(t("calendar.url") if kind == "ics" else t("calendar.password"))
        self.test.setVisible(bool(kind))
        self.message.clear()

    @staticmethod
    def _source(
        chosen: config.CalendarSettings, secret: str
    ) -> tuple[calendars.CalendarSource | None, tuple[str, str] | None]:
        if chosen.kind == "caldav":
            password = secret or config.api_key(assembly.CALDAV_SECRET) or ""
            source = calendars.CalDAVSource(chosen.url, chosen.username, password, chosen.name)
            return source, ((assembly.CALDAV_SECRET, secret) if secret else None)
        if chosen.kind == "ics" and secret:
            if not secret.lower().startswith("https://"):
                raise calendars.CalendarError("https://")
            return calendars.ICSSource(secret), (assembly.ICS_SECRET, secret)
        return assembly.calendar_source(chosen), None

    def _test(self) -> None:
        self.test.setEnabled(False)
        # Read on the window thread; the check itself runs on another.
        chosen, typed = self._chosen(), self.secret.text().strip()

        def check():
            source, secret = self._source(chosen, typed)
            if source is None:
                raise calendars.CalendarError(t("calendar.none"))
            start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
            return len(source.events(start, start + timedelta(days=7))), secret

        def done(result) -> None:
            count, self._verified = result
            self.message.setText(t("calendar.ok", count=count))
            self.test.setEnabled(True)

        def failed(error: str) -> None:
            self.message.setText(t("calendar.failed", error=error))
            self.test.setEnabled(True)

        worker.run(check, done, failed, owner=self)
