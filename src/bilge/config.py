"""Where Bilge keeps settings and data on each system, and the API keys in the system's own key store."""

import contextlib
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from bilge.core.language import AssistantLanguage

APP_NAME = "Bilge"
KEYRING_SERVICE = "bilge"
# Read when no key is stored, so a key already exported for other tools works without setup.
KEY_ENVIRONMENT = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}


def config_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / f"{APP_NAME} Desktop"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME.lower()


def data_dir() -> Path:
    if sys.platform in ("win32", "darwin"):
        return config_dir()
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME.lower()


@dataclass
class ModelSettings:
    provider: str = "lmstudio"
    model: str = ""
    # Overrides the provider's usual address, for a server on another port or machine.
    base_url: str | None = None


@dataclass
class VoiceSettings:
    # "local" (Whisper on this computer), or a transcription API: "openai", "groq".
    recognizer: str = "local"
    recognizer_model: str = ""
    voice: str = "F1"
    wake_phrase: str = "bilge"
    follow_up: bool = True
    barge_in: bool = True
    speaker_check: bool = False
    input_device: str | None = None
    output_device: str | None = None


@dataclass
class CalendarSettings:
    # "caldav" (read and write: Nextcloud, iCloud, Fastmail, Radicale…), "ics" (a read-only address, such as
    # Google Calendar's secret iCal address), or "" for none. Passwords and the secret address are in the key store.
    kind: str = ""
    url: str = ""
    username: str = ""
    # The calendar new events go to; the first one that takes events when empty.
    name: str = ""


@dataclass
class Settings:
    language: str = AssistantLanguage.TURKISH.value
    model: ModelSettings = field(default_factory=ModelSettings)
    # Used when a weather question names no city.
    weather_city: str = "İstanbul"
    voice: VoiceSettings = field(default_factory=VoiceSettings)
    calendar: CalendarSettings = field(default_factory=CalendarSettings)

    @property
    def assistant_language(self) -> AssistantLanguage:
        try:
            return AssistantLanguage(self.language)
        except ValueError:
            return AssistantLanguage.TURKISH


def settings_path() -> Path:
    return config_dir() / "settings.json"


def load_settings(path: Path | None = None) -> Settings:
    path = path or settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Settings()
    except (OSError, ValueError) as error:
        raise RuntimeError(f"Could not read {path}: {error}") from error
    model = data.get("model") or {}
    voice = data.get("voice") if isinstance(data.get("voice"), dict) else {}
    defaults = VoiceSettings()
    calendar = data.get("calendar") if isinstance(data.get("calendar"), dict) else {}
    return Settings(
        calendar=CalendarSettings(
            kind=str(calendar.get("kind", "")),
            url=str(calendar.get("url", "")),
            username=str(calendar.get("username", "")),
            name=str(calendar.get("name", "")),
        ),
        voice=VoiceSettings(
            recognizer=str(voice.get("recognizer", defaults.recognizer)),
            recognizer_model=str(voice.get("recognizer_model", "")),
            voice=str(voice.get("voice", defaults.voice)),
            wake_phrase=str(voice.get("wake_phrase") or defaults.wake_phrase),
            follow_up=bool(voice.get("follow_up", defaults.follow_up)),
            barge_in=bool(voice.get("barge_in", defaults.barge_in)),
            speaker_check=bool(voice.get("speaker_check", defaults.speaker_check)),
            input_device=voice.get("input_device") or None,
            output_device=voice.get("output_device") or None,
        ),
        language=str(data.get("language", AssistantLanguage.TURKISH.value)),
        weather_city=str(data.get("weather_city") or "İstanbul"),
        model=ModelSettings(
            provider=str(model.get("provider", "lmstudio")),
            model=str(model.get("model", "")),
            base_url=model.get("base_url") or None,
        ),
    )


def save_settings(settings: Settings, path: Path | None = None) -> None:
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def api_key(provider: str) -> str | None:
    try:
        stored = keyring.get_password(KEYRING_SERVICE, provider)
    except KeyringError:
        stored = None
    if stored:
        return stored
    variable = KEY_ENVIRONMENT.get(provider)
    return os.environ.get(variable) if variable else None


def store_api_key(provider: str, key: str) -> None:
    """Raises KeyringError when the system has no key store (for example a Linux session without one)."""
    keyring.set_password(KEYRING_SERVICE, provider, key)


def delete_api_key(provider: str) -> None:
    with contextlib.suppress(PasswordDeleteError):
        keyring.delete_password(KEYRING_SERVICE, provider)
