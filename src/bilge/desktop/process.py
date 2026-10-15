"""Running the desktop's own programs (wpctl, xdg-open, nmcli…): always an argument list, never a shell."""

import logging
import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 15
# Parsed output must not change with the user's language ("Mute: yes" would become "Sessiz: evet").
_PARSEABLE = {"LC_ALL": "C.UTF-8", "LANG": "C.UTF-8"}


class DesktopError(Exception):
    """The desktop could not do it. The message is for the log; tools speak their own sentence."""


class MissingProgram(DesktopError):
    """None of the programs that could do this is installed; `programs` are named to the user."""

    def __init__(self, *programs: str):
        super().__init__(f"Needs one of: {', '.join(programs)}")
        self.programs = programs


@dataclass(frozen=True)
class Completed:
    status: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.status == 0


class Runner:
    def which(self, program: str) -> str | None:
        return shutil.which(program)

    def has(self, program: str) -> bool:
        return self.which(program) is not None

    def run(
        self, argv: Sequence[str], input: str | None = None, timeout: float = TIMEOUT_SECONDS, capture: bool = True
    ) -> Completed:
        """`capture=False` is for programs that fork a child to keep serving (xclip, wl-copy): the child would
        hold the pipes open, and waiting for their end would wait for the next copy."""
        output = subprocess.PIPE if capture else subprocess.DEVNULL
        try:
            done = subprocess.run(
                list(argv), input=input, stdout=output, stderr=output, encoding="utf-8", errors="replace", timeout=timeout,
                env={**os.environ, **_PARSEABLE}, check=False,
            )  # fmt: skip
        except FileNotFoundError as error:
            raise MissingProgram(argv[0]) from error
        except subprocess.TimeoutExpired as error:
            raise DesktopError(f"{argv[0]} timed out") from error
        except OSError as error:
            raise DesktopError(f"{argv[0]} could not start: {error}") from error
        if done.returncode != 0:
            log.info("%s exited with %s: %s", argv[0], done.returncode, (done.stderr or "").strip()[:300])
        return Completed(done.returncode, done.stdout or "", done.stderr or "")

    def feed(self, argv: Sequence[str], source: Path, timeout: float = TIMEOUT_SECONDS) -> None:
        """Gives a file to a program on standard input (an image to the clipboard), without awaiting its output."""
        try:
            with source.open("rb") as stdin:
                subprocess.run(list(argv), stdin=stdin, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=timeout, check=True)  # fmt: skip
        except FileNotFoundError as error:
            raise MissingProgram(argv[0]) from error
        except (subprocess.SubprocessError, OSError) as error:
            raise DesktopError(f"{argv[0]} failed: {error}") from error

    def spawn(self, argv: Sequence[str]) -> None:
        """Starts a program that outlives the request (an app, a file viewer), detached from Bilge."""
        try:
            subprocess.Popen(
                list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )  # fmt: skip
        except FileNotFoundError as error:
            raise MissingProgram(argv[0]) from error
        except OSError as error:
            raise DesktopError(f"{argv[0]} could not start: {error}") from error

    def check(self, argv: Sequence[str], input: str | None = None, timeout: float = TIMEOUT_SECONDS) -> str:
        """Runs and returns the output, raising when the program reports failure."""
        done = self.run(argv, input=input, timeout=timeout)
        if not done.ok:
            raise DesktopError(f"{argv[0]} failed: {done.stderr.strip()[:300]}")
        return done.stdout
