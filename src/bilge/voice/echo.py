"""Echo cancellation with WebRTC's audio processing (through the livekit package), so the microphone can
hear the user over Bilge's own voice and they can cut in ("Bilge, dur")."""

import numpy as np
from livekit import rtc

SAMPLE_RATE = 16_000
# WebRTC processes exactly 10 ms at a time.
FRAME = SAMPLE_RATE // 100


class EchoCanceller:
    def __init__(self, delay_ms: int = 0):
        self._delay_ms = delay_ms
        self.reset()

    def reset(self) -> None:
        self._apm = rtc.AudioProcessingModule(
            # Noise suppression is left off: it bent the user's words over Bilge's voice ("saat kaç" → "satkaç").
            echo_cancellation=True,
            noise_suppression=False,
            high_pass_filter=True,
            auto_gain_control=False,
        )
        self._mic_rest = np.zeros(0, dtype=np.float32)
        self._reference_rest = np.zeros(0, dtype=np.float32)

    def process(self, mic: np.ndarray, reference: np.ndarray) -> np.ndarray:
        """`mic` and `reference` are 16 kHz float32 covering the same moment; returns cleaned microphone audio
        (possibly a few samples shorter or longer than given, as frames complete)."""
        mic = np.concatenate([self._mic_rest, mic.astype(np.float32, copy=False)])
        reference = np.concatenate([self._reference_rest, reference.astype(np.float32, copy=False)])
        usable = min(len(mic), len(reference)) // FRAME * FRAME
        cleaned = np.empty(usable, dtype=np.float32)
        for start in range(0, usable, FRAME):
            far = rtc.AudioFrame(_pcm(reference[start : start + FRAME]), SAMPLE_RATE, 1, FRAME)
            self._apm.process_reverse_stream(far)
            self._apm.set_stream_delay_ms(self._delay_ms)
            near = rtc.AudioFrame(_pcm(mic[start : start + FRAME]), SAMPLE_RATE, 1, FRAME)
            self._apm.process_stream(near)
            cleaned[start : start + FRAME] = np.frombuffer(near.data, dtype=np.int16) / 32768.0
        self._mic_rest = mic[usable:]
        self._reference_rest = reference[usable:]
        return cleaned


def _pcm(samples: np.ndarray) -> bytes:
    return (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
