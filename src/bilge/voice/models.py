"""The voice models Bilge downloads, each pinned to a reviewed commit and checked file by file."""

from bilge.models.downloader import ModelSpec
from bilge.voice.supertonic import MODEL as SUPERTONIC

# Whisper large-v3-turbo converted for CTranslate2 (MIT); what faster-whisper fetches for "large-v3-turbo".
WHISPER_TURBO = ModelSpec(
    repo_id="mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    revision="0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf",
    patterns=("model.bin", "config.json", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"),
    name="whisper-large-v3-turbo",
)

# Whisper base (MIT), only for spotting the wake word and cut-ins: about 0.1 s on a CPU, where the large model
# takes over 2 s because Whisper always encodes 30 s of audio.
WHISPER_BASE = ModelSpec(
    repo_id="Systran/faster-whisper-base",
    revision="ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66",
    patterns=("model.bin", "config.json", "tokenizer.json", "vocabulary.*"),
    name="whisper-base",
)

# CAM++ speaker embeddings (3D-Speaker, Apache-2.0): the same weights Bilge for macOS runs through CoreML.
CAMPLUS = ModelSpec(
    repo_id="csukuangfj/speaker-embedding-models",
    revision="0743f301363dec56491a490f6d6cbc9d67f9a3bf",
    patterns=("3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx",),
    name="campplus",
)
CAMPLUS_FILE = "3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx"


# The same Whisper turbo in whisper.cpp's format (MIT), for graphics cards; 8-bit, half the size of the full one.
WHISPER_TURBO_GGML = ModelSpec(
    repo_id="ggerganov/whisper.cpp",
    revision="5359861c739e955e79d9a303bcbc70fb988958b1",
    patterns=("ggml-large-v3-turbo-q8_0.bin",),
    name="whisper-large-v3-turbo-ggml",
)
WHISPER_TURBO_GGML_FILE = "ggml-large-v3-turbo-q8_0.bin"

ALL = (SUPERTONIC, WHISPER_TURBO, WHISPER_TURBO_GGML, WHISPER_BASE, CAMPLUS)
