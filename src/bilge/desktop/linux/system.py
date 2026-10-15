"""Session and system controls: locking, sleep, dark mode, Wi-Fi, settings pages, screenshots, notifications and
opening files or addresses."""

import os
from pathlib import Path
from urllib.parse import quote

from bilge.desktop.base import ScreenshotArea
from bilge.desktop.linux.clipboard import image_command
from bilge.desktop.linux.dbus import Bus
from bilge.desktop.linux.environment import Environment
from bilge.desktop.process import DesktopError, MissingProgram, Runner

_GNOME_SCHEMA = "org.gnome.desktop.interface"
# The user drags a rectangle, which can take a while.
_SELECTION_SECONDS = 60


class LinuxSession:
    def __init__(self, runner: Runner, environment: Environment):
        self._runner = runner
        self._environment = environment

    def lock(self) -> None:
        if self._runner.has("loginctl") and self._runner.run(["loginctl", "lock-session"]).ok:
            return
        if self._runner.has("xdg-screensaver"):
            self._runner.check(["xdg-screensaver", "lock"])
            return
        raise MissingProgram("loginctl", "xdg-screensaver")

    def suspend(self) -> None:
        if not self._runner.has("systemctl"):
            raise MissingProgram("systemctl")
        self._runner.check(["systemctl", "suspend"])

    def dark_mode(self) -> bool | None:
        if self._environment.kde:
            for program in ("kreadconfig6", "kreadconfig5"):
                if self._runner.has(program):
                    scheme = self._runner.run([program, "--group", "General", "--key", "ColorScheme"]).stdout
                    return "dark" in scheme.lower()
            return None
        if self._runner.has("gsettings"):
            done = self._runner.run(["gsettings", "get", _GNOME_SCHEMA, "color-scheme"])
            return "dark" in done.stdout if done.ok else None
        return None

    def set_dark_mode(self, dark: bool) -> None:
        if self._environment.kde:
            if not self._runner.has("plasma-apply-colorscheme"):
                raise MissingProgram("plasma-apply-colorscheme")
            self._runner.check(["plasma-apply-colorscheme", "BreezeDark" if dark else "BreezeLight"])
            return
        if not self._runner.has("gsettings"):
            raise MissingProgram("gsettings")
        # GNOME 42 and later; apps that follow the portal setting switch at once.
        self._runner.check(["gsettings", "set", _GNOME_SCHEMA, "color-scheme", "prefer-dark" if dark else "default"])


class LinuxNetwork:
    def __init__(self, runner: Runner):
        self._runner = runner

    def wifi_enabled(self) -> bool | None:
        if not self._runner.has("nmcli"):
            return None
        done = self._runner.run(["nmcli", "radio", "wifi"])
        return done.stdout.strip() == "enabled" if done.ok else None

    def set_wifi(self, enabled: bool) -> None:
        if not self._runner.has("nmcli"):
            raise MissingProgram("nmcli")
        self._runner.check(["nmcli", "radio", "wifi", "on" if enabled else "off"])


class LinuxScreenshots:
    def __init__(self, runner: Runner, environment: Environment):
        self._runner = runner
        self._environment = environment

    def capture(self, area: ScreenshotArea, destination: Path) -> bool:
        argv = self._command(area, destination)
        if argv is None:
            return False
        timeout = _SELECTION_SECONDS if area is ScreenshotArea.SELECTION else 15
        done = self._runner.run(argv, timeout=timeout)
        # Cancelling a selection exits with an error and writes nothing.
        return done.ok and destination.exists()

    def _command(self, area: ScreenshotArea, file: Path) -> list[str] | None:
        """None when the user cancelled choosing an area."""
        has = self._runner.has
        path = str(file)
        if self._environment.kde and has("spectacle"):
            mode = {
                ScreenshotArea.WHOLE_SCREEN: "-f",
                ScreenshotArea.FRONT_WINDOW: "-a",
                ScreenshotArea.SELECTION: "-r",
            }
            return ["spectacle", "-b", "-n", mode[area], "-o", path]
        if self._environment.gnome and has("gnome-screenshot"):
            mode = {
                ScreenshotArea.WHOLE_SCREEN: [],
                ScreenshotArea.FRONT_WINDOW: ["-w"],
                ScreenshotArea.SELECTION: ["-a"],
            }
            return ["gnome-screenshot", *mode[area], "-f", path]
        if self._environment.wayland and has("grim"):
            if area is ScreenshotArea.SELECTION:
                if not has("slurp"):
                    raise MissingProgram("slurp")
                region = self._runner.run(["slurp"], timeout=_SELECTION_SECONDS)
                if not region.ok:
                    return None
                return ["grim", "-g", region.stdout.strip(), path]
            return ["grim", path]
        if not self._environment.wayland:
            if has("maim"):
                mode = {ScreenshotArea.WHOLE_SCREEN: [], ScreenshotArea.FRONT_WINDOW: ["-i", self._active_window()],
                        ScreenshotArea.SELECTION: ["-s"]}  # fmt: skip
                return ["maim", *mode[area], path]
            if has("scrot"):
                mode = {
                    ScreenshotArea.WHOLE_SCREEN: [],
                    ScreenshotArea.FRONT_WINDOW: ["-u"],
                    ScreenshotArea.SELECTION: ["-s"],
                }
                return ["scrot", *mode[area], path]
        raise MissingProgram("gnome-screenshot", "spectacle", "grim", "maim", "scrot")

    def _active_window(self) -> str:
        if not self._runner.has("xdotool"):
            raise MissingProgram("xdotool")
        return self._runner.check(["xdotool", "getactivewindow"]).strip()

    def copy_image(self, image: Path) -> None:
        self._runner.feed(image_command(self._runner, self._environment), image)


# GNOME Settings panel and KDE System Settings module for each page the assistant knows.
_GNOME_PANELS = {
    "wifi": "wifi", "bluetooth": "bluetooth", "network": "network", "sound": "sound", "displays": "display",
    "battery": "power", "notifications": "notifications", "privacy": "privacy", "keyboard": "keyboard",
    "general": "system", "wallpaper": "background", "accessibility": "universal-access", "mouse": "mouse",
    "trackpad": "mouse", "storage": "usage", "focus": "notifications",
}  # fmt: skip
_KDE_MODULES = {
    "wifi": "kcm_networkmanagement", "network": "kcm_networkmanagement", "bluetooth": "kcm_bluetooth",
    "sound": "kcm_pulseaudio", "displays": "kcm_kscreen", "battery": "kcm_powerdevilprofilesconfig",
    "notifications": "kcm_notifications", "keyboard": "kcm_keyboard", "wallpaper": "kcm_wallpaper",
    "accessibility": "kcm_access", "mouse": "kcm_mouse", "trackpad": "kcm_touchpad", "general": "kcm_about-distro",
    "privacy": "kcm_screenlocker", "focus": "kcm_notifications",
}  # fmt: skip


class LinuxSettings:
    def __init__(self, runner: Runner, environment: Environment):
        self._runner = runner
        self._environment = environment

    def open(self, pane: str) -> bool:
        if pane == "softwareUpdate":
            for argv in (["gnome-software", "--mode=updates"], ["plasma-discover", "--mode", "update"]):
                if self._runner.has(argv[0]):
                    self._runner.spawn(argv)
                    return True
        if self._environment.kde and self._runner.has("systemsettings"):
            module = _KDE_MODULES.get(pane)
            self._runner.spawn(["systemsettings", *([module] if module else [])])
            return module is not None
        if self._runner.has("gnome-control-center"):
            panel = _GNOME_PANELS.get(pane)
            self._runner.spawn(["gnome-control-center", *([panel] if panel else [])])
            return panel is not None
        raise MissingProgram("gnome-control-center", "systemsettings")


class LinuxOpener:
    def __init__(self, runner: Runner, bus: Bus):
        self._runner = runner
        self._bus = bus

    def open(self, target: str) -> None:
        for argv in (["xdg-open", target], ["gio", "open", target]):
            if self._runner.has(argv[0]):
                self._runner.spawn(argv)
                return
        raise MissingProgram("xdg-open")

    def reveal(self, path: Path) -> None:
        uri = "file://" + quote(str(path.resolve()))
        try:
            self._bus.call("org.freedesktop.FileManager1", "/org/freedesktop/FileManager1",
                           "org.freedesktop.FileManager1", "ShowItems", "ass", [uri], "")  # fmt: skip
        except DesktopError:
            # No file manager answers on the bus (some lightweight desktops): open the folder instead.
            self.open(str(path.parent))


class LinuxNotifier:
    def __init__(self, runner: Runner, bus: Bus, app_name: str = "Bilge"):
        self._runner = runner
        self._bus = bus
        self._app_name = app_name

    def notify(self, title: str, body: str) -> None:
        try:
            self._bus.call("org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                           "org.freedesktop.Notifications", "Notify", "susssasa{sv}i",
                           self._app_name, 0, "", title, body, [], {}, -1)  # fmt: skip
        except DesktopError:
            if not self._runner.has("notify-send"):
                raise
            self._runner.run(["notify-send", "--app-name", self._app_name, title, body])


class LinuxFolders:
    def home(self) -> Path:
        return Path.home()

    def desktop(self) -> Path:
        return user_dir("DESKTOP", "Desktop")

    def downloads(self) -> Path:
        return user_dir("DOWNLOAD", "Downloads")

    def documents(self) -> Path:
        return user_dir("DOCUMENTS", "Documents")

    def pictures(self) -> Path:
        return user_dir("PICTURES", "Pictures")


def user_dir(name: str, fallback: str, environ: dict[str, str] | None = None) -> Path:
    """An XDG user folder ("DESKTOP", "DOWNLOAD", "DOCUMENTS", "PICTURES"), which may be translated ("Masaüstü")."""
    env = os.environ if environ is None else environ
    home = Path(env.get("HOME", str(Path.home())))
    config = Path(env.get("XDG_CONFIG_HOME") or home / ".config") / "user-dirs.dirs"
    try:
        for line in config.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == f"XDG_{name}_DIR":
                folder = value.strip().strip('"').replace("$HOME", str(home))
                return Path(folder)
    except OSError:
        pass
    return home / fallback
