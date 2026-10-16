"""Speech to text: Whisper on this computer, or a hosted transcription API."""

import ctypes
import io
import logging
import os
import sys
import wave
from typing import Protocol

import httpx
import numpy as np

from bilge.core.audio import loudness
from bilge.core.language import AssistantLanguage
from bilge.core.speech import hallucinations

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
# CTranslate2 4.5 and later run on CUDA 12 with cuDNN 9; NVIDIA's driver doesn't bring them. Without them it fails
# only once it first transcribes, and on Windows it then takes the whole process down, so they are looked for first.
_CUDA_LIBRARIES = {
    "win32": ("cublas64_12.dll", "cudnn64_9.dll"),
    "linux": ("libcublas.so.12", "libcudnn.so.9"),
}


class RecognitionError(Exception):
    pass


class Recognizer(Protocol):
    def transcribe(self, samples: np.ndarray) -> str:
        """16 kHz mono float32 in [-1, 1]."""
        ...


class WhisperRecognizer:
    """faster-whisper on the CPU (int8) or an NVIDIA card (float16)."""

    def __init__(self, model_dir: str, language: AssistantLanguage, device: str = "cpu", hint: str = ""):
        from faster_whisper import WhisperModel

        threads = min(8, os.cpu_count() or 4)
        use_cuda = device == "cuda"
        self._model = WhisperModel(
            model_dir,
            device="cuda" if use_cuda else "cpu",
            compute_type="float16" if use_cuda else "int8",
            cpu_threads=threads,
        )
        self._language = language.code
        # Names the model should expect ("Bilge"), so it spells them right instead of guessing.
        self._hint = hint or None

    def transcribe(self, samples: np.ndarray) -> str:
        segments, _ = self._model.transcribe(
            samples.astype(np.float32, copy=False),
            language=self._language,
            beam_size=5,
            condition_on_previous_text=False,
            without_timestamps=True,
            initial_prompt=self._hint,
            vad_filter=False,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()


def has_cuda() -> bool:
    """An NVIDIA card, and the CUDA libraries faster-whisper needs to use it."""
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() == 0:
            return False
    except Exception:  # A broken CUDA install must not stop the CPU path.
        return False
    loader = ctypes.WinDLL if sys.platform == "win32" else ctypes.CDLL
    for name in _CUDA_LIBRARIES.get(sys.platform, ()):
        try:
            loader(name)
        except OSError:
            log.info("An NVIDIA card is there, but %s is missing; Whisper runs elsewhere", name)
            return False
    return sys.platform in _CUDA_LIBRARIES


class APIRecognizer:
    """OpenAI-compatible `/audio/transcriptions` (OpenAI, Groq). The recording leaves the computer."""

    def __init__(
        self, base_url: str, api_key: str, model: str, language: AssistantLanguage, client: httpx.Client | None = None
    ):
        self._url = base_url.rstrip("/") + "/audio/transcriptions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._model = model
        self._language = language.code
        self._client = client or httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))

    def transcribe(self, samples: np.ndarray) -> str:
        files = {"file": ("speech.wav", wav_bytes(samples), "audio/wav")}
        data = {"model": self._model, "language": self._language, "response_format": "json"}
        try:
            response = self._client.post(self._url, headers=self._headers, files=files, data=data)
        except httpx.HTTPError as error:
            raise RecognitionError(f"Could not reach the transcription service: {error}") from error
        if response.status_code >= 400:
            raise RecognitionError(f"Transcription failed ({response.status_code})")
        try:
            return str(response.json().get("text", "")).strip()
        except (ValueError, AttributeError) as error:
            raise RecognitionError("Unexpected transcription answer") from error


class GuardedRecognizer:
    """Keeps Whisper from answering noise: a recording with nothing standing out from its own background is not
    transcribed at all, and the closing lines of videos Whisper invents for near-silence are taken out of what comes
    back."""

    def __init__(self, inner: Recognizer):
        self.inner = inner

    def transcribe(self, samples: np.ndarray) -> str:
        if not loudness.holds_speech(frame_levels(samples)):
            log.debug("Not transcribed: nothing louder than the background")
            return ""
        return hallucinations.without_made_up(self.inner.transcribe(samples))

    def close(self) -> None:
        close = getattr(self.inner, "close", None)
        if close is not None:
            close()


def frame_levels(samples: np.ndarray) -> list[float]:
    size = int(SAMPLE_RATE * loudness.FRAME_SECONDS)
    count = len(samples) // size
    if count == 0:
        return []
    frames = samples[: count * size].astype(np.float64).reshape(count, size)
    return [loudness.level_of_power(float(power)) for power in np.mean(frames * frames, axis=1)]


def wav_bytes(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(pcm.tobytes())
    return buffer.getvalue()


TRANSCRIPTION_PRESETS = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini-transcribe"),
    # Groq bills at least 10 seconds per request, which adds up with short commands.
    "groq": ("https://api.groq.com/openai/v1", "whisper-large-v3-turbo"),
}
