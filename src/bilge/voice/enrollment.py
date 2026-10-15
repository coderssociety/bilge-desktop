"""Teaching Bilge the owner's voice: five short sentences are recorded, and only their voice embeddings are kept,
never the recordings. Shared by `bilge enroll` and the settings window."""

from collections.abc import Callable

import numpy as np

from bilge import config
from bilge.core.language import AssistantLanguage
from bilge.voice import models
from bilge.voice.speaker import CampPlus, StoredVoice, VoiceStore

SECONDS = 3.5
SENTENCES = {
    AssistantLanguage.TURKISH: [
        "Bilge, yarın sabah saat yedide beni uyandır.",
        "Bugün hava nasıl olacak, yağmur yağacak mı?",
        "Ahmet'e akşam yemeğe geç kalacağımı yaz.",
        "Bu hafta takvimimde hangi toplantılar var?",
        "Sesi biraz kıs ve sakin bir şarkı aç.",
    ],
    AssistantLanguage.ENGLISH: [
        "Bilge, wake me up tomorrow at seven.",
        "What will the weather be like today, will it rain?",
        "Tell Ahmet I'll be late for dinner tonight.",
        "Which meetings are on my calendar this week?",
        "Turn the volume down a little and play something calm.",
    ],
}


def voice_store() -> VoiceStore:
    return VoiceStore(config.data_dir() / "voiceprint.json")


def record(input_device: int | str | None, seconds: float = SECONDS) -> np.ndarray:
    """One sentence from the microphone, as 16 kHz mono."""
    import sounddevice as sd
    import soxr

    rate = int(sd.query_devices(input_device, "input")["default_samplerate"])
    audio = sd.rec(int(seconds * rate), samplerate=rate, channels=1, dtype="float32", device=input_device)
    sd.wait()
    return soxr.resample(audio[:, 0], rate, 16_000).astype(np.float32)


def enroll(recordings: list[np.ndarray], models_dir, store: VoiceStore | None = None) -> StoredVoice:
    """Raises EnrollmentError when the recordings don't make a usable voice print."""
    model = CampPlus(models_dir / models.CAMPLUS.name / models.CAMPLUS_FILE)
    return (store or voice_store()).enroll([model.embedding(samples) for samples in recordings])


def enroll_interactively(
    language: AssistantLanguage, input_device: int | str | None, models_dir, before_each: Callable[[str], None]
) -> StoredVoice:
    """`before_each` shows a sentence and returns when the user is ready to read it."""
    recordings = []
    for sentence in SENTENCES[language]:
        before_each(sentence)
        recordings.append(record(input_device))
    return enroll(recordings, models_dir)
