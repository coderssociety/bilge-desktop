"""LibreOffice Calc, driven through its UNO API.

The `uno` module only exists in the Python LibreOffice was built with (the system Python with python3-uno on Linux,
LibreOffice's own on Windows), not in Bilge's environment, so `uno_server.py` runs there as a helper and is spoken
to over its standard input and output. LibreOffice is asked to accept connections on a named pipe with
`soffice --accept=…`; when it is already running, that request goes to the open instance.
"""

import contextlib
import json
import os
import queue
import secrets
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

from bilge.core.spreadsheet.cell_reference import CellReference, SpreadsheetNumber, SpreadsheetValue
from bilge.desktop.process import DesktopError, Runner

PIPE_PREFIX = "bilge_calc_"
ANSWER_SECONDS = 10
CONNECT_ATTEMPTS = 6
CONNECT_PAUSE_SECONDS = 0.5
# Larger ranges are refused rather than read cell by cell.
MAX_CELLS = 10_000
_SERVER = Path(__file__).with_name("uno_server.py")
_PROCESS_NAMES = frozenset({"soffice.bin", "soffice", "soffice.exe", "libreoffice"})


class CalcError(Exception):
    """`reason`: "not_running", "no_uno", "no_document", "no_sheet", "too_large", "not_connected", "failed"."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


@dataclass(frozen=True)
class Location:
    """The sheet a change was made in, so undo goes back to the same one even if another is in front."""

    document: str
    title: str
    sheet: str


def uno_python_candidates() -> list[str]:
    configured = os.environ.get("BILGE_UNO_PYTHON")
    if configured:
        return [configured]
    if sys.platform == "win32":
        roots = [os.environ.get("PROGRAMFILES", r"C:\Program Files"), os.environ.get("PROGRAMFILES(X86)", "")]
        return [str(Path(root) / "LibreOffice" / "program" / "python.exe") for root in roots if root]
    bundled = sorted(Path("/opt").glob("libreoffice*/program/python"), reverse=True)
    system = [path for path in ("/usr/bin/python3", shutil.which("python3")) if path]
    return [*map(str, bundled), *dict.fromkeys(system)]


def calc_formula(formula: str) -> str:
    """Formulas are written with Excel's commas ("=AVERAGE(B1,B2)"); Calc's API separates arguments with
    semicolons. Commas inside quoted text stay."""
    converted, quoted = [], False
    for character in formula:
        if character == '"':
            quoted = not quoted
        converted.append(";" if character == "," and not quoted else character)
    return "".join(converted)


class LibreOfficeCalc:
    def __init__(self, runner: Runner, candidates: list[str] | None = None):
        self._runner = runner
        self._candidates = candidates
        self._python: str | None = None
        self._process: subprocess.Popen | None = None
        self._answers: queue.Queue[str | None] = queue.Queue()
        self._lock = threading.Lock()
        # Each session opens its own pipe and closes it again, so no acceptor is left behind for another program.
        self.pipe = PIPE_PREFIX + secrets.token_hex(8)
        self._accepting = False

    def is_running(self) -> bool:
        for process in psutil.process_iter(["name"]):
            if (process.info.get("name") or "").lower() in _PROCESS_NAMES:
                return True
        return False

    def location(self) -> Location | None:
        found = self._request({"op": "location"})
        return Location(found["document"], found["title"], found["sheet"]) if found else None

    def formula(self, at: Location, cell: CellReference) -> str:
        return str(self._request(self._at(at, "formula", cell=cell.address)) or "")

    def shown(self, at: Location, cell: CellReference) -> str:
        return str(self._request(self._at(at, "shown", cell=cell.address)) or "")

    def set_formula(self, at: Location, cell: CellReference, formula: str) -> None:
        self._request(self._at(at, "set_formula", cell=cell.address, formula=calc_formula(formula)))

    def restore(self, at: Location, cell: CellReference, content: str) -> None:
        """Puts back what `formula` read, which is already in Calc's own syntax."""
        self._request(self._at(at, "set_formula", cell=cell.address, formula=content))

    def set_value(self, at: Location, cell: CellReference, value: SpreadsheetValue) -> None:
        if isinstance(value, SpreadsheetNumber):
            self._request(self._at(at, "set_number", cell=cell.address, value=value.value))
        else:
            self._request(self._at(at, "set_text", cell=cell.address, text=value.value))

    def clear(self, at: Location, cell: CellReference) -> None:
        self._request(self._at(at, "clear", cell=cell.address))

    def copy(self, at: Location, source: CellReference, destination: CellReference) -> None:
        self._request(self._at(at, "copy", source=source.address, destination=destination.address))

    def values(self, at: Location, reference: str) -> list[str]:
        return [str(v) for v in self._request(self._at(at, "values", range=reference, limit=MAX_CELLS)) or []]

    @staticmethod
    def _at(at: Location, operation: str, **details: Any) -> dict[str, Any]:
        return {"op": operation, "document": at.document, "sheet": at.sheet, **details}

    # The helper process

    def _request(self, payload: dict[str, Any]) -> Any:
        with self._lock:
            if not self.is_running():
                raise CalcError("not_running")
            try:
                answer = self._connected_exchange(payload)
            except (DesktopError, OSError) as error:
                self._stop()
                raise CalcError("failed", str(error)) from error
            if "error" in answer:
                raise CalcError(answer["error"], str(answer.get("detail", "")))
            return answer.get("ok")

    def _connected_exchange(self, payload: dict[str, Any]) -> dict[str, Any]:
        answer: dict[str, Any] = {}
        for attempt in range(CONNECT_ATTEMPTS):
            answer = self._exchange(payload)
            if answer.get("error") != "not_connected":
                return answer
            if attempt == 0:
                self._listen()
            time.sleep(CONNECT_PAUSE_SECONDS)
        return answer

    def _listen(self) -> None:
        """Asks the running LibreOffice to accept Bilge's pipe."""
        program = next((p for p in ("soffice", "libreoffice") if self._runner.has(p)), None)
        if program is None:
            raise CalcError("not_connected", "soffice is not on PATH")
        self._runner.run([program, f"--accept=pipe,name={self.pipe};urp;", "--nologo", "--norestore"], timeout=20)
        self._accepting = True

    def _exchange(self, payload: dict[str, Any]) -> dict[str, Any]:
        process = self._ensure_process()
        try:
            process.stdin.write(json.dumps(payload) + "\n")
            process.stdin.flush()
            line = self._answers.get(timeout=ANSWER_SECONDS)
        except (OSError, queue.Empty) as error:
            self._stop()
            raise CalcError("failed", "the helper stopped answering") from error
        if line is None:
            self._stop()
            raise CalcError("failed", "the helper exited")
        try:
            return json.loads(line)
        except ValueError as error:
            # Answers are matched to requests by order; after a stray line the next answer would be the wrong one.
            self._stop()
            raise CalcError("failed", "unreadable answer") from error

    def _ensure_process(self) -> subprocess.Popen:
        if self._process is not None and self._process.poll() is None:
            return self._process
        python = self._find_python()
        self._answers = queue.Queue()
        self._process = subprocess.Popen(
            [python, str(_SERVER), self.pipe], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )  # fmt: skip
        threading.Thread(target=self._read, args=(self._process, self._answers), daemon=True).start()
        return self._process

    @staticmethod
    def _read(process: subprocess.Popen, answers: "queue.Queue[str | None]") -> None:
        for line in process.stdout:
            answers.put(line)
        answers.put(None)

    def _find_python(self) -> str:
        if self._python:
            return self._python
        for candidate in self._candidates if self._candidates is not None else uno_python_candidates():
            if not Path(candidate).exists():
                continue
            done = self._runner.run([candidate, "-c", "import uno"], timeout=15)
            if done.ok:
                self._python = candidate
                return candidate
        raise CalcError("no_uno")

    def _stop(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        process.kill()
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                with contextlib.suppress(OSError):
                    stream.close()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(5)

    def close(self) -> None:
        with self._lock:
            self._stop()
            if self._accepting and self.is_running():
                program = next((p for p in ("soffice", "libreoffice") if self._runner.has(p)), None)
                if program is not None:
                    with contextlib.suppress(DesktopError):
                        self._runner.run([program, f"--unaccept=pipe,name={self.pipe};urp;"], timeout=20)
            self._accepting = False
