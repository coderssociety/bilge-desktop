"""Supertonic-3 speech synthesis with onnxruntime: the same voice as Bilge for macOS.

Adapted from Supertone's reference code (supertone-inc/supertonic, py/helper.py, MIT License,
Copyright (c) Supertone Inc.). The model weights are under the BigScience OpenRAIL-M license.
"""

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime as ort

from bilge.core.language import AssistantLanguage
from bilge.models.downloader import ModelSpec

MODEL = ModelSpec(
    repo_id="Supertone/supertonic-3",
    revision="3cadd1ee6394adea1bd021217a0e650ede09a323",
    patterns=("onnx/*", "voice_styles/*.json", "LICENSE"),
    name="supertonic-3",
)
VOICES = tuple(f"{kind}{n}" for kind in "FM" for n in range(1, 6))
DEFAULT_STEPS = 8
DEFAULT_SPEED = 1.05
# Four threads measured fastest on an 18-core Mac; more only adds overhead for this model's small graphs.
THREADS = 4
_SILENCE_BETWEEN_CHUNKS = 0.3
_MAX_CHUNK = 300

_EMOJI = re.compile(
    "[\U0001f600-\U0001f64f\U0001f300-\U0001f5ff\U0001f680-\U0001f6ff\U0001f700-\U0001f77f"
    "\U0001f780-\U0001f7ff\U0001f800-\U0001f8ff\U0001f900-\U0001f9ff\U0001fa00-\U0001fa6f"
    "\U0001fa70-\U0001faff☀-⛿✀-➿\U0001f1e6-\U0001f1ff]+"
)
_CHARACTERS = str.maketrans(
    {"–": "-", "‑": "-", "—": "-", "_": " ", "“": '"', "”": '"', "‘": "'", "’": "'", "´": "'", "`": "'",
     "[": " ", "]": " ", "|": " ", "/": " ", "#": " ", "→": " ", "←": " ", "♥": None, "☆": None, "♡": None,
     "©": None, "\\": None}
)  # fmt: skip
_EXPRESSIONS = {"@": " at ", "e.g.,": "for example, ", "i.e.,": "that is, "}
_ENDS_WITH_PUNCTUATION = re.compile(r"[.!?;:,'\"')\]}…。」』】〉》›»]$")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def preprocess(text: str, language: AssistantLanguage) -> str:
    """The model was trained on NFKD text wrapped in a language tag; Turkish letters split into base + mark."""
    text = _EMOJI.sub("", unicodedata.normalize("NFKD", text)).translate(_CHARACTERS)
    for old, new in _EXPRESSIONS.items():
        text = text.replace(old, new)
    text = re.sub(r" ([,.!?;:'])", r"\1", text)
    for double, single in (('""', '"'), ("''", "'")):
        while double in text:
            text = text.replace(double, single)
    text = re.sub(r"\s+", " ", text).strip()
    if not _ENDS_WITH_PUNCTUATION.search(text):
        text += "."
    return f"<{language.code}>{text}</{language.code}>"


def chunks(text: str, max_length: int = _MAX_CHUNK) -> list[str]:
    """Bilge already speaks sentence by sentence; this only splits an unusually long sentence group."""
    out: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(text.strip()):
        if current and len(current) + len(sentence) + 1 > max_length:
            out.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
    if current:
        out.append(current)
    return out


@dataclass(frozen=True)
class VoiceStyle:
    ttl: np.ndarray  # [1, 50, 256]
    dp: np.ndarray  # [1, 8, 16]

    @classmethod
    def load(cls, path: Path) -> "VoiceStyle":
        raw = json.loads(path.read_text(encoding="utf-8"))

        def tensor(key: str) -> np.ndarray:
            return np.asarray(raw[key]["data"], dtype=np.float32).reshape(raw[key]["dims"])

        return cls(ttl=tensor("style_ttl"), dp=tensor("style_dp"))


class Supertonic:
    def __init__(self, model_dir: Path, steps: int = DEFAULT_STEPS, speed: float = DEFAULT_SPEED):
        onnx = model_dir / "onnx"
        config = json.loads((onnx / "tts.json").read_text(encoding="utf-8"))
        self.sample_rate: int = config["ae"]["sample_rate"]
        self._latent_chunk = config["ae"]["base_chunk_size"] * config["ttl"]["chunk_compress_factor"]
        self._latent_dim = config["ttl"]["latent_dim"] * config["ttl"]["chunk_compress_factor"]
        self._indexer = np.asarray(
            json.loads((onnx / "unicode_indexer.json").read_text(encoding="utf-8")), dtype=np.int64
        )
        self._voices_dir = model_dir / "voice_styles"
        self._styles: dict[str, VoiceStyle] = {}
        self.steps = steps
        self.speed = speed
        options = ort.SessionOptions()
        options.intra_op_num_threads = THREADS

        def session(name: str) -> ort.InferenceSession:
            return ort.InferenceSession(str(onnx / f"{name}.onnx"), options, providers=["CPUExecutionProvider"])

        self._duration = session("duration_predictor")
        self._encoder = session("text_encoder")
        self._estimator = session("vector_estimator")
        self._vocoder = session("vocoder")

    def style(self, voice: str) -> VoiceStyle:
        if voice not in VOICES:
            raise ValueError(f"Unknown voice: {voice}")
        if voice not in self._styles:
            self._styles[voice] = VoiceStyle.load(self._voices_dir / f"{voice}.json")
        return self._styles[voice]

    def synthesize(self, text: str, language: AssistantLanguage, voice: str, seed: int | None = None) -> np.ndarray:
        """Mono float32 samples at `sample_rate`; empty for text with nothing to say."""
        style = self.style(voice)
        rng = np.random.default_rng(seed)
        silence = np.zeros(int(_SILENCE_BETWEEN_CHUNKS * self.sample_rate), dtype=np.float32)
        parts: list[np.ndarray] = []
        for chunk in chunks(text):
            if parts:
                parts.append(silence)
            parts.append(self._chunk(chunk, language, style, rng))
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)

    def _chunk(self, text: str, language: AssistantLanguage, style: VoiceStyle, rng: np.random.Generator) -> np.ndarray:
        codepoints = np.frombuffer(preprocess(text, language).encode("utf-32-le"), dtype=np.uint32)
        # A character the model has no token for (outside the Basic Multilingual Plane) is left out.
        codepoints = codepoints[codepoints < len(self._indexer)]
        text_ids = self._indexer[codepoints][None, :]
        text_mask = np.ones((1, 1, text_ids.shape[1]), dtype=np.float32)
        (duration,) = self._duration.run(None, {"text_ids": text_ids, "style_dp": style.dp, "text_mask": text_mask})
        (text_emb,) = self._encoder.run(None, {"text_ids": text_ids, "style_ttl": style.ttl, "text_mask": text_mask})
        samples = int(duration[0] / self.speed * self.sample_rate)
        latent_length = max(1, -(-samples // self._latent_chunk))
        latent_mask = np.ones((1, 1, latent_length), dtype=np.float32)
        latent = rng.standard_normal((1, self._latent_dim, latent_length), dtype=np.float32)
        total = np.array([self.steps], dtype=np.float32)
        for step in range(self.steps):
            (latent,) = self._estimator.run(
                None,
                {
                    "noisy_latent": latent, "text_emb": text_emb, "style_ttl": style.ttl, "text_mask": text_mask,
                    "latent_mask": latent_mask, "current_step": np.array([step], dtype=np.float32), "total_step": total,
                },
            )  # fmt: skip
        (wav,) = self._vocoder.run(None, {"latent": latent})
        return wav[0, :samples]
