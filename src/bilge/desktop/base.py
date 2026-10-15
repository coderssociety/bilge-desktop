"""What the tools need from the operating system. Each platform provides these; the tools stay the same."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class AppEntry:
    """An installed application. `names` are everything the user might call it ("Hesap Makinesi", "calculator")."""

    id: str
    display_name: str
    names: tuple[str, ...]


@dataclass(frozen=True)
class FrontWindow:
    """The application in front. `name` is the program or window class, lowercase ("gnome-terminal-server");
    `app_class` the window class or Wayland app id ("org.gnome.console"), which names apps a script runs."""

    name: str
    title: str = ""
    app_class: str = ""


@dataclass(frozen=True)
class VolumeState:
    level: int
    muted: bool


@dataclass(frozen=True)
class NowPlaying:
    player: str
    playing: bool
    title: str = ""
    artist: str = ""


class MediaCommand(StrEnum):
    PLAY = "play"
    PAUSE = "pause"
    TOGGLE = "toggle"
    NEXT = "next"
    PREVIOUS = "previous"


class ScreenshotArea(StrEnum):
    WHOLE_SCREEN = "wholeScreen"
    FRONT_WINDOW = "frontWindow"
    SELECTION = "selection"


class Apps(Protocol):
    def installed(self) -> list[AppEntry]: ...

    def launch(self, app: AppEntry) -> None: ...

    def running(self) -> list[AppEntry]: ...

    def quit(self, app: AppEntry) -> bool:
        """Asks the app to close; False when it wasn't running."""
        ...


class Volume(Protocol):
    def state(self) -> VolumeState: ...

    def set_level(self, level: int) -> None: ...

    def set_muted(self, muted: bool) -> None: ...


class Media(Protocol):
    def now_playing(self) -> NowPlaying | None:
        """None when no player is open."""
        ...

    def send(self, command: MediaCommand) -> str:
        """Returns the player's name."""
        ...


class Clipboard(Protocol):
    def read(self) -> str: ...

    def write(self, text: str) -> None: ...

    def selection(self) -> str:
        """The text selected in the app in front, or empty."""
        ...


class Keyboard(Protocol):
    def front_window(self) -> FrontWindow | None:
        """None when the platform doesn't say which app is in front."""
        ...

    def type(self, text: str) -> None: ...

    def new_line(self) -> None:
        """Shift+Enter: a line break even where Enter would send a message."""
        ...

    def backspace(self, count: int) -> None: ...


class Session(Protocol):
    def lock(self) -> None: ...

    def suspend(self) -> None: ...

    def dark_mode(self) -> bool | None: ...

    def set_dark_mode(self, dark: bool) -> None: ...


class Network(Protocol):
    def wifi_enabled(self) -> bool | None: ...

    def set_wifi(self, enabled: bool) -> None: ...


class Screenshots(Protocol):
    def capture(self, area: ScreenshotArea, destination: Path) -> bool:
        """False when the user cancelled (for example, no area was selected)."""
        ...

    def copy_image(self, image: Path) -> None: ...


class SettingsPanes(Protocol):
    def open(self, pane: str) -> bool:
        """`pane` is one of the names in `bilge.core.conversation.quick_intent_parser.SettingsPane`; False when this
        desktop has no such page, in which case the main settings window is opened."""
        ...


class Opener(Protocol):
    def open(self, target: str) -> None:
        """A web address or a file, in the app the user chose for it."""
        ...

    def reveal(self, path: Path) -> None:
        """Shows the file selected in the file manager, without opening it."""
        ...


class Folders(Protocol):
    """The user's standard folders, which may have translated names ("Masaüstü", "İndirilenler")."""

    def home(self) -> Path: ...

    def desktop(self) -> Path: ...

    def downloads(self) -> Path: ...

    def documents(self) -> Path: ...

    def pictures(self) -> Path: ...


class Notifier(Protocol):
    def notify(self, title: str, body: str) -> None: ...


@dataclass(frozen=True)
class Desktop:
    apps: Apps
    volume: Volume
    media: Media
    clipboard: Clipboard
    keyboard: Keyboard
    session: Session
    network: Network
    screenshots: Screenshots
    settings: SettingsPanes
    opener: Opener
    notifier: Notifier
    folders: Folders
