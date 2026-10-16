"""Whisper on a graphics card of any make, through whisper.cpp's server built with Vulkan.

The server is a helper program that Bilge starts on this computer's loopback address only, with the model loaded
once; each recording is posted to it. It is tied to Bilge so that it ends with it, and one left over from a crash is
ended at the next start.
"""

import collections
import contextlib
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import numpy as np
import psutil

from bilge.core.language import AssistantLanguage
from bilge.desktop.process import child_environment
from bilge.voice.gpu import Gpu
from bilge.voice.recognizers import RecognitionError, wav_bytes

log = logging.getLogger(__name__)

PROGRAM = "whisper-server.exe" if sys.platform == "win32" else "whisper-server"
HOST = "127.0.0.1"
# Loading a large model onto a card, or compiling its shaders the first time, can take a while.
STARTUP_SECONDS = 180
REQUEST_SECONDS = 60
START_ATTEMPTS = 3
POLL_SECONDS = 0.25
STOP_SECONDS = 3
LOG_LINES = 40
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# What whisper.cpp writes once it has picked where the model runs.
_ON_CARD = "whisper_backend_init_gpu: using"
_NO_CARD = "whisper_backend_init_gpu: no GPU found"


class WhisperServerError(Exception):
    pass


def server_program() -> Path | None:
    """The packaged apps carry a Vulkan build; elsewhere one can be named in BILGE_WHISPER_SERVER or be on PATH."""
    configured = os.environ.get("BILGE_WHISPER_SERVER")
    if configured:
        return Path(configured) if Path(configured).is_file() else None
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        packaged = Path(bundle) / "whisper" / PROGRAM
        return packaged if packaged.is_file() else None
    found = shutil.which(PROGRAM)
    return Path(found) if found else None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((HOST, 0))
        return probe.getsockname()[1]


def end_leftover(pid_file: Path, program: Path) -> None:
    """A server left running by a Bilge that crashed still holds the card's memory."""
    try:
        pid = int(pid_file.read_text().strip())
    except (OSError, ValueError):
        return
    try:
        process = psutil.Process(pid)
        if Path(process.exe()).resolve() == program.resolve():
            log.info("Ending a whisper.cpp server left running (%s)", pid)
            process.kill()
    except (psutil.Error, OSError):
        pass
    with contextlib.suppress(OSError):
        pid_file.unlink()


class WhisperServer:
    def __init__(
        self,
        program: Path,
        model: Path,
        language: AssistantLanguage,
        gpu: Gpu | None,
        hint: str = "",
        pid_file: Path | None = None,
        client: httpx.Client | None = None,
    ):
        self.program = program
        self.model = model
        self.language = language
        self.gpu = gpu
        self.hint = hint
        self.pid_file = pid_file
        self._client = client or httpx.Client(timeout=httpx.Timeout(REQUEST_SECONDS, connect=5.0))
        self._process: subprocess.Popen | None = None
        self._job = None
        self._url = ""
        self._log: collections.deque[str] = collections.deque(maxlen=LOG_LINES)
        self.on_card = False

    def start(self) -> None:
        if self.pid_file is not None:
            end_leftover(self.pid_file, self.program)
        for attempt in range(1, START_ATTEMPTS + 1):
            try:
                self._start_once()
                return
            except WhisperServerError:
                self._stop()
                # Another program may have taken the free port before the server did.
                if attempt == START_ATTEMPTS or "bind" not in self.tail().lower():
                    raise

    def _start_once(self) -> None:
        port = _free_port()
        self._url = f"http://{HOST}:{port}"
        threads = str(min(8, os.cpu_count() or 4))
        argv = [str(self.program), "--model", str(self.model), "--host", HOST, "--port", str(port), "--language",
                self.language.code, "--threads", threads, "--beam-size", "5", "--no-timestamps", "--suppress-nst"]  # fmt: skip
        extra = {"GGML_VK_VISIBLE_DEVICES": str(self.gpu.index)} if self.gpu is not None else {}
        self._log.clear()
        self.on_card = False
        try:
            self._process = subprocess.Popen(
                argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=child_environment(extra), creationflags=_NO_WINDOW,
            )  # fmt: skip
        except OSError as error:
            raise WhisperServerError(f"whisper.cpp could not start: {error}") from error
        self._tie(self._process)
        threading.Thread(target=self._read_output, args=(self._process,), name="bilge-whisper-log", daemon=True).start()
        self._wait_until_ready()
        if self.gpu is not None and not self.on_card:
            raise WhisperServerError(f"whisper.cpp did not use {self.gpu.name}: {self.tail()}")
        log.info("whisper.cpp is ready on %s", self.gpu.name if self.gpu is not None else "the processor")

    def _tie(self, process: subprocess.Popen) -> None:
        if self.pid_file is not None:
            with contextlib.suppress(OSError):
                self.pid_file.parent.mkdir(parents=True, exist_ok=True)
                self.pid_file.write_text(str(process.pid))
        if sys.platform == "win32":
            from bilge.desktop.windows.jobs import Job

            try:
                self._job = Job()
                self._job.add(int(process._handle))  # type: ignore[attr-defined]
            except OSError:
                log.info("whisper.cpp is not tied to Bilge; it is still ended when Bilge stops", exc_info=True)

    def _read_output(self, process: subprocess.Popen) -> None:
        assert process.stdout is not None
        for raw in process.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            self._log.append(line)
            if line.startswith(_ON_CARD):
                self.on_card = True
            log.debug("whisper.cpp: %s", line)

    def _wait_until_ready(self) -> None:
        deadline = time.monotonic() + STARTUP_SECONDS
        while time.monotonic() < deadline:
            process = self._process
            if process is None or process.poll() is not None:
                raise WhisperServerError(f"whisper.cpp stopped while starting: {self.tail()}")
            with contextlib.suppress(httpx.HTTPError):
                if self._client.get(f"{self._url}/health", timeout=2.0).status_code == 200:
                    # The log line about the card comes before the server answers; give the reader a moment.
                    time.sleep(POLL_SECONDS)
                    return
            time.sleep(POLL_SECONDS)
        raise WhisperServerError(f"whisper.cpp did not start in {STARTUP_SECONDS} s: {self.tail()}")

    def tail(self) -> str:
        return " | ".join(list(self._log)[-6:])

    def transcribe(self, samples: np.ndarray) -> str:
        process = self._process
        if process is None or process.poll() is not None:
            raise RecognitionError(f"whisper.cpp is not running: {self.tail()}")
        files = {"file": ("speech.wav", wav_bytes(samples), "audio/wav")}
        data = {"response_format": "json", "language": self.language.code, "temperature": "0.0"}
        if self.hint:
            data["prompt"] = self.hint
        try:
            response = self._client.post(f"{self._url}/inference", files=files, data=data)
        except httpx.HTTPError as error:
            raise RecognitionError(f"whisper.cpp did not answer: {error}") from error
        if response.status_code >= 400:
            raise RecognitionError(f"whisper.cpp failed ({response.status_code}): {response.text[:200]}")
        try:
            return str(response.json().get("text", "")).strip()
        except (ValueError, AttributeError) as error:
            raise RecognitionError("Unexpected answer from whisper.cpp") from error

    def close(self) -> None:
        """Ends the server for good; a server is not started again after this."""
        self._stop()
        self._client.close()

    def _stop(self) -> None:
        process, self._process = self._process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=STOP_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=STOP_SECONDS)
        if process is not None and process.stdout is not None:
            # The output reader ends at the pipe's end; closing it here doesn't wait for that.
            with contextlib.suppress(OSError):
                process.stdout.close()
        if self._job is not None:
            self._job.close()
            self._job = None
        if self.pid_file is not None:
            with contextlib.suppress(OSError):
                self.pid_file.unlink()
