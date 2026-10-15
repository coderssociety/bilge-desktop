"""Spoken controls inside dictation. Only whole utterances count, so a sentence that merely contains
"sil" or "satır" is typed as text."""

from enum import StrEnum

from bilge.core.language import AssistantLanguage
from bilge.core.text import folded


class DictationCommand(StrEnum):
    NEW_LINE = "newLine"
    NEW_PARAGRAPH = "newParagraph"
    DELETE_LAST = "deleteLast"
    FINISH = "finish"


_TURKISH_PHRASES: dict[str, DictationCommand] = {
    "yeni satir": DictationCommand.NEW_LINE,
    "alt satir": DictationCommand.NEW_LINE,
    "alt satira gec": DictationCommand.NEW_LINE,
    "satir atla": DictationCommand.NEW_LINE,
    "yeni paragraf": DictationCommand.NEW_PARAGRAPH,
    "paragraf": DictationCommand.NEW_PARAGRAPH,
    "son cumleyi sil": DictationCommand.DELETE_LAST,
    "sonuncuyu sil": DictationCommand.DELETE_LAST,
    "geri al": DictationCommand.DELETE_LAST,
    "onu sil": DictationCommand.DELETE_LAST,
    "sonu sil": DictationCommand.DELETE_LAST,
    "son yazdigini sil": DictationCommand.DELETE_LAST,
    "dikteyi bitir": DictationCommand.FINISH,
    "dikte bitti": DictationCommand.FINISH,
    "tamam bitti": DictationCommand.FINISH,
    "dikteyi kapat": DictationCommand.FINISH,
    "dikte modunu kapat": DictationCommand.FINISH,
    "yazmayi bitir": DictationCommand.FINISH,
    "bitti": DictationCommand.FINISH,
}

_ENGLISH_PHRASES: dict[str, DictationCommand] = {
    "new line": DictationCommand.NEW_LINE,
    "next line": DictationCommand.NEW_LINE,
    "line break": DictationCommand.NEW_LINE,
    "new paragraph": DictationCommand.NEW_PARAGRAPH,
    "next paragraph": DictationCommand.NEW_PARAGRAPH,
    "delete that": DictationCommand.DELETE_LAST,
    "scratch that": DictationCommand.DELETE_LAST,
    "delete the last sentence": DictationCommand.DELETE_LAST,
    "delete last sentence": DictationCommand.DELETE_LAST,
    "undo that": DictationCommand.DELETE_LAST,
    "remove that": DictationCommand.DELETE_LAST,
    "stop dictation": DictationCommand.FINISH,
    "end dictation": DictationCommand.FINISH,
    "finish dictation": DictationCommand.FINISH,
    "dictation off": DictationCommand.FINISH,
    "stop dictating": DictationCommand.FINISH,
    "im done": DictationCommand.FINISH,
    "done": DictationCommand.FINISH,
    "turn off dictation": DictationCommand.FINISH,
    "turn dictation off": DictationCommand.FINISH,
    "disable dictation": DictationCommand.FINISH,
    "dictation mode off": DictationCommand.FINISH,
}

_ENGLISH_START_WORDS = frozenset({"start", "begin", "turn", "enable", "take"})
_ENGLISH_STOP_WORDS = frozenset({"off", "stop", "end", "disable", "finish"})


def parse(text: str, language: AssistantLanguage = AssistantLanguage.TURKISH) -> DictationCommand | None:
    phrases = _ENGLISH_PHRASES if language is AssistantLanguage.ENGLISH else _TURKISH_PHRASES
    return phrases.get(folded(text))


def is_start(text: str, language: AssistantLanguage = AssistantLanguage.TURKISH) -> bool:
    """ "Dikte modunu başlat", "dikteye başla", "yazdırmaya başla"; "start dictation", "dictate"."""
    words = folded(text).split()
    if language is AssistantLanguage.ENGLISH:
        mentions = any(word.startswith("dictat") for word in words)
        starts = any(word in _ENGLISH_START_WORDS for word in words) or (bool(words) and words[0] == "dictate")
        stops = any(word in _ENGLISH_STOP_WORDS for word in words)
        return mentions and starts and not stops
    mentions = any(word.startswith(("dikte", "yazdirma")) for word in words)
    starts = any(word.startswith("basla") or word == "ac" for word in words)
    return mentions and starts
