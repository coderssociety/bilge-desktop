"""Sentences Whisper makes up when it hears no words (silence, breathing, a fan, music). They come from the subtitles
it was trained on, so they are the closing lines of videos: nobody says them to an assistant.

Only whole sentences are dropped, and only these; "teşekkürler" and "thank you" stay, since people do say those.
"""

import re

from bilge.core.text import folded

# Folded (lowercase, no Turkish letters, no punctuation) whole sentences.
_SENTENCES = frozenset({
    "altyazi m k", "alt yazi m k", "altyazi mk", "altyazilar m k",
    "izlediginiz icin tesekkur ederim", "izlediginiz icin tesekkurler", "izlediginiz icin tesekkur ederiz",
    "abone olmayi unutmayin", "kanalima abone olmayi unutmayin", "begenmeyi ve abone olmayi unutmayin",
    "videoyu begenmeyi ve abone olmayi unutmayin", "bir sonraki videoda gorusmek uzere",
    "bir sonraki videoda gorusuruz", "altyazilar amara org toplulugu tarafindan saglanmistir",
    "thanks for watching", "thank you for watching", "thanks for watching and see you next time",
    "thank you so much for watching", "please subscribe", "please like and subscribe",
    "don t forget to like and subscribe", "see you in the next video", "see you next time",
    "subtitles by the amara org community", "you",
})  # fmt: skip
# Credit lines with a name after them ("Subtitles by …", "Altyazı: …"). The Turkish ones need the colon: "altyazı
# aç" is a request.
_PREFIXES = ("subtitles by ", "subtitled by ", "transcription by ", "transcribed by ", "translated by ",
             "captions by ")  # fmt: skip
_TURKISH_CREDIT = re.compile(r"^\s*(alt ?yazı(lar)?|çeviri|çeviren)\s*:", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def is_made_up(sentence: str) -> bool:
    key = folded(sentence)
    return (key in _SENTENCES or key.startswith(_PREFIXES) or "amara org" in key
            or _TURKISH_CREDIT.match(sentence.replace("İ", "i").replace("I", "ı")) is not None)  # fmt: skip


def without_made_up(transcript: str) -> str:
    """The transcript without the sentences Whisper invents; empty when nothing else was heard."""
    kept = [sentence for sentence in _SENTENCE_END.split(transcript.strip()) if sentence and not is_made_up(sentence)]
    return " ".join(kept).strip()
