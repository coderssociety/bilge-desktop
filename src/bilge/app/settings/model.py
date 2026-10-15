"""Choosing the language model: a server on this computer (LM Studio, Ollama, llama.cpp) or a hosted API. The key
goes to the system key store, never into the settings file."""

from PySide6.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from bilge import config
from bilge.app import worker
from bilge.app.texts import t
from bilge.llm.providers import PRESETS, make_provider

LOCAL = ("lmstudio", "ollama", "llamacpp")


def list_models(provider: str, key: str | None, base_url: str | None) -> list[str]:
    return make_provider(provider, "-", key or config.api_key(provider), base_url or None).list_models()


class ModelChooser(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.provider = QComboBox()
        for group, ids in ((t("model.local"), LOCAL), (t("model.hosted"), [p for p in PRESETS if p not in LOCAL])):
            self.provider.addItem(group)
            # The group names are headings, not choices.
            self.provider.model().item(self.provider.count() - 1).setEnabled(False)
            for preset in ids:
                self.provider.addItem(f"   {PRESETS[preset].name}", preset)
        self.model = QComboBox(editable=True)
        self.fetch = QPushButton(t("model.fetch"))
        self.fetch.clicked.connect(self.fetch_models)
        self.base_url = QLineEdit()
        self.key = QLineEdit(echoMode=QLineEdit.EchoMode.Password, placeholderText=t("model.key_placeholder"))
        self.key_state = QLabel(wordWrap=True)
        self.note = QLabel(t("model.privacy"), wordWrap=True)
        self.message = QLabel(wordWrap=True)
        row = QHBoxLayout()
        row.addWidget(self.model, 1)
        row.addWidget(self.fetch)
        form = QFormLayout(self)
        form.addRow(t("model.provider"), self.provider)
        form.addRow(t("model.model"), row)
        form.addRow(t("model.base_url"), self.base_url)
        self.key_label = QLabel(t("model.key"))
        form.addRow(self.key_label, self.key)
        form.addRow("", self.key_state)
        form.addRow("", self.note)
        form.addRow("", self.message)
        self.provider.currentIndexChanged.connect(self._provider_changed)

    @property
    def chosen(self) -> str:
        return self.provider.currentData() or "lmstudio"

    def load(self, settings: config.Settings) -> None:
        index = self.provider.findData(settings.model.provider)
        self.provider.setCurrentIndex(index if index >= 0 else self.provider.findData("lmstudio"))
        self.model.setCurrentText(settings.model.model)
        self.base_url.setText(settings.model.base_url or "")
        self._provider_changed()

    def apply(self, settings: config.Settings) -> None:
        settings.model = config.ModelSettings(
            self.chosen, self.model.currentText().strip(), self.base_url.text().strip() or None
        )

    def save_secrets(self) -> None:
        if self.key.text().strip():
            config.store_api_key(self.chosen, self.key.text().strip())
            self.key.clear()

    def _provider_changed(self) -> None:
        # A key typed for one provider must never be stored as, or sent to, another.
        self.key.clear()
        preset = PRESETS[self.chosen]
        hosted = preset.needs_key
        for widget in (self.key_label, self.key, self.key_state, self.note):
            widget.setVisible(hosted)
        self.base_url.setPlaceholderText(preset.base_url)
        if hosted:
            self.key_state.setText(t("model.key_stored") if config.api_key(preset.id) else t("model.key_missing"))
        self.message.clear()

    def fetch_models(self) -> None:
        self.fetch.setEnabled(False)
        provider, key, base_url = self.chosen, self.key.text().strip(), self.base_url.text().strip()

        def done(found: list[str]) -> None:
            current = self.model.currentText()
            self.model.clear()
            self.model.addItems(found)
            self.model.setCurrentText(current if current in found else (found[0] if found else current))
            self.message.setText(t("model.found", count=len(found)))
            self.fetch.setEnabled(True)

        def failed(error: str) -> None:
            self.message.setText(t("model.fetch_failed", error=error))
            self.fetch.setEnabled(True)

        worker.run(lambda: list_models(provider, key, base_url), done, failed, owner=self)
