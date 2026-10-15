"""Speaker check: "only answer my voice". CAM++ embeddings compared with the voice the user enrolled.

Only embeddings are stored, never recordings. If the check cannot run (model missing, an error), speech is let
through: a broken check must not lock the user out of their own assistant.
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import kaldi_native_fbank as knf
import numpy as np
import onnxruntime as ort

from bilge.core.speaker import voice_print
from bilge.core.speaker.voice_print import Decision, VoicePrint

log = logging.getLogger(__name__)
SAMPLE_RATE = 16_000
# Enrolment recordings that disagree this much were not one voice, or the room was too noisy.
MINIMUM_CONSISTENCY = 0.45


class CampPlus:
    def __init__(self, model_path: Path):
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self._session = ort.InferenceSession(str(model_path), options, providers=["CPUExecutionProvider"])

    def embedding(self, samples: np.ndarray) -> list[float]:
        features = _fbank(samples)[None, :, :].astype(np.float32)
        (embedding,) = self._session.run(["embedding"], {"x": features})
        vector = embedding[0]
        return (vector / max(float(np.linalg.norm(vector)), 1e-9)).tolist()


def _fbank(samples: np.ndarray) -> np.ndarray:
    """80 mel bins with the mean over time removed, as the model was trained (its metadata says so)."""
    options = knf.FbankOptions()
    options.frame_opts.samp_freq = SAMPLE_RATE
    options.frame_opts.dither = 0.0
    options.frame_opts.snip_edges = True
    options.mel_opts.num_bins = 80
    extractor = knf.OnlineFbank(options)
    extractor.accept_waveform(SAMPLE_RATE, samples.astype(np.float32).tolist())
    extractor.input_finished()
    features = np.stack([extractor.get_frame(i) for i in range(extractor.num_frames_ready)])
    return features - features.mean(axis=0, keepdims=True)


@dataclass(frozen=True)
class StoredVoice:
    voice_print: VoicePrint
    threshold: float
    created: str


class EnrollmentError(Exception):
    """The message is spoken to the user."""


class VoiceStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> StoredVoice | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return StoredVoice(
                VoicePrint.from_dict(data["voice_print"]), float(data["threshold"]), str(data["created"])
            )
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError):
            log.exception("The stored voice could not be read; the speaker check stays off")
            return None

    def enroll(self, embeddings: list[list[float]]) -> StoredVoice:
        created = VoicePrint.create(embeddings)
        if created is None:
            raise EnrollmentError(f"At least {voice_print.MINIMUM_RECORDINGS} recordings are needed.")
        if created.consistency < MINIMUM_CONSISTENCY:
            raise EnrollmentError("The recordings don't sound like one voice; try again somewhere quieter.")
        stored = StoredVoice(created, created.suggested_threshold, datetime.now().isoformat(timespec="seconds"))
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(
                {"voice_print": created.to_dict(), "threshold": stored.threshold, "created": stored.created}, file
            )
        temporary.replace(self.path)
        return stored

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)


class SpeakerGate:
    def __init__(self, store: VoiceStore, model: CampPlus | None, enabled: bool):
        self._voice = store.load() if enabled else None
        self._model = model

    @property
    def is_active(self) -> bool:
        return self._voice is not None and self._model is not None

    def check(self, samples: np.ndarray) -> Decision:
        if not self.is_active:
            return Decision.ACCEPTED
        seconds = len(samples) / SAMPLE_RATE
        if seconds < voice_print.MINIMUM_SECONDS:
            return Decision.TOO_SHORT
        try:
            score = self._voice.voice_print.score(self._model.embedding(samples))
        except Exception:
            log.exception("Speaker check failed; letting the speech through")
            return Decision.ACCEPTED
        log.info("Speaker score %.2f (threshold %.2f)", score, self._voice.threshold)
        return voice_print.decide(score, seconds, self._voice.threshold)
