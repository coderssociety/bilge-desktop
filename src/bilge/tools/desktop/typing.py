"""Typing dictated text into the app in front: "şunu yaz: …" once, or dictation mode for everything said.

Control characters are removed, so typing never presses Enter or Tab. Apps where typed text could run as a command
or land in a secret store (terminals, code editors, remote desktops, virtual machines, password managers) are
refused. Where the platform doesn't say which app is in front (GNOME on Wayland), Bilge asks before typing.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from bilge.core.dictation import dictation_command, dictation_text
from bilge.core.dictation.dictation_command import DictationCommand
from bilge.core.language import AssistantLanguage
from bilge.core.tools import typed_text
from bilge.desktop.base import FrontWindow, Keyboard
from bilge.desktop.process import DesktopError
from bilge.tools.base import Risk, Tool, ToolError
from bilge.tools.desktop.common import failure, obj, string_argument, text

REFUSED_PROGRAMS = frozenset(
    {
        # Terminals
        "gnome-terminal", "gnome-terminal-server", "kgx", "ptyxis", "konsole", "xterm", "uxterm", "kitty", "alacritty",
        "wezterm", "wezterm-gui", "foot", "footclient", "tilix", "terminator", "xfce4-terminal", "mate-terminal",
        "lxterminal", "qterminal", "terminology", "guake", "yakuake", "tilda", "urxvt", "rxvt", "st", "blackbox",
        "tabby", "hyper", "warp", "warp-terminal", "ghostty", "cool-retro-term", "deepin-terminal", "contour",
        "console", "terminal", "org.gnome.console", "org.gnome.ptyxis", "org.kde.konsole", "com.mitchellh.ghostty",
        "io.elementary.terminal", "org.gnome.terminal",
        # Windows: programs, and the window classes of consoles
        "windowsterminal", "wt", "cmd", "powershell", "powershell_ise", "pwsh", "conhost", "openconsole", "mintty",
        "putty", "mobaxterm", "termius", "consolewindowclass", "cascadia_hosting_window_class", "devenv", "mstsc",
        "vmconnect", "prl_client_app", "credentialuibroker", "wsl", "conemu64", "cmder", "msrdc", "dashlane",
        "lastpass", "nordpass", "roboform", "windsurf", "code - insiders", "code-insiders",
        "consent", "logonui",
        # Code editors with a built-in terminal
        "code", "code-oss", "codium", "vscodium", "cursor", "zed", "zeditor", "sublime_text", "gnome-builder",
        # Remote desktops and virtual machines
        "remmina", "krdc", "vncviewer", "xfreerdp", "wlfreerdp", "gnome-connections", "rustdesk", "anydesk",
        "teamviewer", "virt-manager", "virt-viewer", "remote-viewer", "virtualbox", "virtualboxvm", "vmware",
        "vmplayer", "gnome-boxes", "qemu-system-x86_64",
        # Password managers
        "keepassxc", "keepass", "1password", "bitwarden", "seahorse", "kwalletmanager5", "kwalletmanager6",
        "gnome-secrets", "secrets", "enpass", "proton-pass", "passwordsafe",
    }
)  # fmt: skip
REFUSED_PREFIXES = ("jetbrains-", "idea", "pycharm", "webstorm", "clion", "goland", "rider", "rubymine", "phpstorm")

_TEXTS = {
    AssistantLanguage.TURKISH: {
        "type": "Söylenen metni öndeki uygulamada imlecin olduğu yere yazar (dikte). Enter'a basmaz.",
        "text": "Yazılacak metin, kullanıcının söylediği gibi",
        "unclear": "Ne yazacağımı anlayamadım.",
        "refused": "Güvenlik için terminallere, kod düzenleyicilere, uzak masaüstüne, sanal makinelere ve parola yöneticilerine yazı yazmıyorum.",
        "unknown_front": "Öndeki pencereyi göremiyorum; imlecin olduğu yere yazayım mı?",
        "typed": "Yazdım.",
        "start": "Dikte modunu başlatır: söylenenleri öndeki uygulamaya yazar.",
        "started": "Dikte açık, {app} uygulamasına yazıyorum. Bitirmek için 'dikteyi bitir' de.",
        "started_unknown": "Dikte açık, öndeki uygulamaya yazıyorum. Bitirmek için 'dikteyi bitir' de.",
        "unknown_dictation": "Öndeki pencereyi göremiyorum; söylediklerini imlecin olduğu yere yazayım mı?",
        "front_changed": "Öndeki uygulama değişti, dikteyi bitirdim.",
        "finished": "Dikte bitti.",
        "nothing_to_delete": "Silinecek bir şey yok.",
    },
    AssistantLanguage.ENGLISH: {
        "type": "Types the given text where the cursor is in the app in front (dictation). Never presses Enter.",
        "text": "The text to type, as the user said it",
        "unclear": "I didn't get what to type.",
        "refused": "For safety I don't type into terminals, code editors, remote desktops, virtual machines or password managers.",
        "unknown_front": "I can't see which window is in front; shall I type where the cursor is?",
        "typed": "Done.",
        "start": "Starts dictation mode: types what the user says into the app in front.",
        "started": "Dictation is on; I'm typing into {app}. Say 'stop dictation' to finish.",
        "started_unknown": "Dictation is on; I'm typing into the app in front. Say 'stop dictation' to finish.",
        "unknown_dictation": "I can't see which window is in front; shall I type what you say where the cursor is?",
        "front_changed": "The app in front changed, so I stopped dictation.",
        "finished": "Dictation is over.",
        "nothing_to_delete": "There's nothing to delete.",
    },
}


def refuses(window: FrontWindow) -> bool:
    """Both the program and the window class count: a terminal written in Python runs as "python3", and a Flatpak
    app is known by its app id ("org.gnome.Console")."""
    names = {window.name.lower(), window.app_class.lower()} - {""}
    names |= {name.rsplit(".", 1)[-1] for name in names}
    return any(name in REFUSED_PROGRAMS or name.startswith(REFUSED_PREFIXES) for name in names)


def front_window(keyboard: Keyboard) -> FrontWindow | None:
    try:
        return keyboard.front_window()
    except DesktopError:
        return None


def front_app(keyboard: Keyboard) -> str | None:
    """The program in front, or None when the platform won't say. Window titles change while typing, so only the
    program and its class count."""
    window = front_window(keyboard)
    if window is None or not window.name:
        return None
    return f"{window.name}|{window.app_class}"


def type_text_tool(keyboard: Keyboard, language: AssistantLanguage) -> Tool:
    texts = _TEXTS[language]

    def question(_: dict[str, Any]) -> str | None:
        return texts["unknown_front"] if front_app(keyboard) is None else None

    def run(arguments: dict[str, Any]) -> str:
        content = typed_text.sanitized(string_argument(arguments, "text"))
        if not content:
            raise ToolError(texts["unclear"])
        front = front_window(keyboard)
        if front is not None and refuses(front):
            raise ToolError(texts["refused"])
        try:
            keyboard.type(content)
        except DesktopError as error:
            raise failure(error, language) from error
        return texts["typed"]

    return Tool("typeText", texts["type"], run=run, parameters=obj(["text"], text=text(texts["text"])),
                risk=Risk.CONFIRM, confirmation=question)  # fmt: skip


@dataclass
class DictationSession:
    """Hands-free dictation into one app: what was typed (so "son cümleyi sil" can take it back) and where.
    Typing stops when another app comes to the front."""

    keyboard: Keyboard
    language: AssistantLanguage
    # How long dictation waits for the next sentence before it ends. Where the window in front can't be checked,
    # dictation ends sooner, so speech meant for no one isn't typed into whatever came to the front meanwhile.
    window_seconds: float = 60
    unchecked_window_seconds: float = 20
    max_remembered: int = 50
    active: bool = False
    target: str | None = None
    typed: list[str] = field(default_factory=list)

    def window(self) -> float:
        return self.window_seconds if self.target is not None else self.unchecked_window_seconds

    def begin(self, target: str | None) -> None:
        self.active, self.target, self.typed = True, target, []

    def end(self) -> None:
        self.active, self.target, self.typed = False, None, []

    def handle(self, spoken: str) -> str:
        """One dictated utterance: a control ("yeni satır", "son cümleyi sil", "dikteyi bitir") or text. Returns what
        to say, usually nothing."""
        texts = _TEXTS[self.language]
        if not self.active:
            return ""
        if self.target is not None and front_app(self.keyboard) != self.target:
            self.end()
            return texts["front_changed"]
        try:
            command = dictation_command.parse(spoken, self.language)
            if command is DictationCommand.FINISH:
                self.end()
                return texts["finished"]
            if command is DictationCommand.NEW_LINE:
                self._new_line()
            elif command is DictationCommand.NEW_PARAGRAPH:
                self._new_line()
                self._new_line()
            elif command is DictationCommand.DELETE_LAST:
                if not self.typed:
                    return texts["nothing_to_delete"]
                self.keyboard.backspace(len(self.typed[-1]))
                self.typed = self.typed[:-1]
            else:
                content = typed_text.sanitized(dictation_text.format(spoken, "".join(self.typed), self.language))
                if content:
                    self.keyboard.type(content)
                    self._remember(content)
        except DesktopError as error:
            self.end()
            return str(failure(error, self.language))
        return ""

    def _new_line(self) -> None:
        self.keyboard.new_line()
        self._remember("\n")

    def _remember(self, content: str) -> None:
        self.typed = [*self.typed, content][-self.max_remembered :]


def start_dictation_tool(session: DictationSession, language: AssistantLanguage) -> Tool:
    texts = _TEXTS[language]

    def question(_: dict[str, Any]) -> str | None:
        return texts["unknown_dictation"] if front_app(session.keyboard) is None else None

    def run(_: dict[str, Any]) -> str:
        front = front_window(session.keyboard)
        if front is not None and refuses(front):
            raise ToolError(texts["refused"])
        session.begin(front_app(session.keyboard) if front else None)
        return texts["started"].format(app=front.name) if front and front.name else texts["started_unknown"]

    return Tool("startDictation", texts["start"], run=run, risk=Risk.CONFIRM, confirmation=question)


def dictation_owns(session: DictationSession) -> Callable[[str], bool]:
    """Controls like "dikteyi bitir" said with the wake word still steer an active dictation."""
    return lambda command: session.active and dictation_command.parse(command, session.language) is not None
