"""Microphone and speaker as one full-duplex stream, so every microphone block arrives together with what
the speaker was playing at that moment: the reference echo cancellation needs."""

import logging
import queue
import threading
from collections import deque
from collections.abc import Callable
from typing import Protocol

import numpy as np
import soxr

from bilge.voice.echo import EchoCanceller

log = logging.getLogger(__name__)
SAMPLE_RATE = 16_000
CHUNK = 512

BlockHandler = Callable[[np.ndarray, np.ndarray], None]


class AudioDevice(Protocol):
    sample_rate: int

    def start(self, on_block: BlockHandler) -> None:
        """Calls `on_block(microphone, played)` for every block, both mono float32 at `sample_rate`."""
        ...

    def stop(self) -> None: ...

    def play(self, samples: np.ndarray) -> None:
        """Queues mono float32 at `sample_rate` after whatever is already playing."""
        ...

    def clear(self) -> None:
        """Stops playback at once and drops what was queued."""
        ...

    @property
    def is_playing(self) -> bool: ...


class PlaybackBuffer:
    """Shared by the audio callback and the speech thread; the callback must never wait for long."""

    def __init__(self) -> None:
        self._clips: deque[np.ndarray] = deque()
        self._lock = threading.Lock()

    def add(self, samples: np.ndarray) -> None:
        with self._lock:
            self._clips.append(samples.astype(np.float32, copy=False))

    def clear(self) -> None:
        with self._lock:
            self._clips.clear()

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return bool(self._clips)

    def take(self, count: int) -> np.ndarray:
        out = np.zeros(count, dtype=np.float32)
        filled = 0
        with self._lock:
            while filled < count and self._clips:
                clip = self._clips[0]
                n = min(count - filled, len(clip))
                out[filled : filled + n] = clip[:n]
                filled += n
                if n == len(clip):
                    self._clips.popleft()
                else:
                    self._clips[0] = clip[n:]
        return out


class SoundDevice:
    """The computer's microphone and speaker through PortAudio (WASAPI on Windows, PipeWire/PulseAudio on Linux)."""

    def __init__(self, input_device: int | str | None = None, output_device: int | str | None = None):
        import sounddevice as sd

        self._sd = sd
        self._devices = choose_devices(sd, input_device, output_device)
        self.sample_rate = int(sd.query_devices(self._devices[1])["default_samplerate"])
        self._buffer = PlaybackBuffer()
        self._stream = None

    def start(self, on_block: BlockHandler) -> None:
        sd = self._sd
        extra = None
        if all(_host_api_name(sd, device) == WASAPI for device in self._devices):
            # Lets Windows convert the rate when the microphone and the speaker run at different ones.
            extra = (sd.WasapiSettings(auto_convert=True), sd.WasapiSettings(auto_convert=True))

        def callback(indata, outdata, frames, time, status):
            if status:
                log.debug("Audio status: %s", status)
            played = self._buffer.take(frames)
            outdata[:] = played[:, None]
            on_block(indata.mean(axis=1).astype(np.float32), played)

        self._stream = sd.Stream(
            samplerate=self.sample_rate, channels=(1, 1), dtype="float32", device=self._devices,
            callback=callback, latency="low", extra_settings=extra,
        )  # fmt: skip
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._buffer.clear()

    def play(self, samples: np.ndarray) -> None:
        self._buffer.add(samples)

    def clear(self) -> None:
        self._buffer.clear()

    @property
    def is_playing(self) -> bool:
        return self._buffer.is_playing


WASAPI = "Windows WASAPI"


def _host_api_name(sd, device: int) -> str:
    return sd.query_hostapis(sd.query_devices(device)["hostapi"])["name"]


def choose_devices(sd, input_device: int | str | None, output_device: int | str | None) -> tuple[int, int]:
    """The devices the user picked, else the system defaults. On Windows the defaults are taken from WASAPI:
    PortAudio's own default is the old MME interface, which adds latency and can't share a stream's settings."""
    default_input, default_output = sd.default.device
    for api in sd.query_hostapis():
        if api["name"] == WASAPI and api["default_input_device"] >= 0 and api["default_output_device"] >= 0:
            default_input, default_output = api["default_input_device"], api["default_output_device"]

    def resolve(device: int | str | None, default: int, kind: str) -> int:
        if device is None or device == "":
            return default
        return int(sd.query_devices(device, kind)["index"])

    return resolve(input_device, default_input, "input"), resolve(output_device, default_output, "output")


ChunkHandler = Callable[[np.ndarray], None]


class FrontEnd:
    """Turns device blocks into echo-cancelled 16 kHz chunks of 512 samples, off the audio callback's thread."""

    def __init__(self, device: AudioDevice, on_chunk: ChunkHandler, echo: EchoCanceller | None = None):
        self.device = device
        self._on_chunk = on_chunk
        self._echo = echo
        self._blocks: queue.Queue[tuple[np.ndarray, np.ndarray] | None] = queue.Queue(maxsize=400)
        self._mic_resampler = soxr.ResampleStream(device.sample_rate, SAMPLE_RATE, 1, dtype="float32")
        self._ref_resampler = soxr.ResampleStream(device.sample_rate, SAMPLE_RATE, 1, dtype="float32")
        self._pending = np.zeros(0, dtype=np.float32)
        self._thread = threading.Thread(target=self._run, name="bilge-audio", daemon=True)

    def start(self) -> None:
        self._thread.start()
        self.device.start(self._receive)

    def stop(self) -> None:
        self.device.stop()
        self._blocks.put(None)
        self._thread.join(timeout=2)

    def _receive(self, microphone: np.ndarray, played: np.ndarray) -> None:
        try:
            self._blocks.put_nowait((microphone, played))
        except queue.Full:
            log.warning("Audio processing fell behind; dropping a block")

    def _run(self) -> None:
        while (item := self._blocks.get()) is not None:
            microphone, played = item
            mic = self._mic_resampler.resample_chunk(microphone)
            ref = self._ref_resampler.resample_chunk(played)
            cleaned = self._echo.process(mic, ref) if self._echo else mic
            self._pending = np.concatenate([self._pending, cleaned])
            while len(self._pending) >= CHUNK:
                chunk, self._pending = self._pending[:CHUNK], self._pending[CHUNK:]
                try:
                    self._on_chunk(chunk)
                except Exception:
                    log.exception("Audio chunk handler failed")


class SimulatedDevice:
    """A stand-in for tests and benchmarks: plays scripted speech into the "microphone" and mixes what Bilge
    says back in as room echo. Runs faster than real time when `speed` > 1."""

    def __init__(self, sample_rate: int = 48_000, echo_gain: float = 0.4, echo_delay: float = 0.05, block: int = 480):
        self.sample_rate = sample_rate
        self._echo_gain = echo_gain
        self._delay_line = np.zeros(int(echo_delay * sample_rate), dtype=np.float32)
        self._block = block
        self._buffer = PlaybackBuffer()
        self._script: deque[np.ndarray] = deque()
        self._script_lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self.played_seconds = 0.0

    def say(self, samples: np.ndarray) -> None:
        """Queues speech at `sample_rate` for the microphone to hear."""
        with self._script_lock:
            self._script.append(samples.astype(np.float32))

    @property
    def script_done(self) -> bool:
        with self._script_lock:
            return not self._script

    def start(self, on_block: BlockHandler) -> None:
        self._running = True

        def run() -> None:
            import time

            period = self._block / self.sample_rate
            next_time = time.monotonic()
            while self._running:
                played = self._buffer.take(self._block)
                self.played_seconds += np.count_nonzero(played) / self.sample_rate
                line = np.concatenate([self._delay_line, played])
                echo, self._delay_line = line[: self._block], line[self._block :]
                on_block(self._next_speech() + echo * self._echo_gain, played)
                next_time += period
                time.sleep(max(0.0, next_time - time.monotonic()))

        self._thread = threading.Thread(target=run, name="bilge-simulated-audio", daemon=True)
        self._thread.start()

    def _next_speech(self) -> np.ndarray:
        out = np.zeros(self._block, dtype=np.float32)
        filled = 0
        with self._script_lock:
            while filled < self._block and self._script:
                clip = self._script[0]
                n = min(self._block - filled, len(clip))
                out[filled : filled + n] = clip[:n]
                filled += n
                if n == len(clip):
                    self._script.popleft()
                else:
                    self._script[0] = clip[n:]
        return out

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def play(self, samples: np.ndarray) -> None:
        self._buffer.add(samples)

    def clear(self) -> None:
        self._buffer.clear()

    @property
    def is_playing(self) -> bool:
        return self._buffer.is_playing
