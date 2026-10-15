"""The clipboard and the selection. X11 and Wayland both keep the last selected text as the "primary selection",
so reading what is selected needs no copy shortcut."""

from bilge.desktop.linux.environment import Environment
from bilge.desktop.process import MissingProgram, Runner

_WAYLAND = ("wl-paste", "wl-copy")
_X11 = ("xclip", "xsel")


class LinuxClipboard:
    def __init__(self, runner: Runner, environment: Environment):
        self._runner = runner
        self._environment = environment

    def _tool(self) -> str:
        # Under Wayland, X11 tools only see the clipboard of X11 apps, so wl-clipboard comes first.
        order = ["wl-copy", *_X11] if self._environment.wayland else [*_X11, "wl-copy"]
        for program in order:
            if self._runner.has(program):
                return program
        raise MissingProgram("wl-clipboard", "xclip", "xsel")

    def read(self) -> str:
        return self._paste(primary=False)

    def selection(self) -> str:
        return self._paste(primary=True)

    def _paste(self, primary: bool) -> str:
        tool = self._tool()
        if tool == "wl-copy":
            # "text" picks whichever text type the app offers, and nothing when only an image was copied.
            argv = ["wl-paste", "--no-newline", *(["--primary"] if primary else []), "--type", "text"]
        elif tool == "xclip":
            argv = ["xclip", "-selection", "primary" if primary else "clipboard", "-out"]
        else:
            argv = ["xsel", "--primary" if primary else "--clipboard", "--output"]
        done = self._runner.run(argv, timeout=5)
        # An empty clipboard is an error for wl-paste and xclip; for the user it is just nothing.
        return done.stdout if done.ok else ""

    def write(self, text: str) -> None:
        tool = self._tool()
        if tool == "wl-copy":
            argv = ["wl-copy", "--type", "text/plain;charset=utf-8"]
        elif tool == "xclip":
            argv = ["xclip", "-selection", "clipboard", "-in"]
        else:
            argv = ["xsel", "--clipboard", "--input"]
        # These stay running to serve the copied text, so their output is not awaited.
        self._runner.run(argv, input=text, timeout=5, capture=False)


def image_command(runner: Runner, environment: Environment) -> list[str]:
    """Copies a PNG given on standard input."""
    if environment.wayland and runner.has("wl-copy"):
        return ["wl-copy", "--type", "image/png"]
    if runner.has("xclip"):
        return ["xclip", "-selection", "clipboard", "-target", "image/png", "-in"]
    raise MissingProgram("wl-clipboard", "xclip")
