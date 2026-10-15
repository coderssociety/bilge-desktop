"""Speech probability per 32 ms of 16 kHz audio, with the Silero VAD model that ships inside faster-whisper."""

import os

import numpy as np
import onnxruntime as ort
from faster_whisper.utils import get_assets_path

SAMPLE_RATE = 16_000
CHUNK = 512
_CONTEXT = 64


class SileroVAD:
    """Stateful: chunks must arrive in order. The model reads the last 64 samples of the previous chunk too."""

    def __init__(self, path: str | None = None):
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.log_severity_level = 4
        self._session = ort.InferenceSession(
            path or os.path.join(get_assets_path(), "silero_vad_v6.onnx"), options, providers=["CPUExecutionProvider"]
        )
        self.reset()

    def reset(self) -> None:
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._context = np.zeros(_CONTEXT, dtype=np.float32)

    def probability(self, chunk: np.ndarray) -> float:
        if chunk.shape != (CHUNK,):
            raise ValueError(f"Silero VAD takes {CHUNK} samples at a time")
        window = np.concatenate([self._context, chunk.astype(np.float32, copy=False)])[None, :]
        output, self._h, self._c = self._session.run(None, {"input": window, "h": self._h, "c": self._c})
        self._context = window[0, -_CONTEXT:]
        return float(output.reshape(-1)[0])
