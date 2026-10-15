"""Installed applications from their .desktop files (the freedesktop.org menu entries every Linux desktop reads)."""

import os
import shlex
import signal
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from bilge.desktop.base import AppEntry
from bilge.desktop.process import DesktopError, Runner

# Exec field codes (%f, %U…) stand for files the launcher passes; Bilge passes none.
_FIELD_CODES = frozenset({"%f", "%F", "%u", "%U", "%i", "%c", "%k", "%d", "%D", "%n", "%N", "%v", "%m"})
_WRAPPERS = frozenset({"env", "flatpak", "snap", "gtk-launch", "gio"})
# A process started as "python3 /usr/bin/foo" is known by the script, not the interpreter; matching on the interpreter
# would close every Python program at once.
_INTERPRETERS = frozenset(
    {"python", "python3", "perl", "ruby", "node", "java", "sh", "bash", "gjs", "mono", "electron"}
)


@dataclass(frozen=True)
class DesktopFile:
    id: str
    path: Path
    name: str
    names: tuple[str, ...]
    exec: str
    # Program names a running process of this app may have.
    binaries: frozenset[str]
    flatpak: str | None = None


def search_dirs(environ: dict[str, str] | None = None) -> list[Path]:
    env = os.environ if environ is None else environ
    home = Path(env.get("HOME", str(Path.home())))
    data_home = Path(env.get("XDG_DATA_HOME") or home / ".local/share")
    data_dirs = [Path(d) for d in (env.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":") if d]
    # Flatpak and Snap usually add themselves to XDG_DATA_DIRS; listed again for sessions that don't.
    extra = [home / ".local/share/flatpak/exports/share", Path("/var/lib/flatpak/exports/share"),
             Path("/var/lib/snapd/desktop")]  # fmt: skip
    seen: list[Path] = []
    for base in [data_home, *data_dirs, *extra]:
        folder = base / "applications"
        if folder not in seen:
            seen.append(folder)
    return seen


def parse(path: Path, desktop_id: str, languages: tuple[str, ...]) -> DesktopFile | None:
    """None for entries that are not launchable apps (hidden ones, links, terminal programs)."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    fields: dict[str, str] = {}
    in_entry = False
    for line in lines:
        line = line.strip()
        if line.startswith("["):
            in_entry = line == "[Desktop Entry]"
            continue
        if in_entry and "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            fields.setdefault(key.strip(), value.strip())
    if fields.get("Type") != "Application" or not fields.get("Name") or not fields.get("Exec"):
        return None
    if any(fields.get(key, "").lower() == "true" for key in ("Hidden", "NoDisplay", "Terminal")):
        return None
    localized = [fields.get(f"{key}[{lang}]") for key in ("Name", "GenericName") for lang in languages]
    display = next((name for name in localized[: len(languages)] if name), fields["Name"])
    stem = desktop_id.removesuffix(".desktop")
    names = [display, fields["Name"], *localized, fields.get("GenericName"), stem.split(".")[-1]]
    binaries, flatpak = _binaries(fields)
    unique = tuple(dict.fromkeys(name for name in names if name))
    return DesktopFile(desktop_id, path, display, unique, fields["Exec"], binaries, flatpak)


def _binaries(fields: dict[str, str]) -> tuple[frozenset[str], str | None]:
    try:
        words = shlex.split(fields["Exec"])
    except ValueError:
        words = fields["Exec"].split()
    flatpak = None
    if words and Path(words[0]).name == "flatpak" and "run" in words:
        flatpak = next((w for w in words[words.index("run") + 1 :] if not w.startswith("-")), None)
    candidates = [w for w in words if "=" not in w and not w.startswith("-") and Path(w).name not in _WRAPPERS]
    while candidates and _is_interpreter(Path(candidates[0]).name):
        candidates = candidates[1:]
    program = Path(candidates[0]).name if candidates else None
    if program in _LAUNCHERS and len([w for w in words if w not in _FIELD_CODES]) > 1 + words.index(candidates[0]):
        return frozenset(), flatpak
    names = {Path(p).name for p in (program, fields.get("TryExec")) if p}
    return frozenset(name for name in names if not _is_interpreter(name)), flatpak


# Programs that start many different things. An entry that passes them arguments ("chrome --app-id=…" for a web
# app, "steam steam://rungameid/…") can't be told apart from the rest by process name, so it is never matched.
_LAUNCHERS = frozenset(
    {
        "google-chrome", "google-chrome-stable", "chrome", "chromium", "chromium-browser", "microsoft-edge",
        "microsoft-edge-stable", "brave-browser", "vivaldi", "opera", "firefox", "steam", "wine", "wine64",
        "dotnet", "xdg-open", "uv", "run", "snap", "electron",
    }
)  # fmt: skip


def _is_interpreter(name: str) -> bool:
    return name.rstrip("0123456789.") in _INTERPRETERS


def launch_command(entry: DesktopFile) -> list[str]:
    """The Exec line without field codes, for desktops that have neither gio nor gtk-launch."""
    words = [w.replace("%%", "%") for w in shlex.split(entry.exec) if w not in _FIELD_CODES]
    if not words:
        raise DesktopError(f"Empty Exec in {entry.path}")
    return words


class LinuxApps:
    def __init__(
        self,
        runner: Runner,
        languages: tuple[str, ...] = ("tr_TR", "tr"),
        dirs: Callable[[], list[Path]] = search_dirs,
        processes: Callable[[], Iterable[tuple[int, str]]] | None = None,
    ):
        self._runner = runner
        self._languages = languages
        self._dirs = dirs
        self._processes = processes or own_processes
        self._entries: dict[str, DesktopFile] | None = None

    def entries(self) -> dict[str, DesktopFile]:
        if self._entries is None:
            found: dict[str, DesktopFile] = {}
            for folder in self._dirs():
                for path in sorted(folder.rglob("*.desktop")) if folder.is_dir() else []:
                    # Subfolders become part of the id ("kde4/kate.desktop" is "kde4-kate.desktop").
                    desktop_id = str(path.relative_to(folder)).replace(os.sep, "-")
                    # The first folder in the search order wins, so a user's own copy overrides the system's.
                    if desktop_id in found:
                        continue
                    entry = parse(path, desktop_id, self._languages)
                    if entry is not None:
                        found[desktop_id] = entry
            self._entries = found
        return self._entries

    def installed(self) -> list[AppEntry]:
        return [AppEntry(e.id, e.name, e.names) for e in self.entries().values()]

    def launch(self, app: AppEntry) -> None:
        entry = self.entries()[app.id]
        # The app inherits the launcher's output, so it is not captured: waiting for it would wait for the app to exit.
        if self._runner.has("gio"):
            done = self._runner.run(["gio", "launch", str(entry.path)], capture=False)
            if done.ok:
                return
        if self._runner.has("gtk-launch"):
            done = self._runner.run(["gtk-launch", entry.id], capture=False)
            if done.ok:
                return
        self._runner.spawn(launch_command(entry))

    def running(self) -> list[AppEntry]:
        pids = self._pids_by_app()
        return [AppEntry(e.id, e.name, e.names) for e in self.entries().values() if pids.get(e.id)]

    def quit(self, app: AppEntry) -> bool:
        pids = self._pids_by_app().get(app.id, [])
        refused = []
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
            except PermissionError:
                refused.append(pid)
        if refused and len(refused) == len(pids):
            raise DesktopError(f"Not allowed to stop {refused}")
        return bool(pids)

    def _pids_by_app(self) -> dict[str, list[int]]:
        by_binary: dict[str, list[int]] = {}
        for pid, binary in self._processes():
            by_binary.setdefault(binary, []).append(pid)
        flatpaks = self._flatpak_pids()
        result: dict[str, list[int]] = {}
        for entry in self.entries().values():
            if entry.flatpak:
                pids = flatpaks.get(entry.flatpak, [])
            else:
                pids = [pid for binary in entry.binaries for pid in by_binary.get(binary, [])]
            if pids:
                result[entry.id] = sorted(set(pids))
        return result

    def _flatpak_pids(self) -> dict[str, list[int]]:
        if not self._runner.has("flatpak"):
            return {}
        done = self._runner.run(["flatpak", "ps", "--columns=child-pid,application"])
        result: dict[str, list[int]] = {}
        for line in done.stdout.splitlines() if done.ok else []:
            parts = line.split()
            if len(parts) == 2 and parts[0].isdigit():
                result.setdefault(parts[1], []).append(int(parts[0]))
        return result


def own_processes(proc: Path = Path("/proc")) -> Iterable[tuple[int, str]]:
    """(pid, program name) for this user's processes, Bilge and its parents excluded."""
    uid = os.getuid()
    excluded = {os.getpid(), os.getppid()}
    for folder in proc.iterdir() if proc.is_dir() else []:
        if not folder.name.isdigit() or int(folder.name) in excluded:
            continue
        try:
            if folder.stat().st_uid != uid:
                continue
            argv = (folder / "cmdline").read_bytes().split(b"\0")
            exe = os.readlink(folder / "exe")
        except OSError:
            continue
        words = [Path(a.decode(errors="replace")).name for a in argv[:2]]
        names = {Path(exe).name, words[0]}
        if _is_interpreter(words[0]) and len(words) > 1:
            names.add(words[1])
        for name in names - {""}:
            if not _is_interpreter(name):
                yield int(folder.name), name
