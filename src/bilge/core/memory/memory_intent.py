"""Recognizes requests about the assistant's memory without the model. "Hatırla" (remember) and
"hatırlat" (remind) differ by one letter, and the router model cannot be trusted to tell them apart."""

import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from types import ModuleType

from bilge.core.language import AssistantLanguage
from bilge.core.text import folded


class MemoryIntent(StrEnum):
    REMEMBER = "remember"
    FORGET = "forget"
    LIST = "list"


@dataclass(frozen=True)
class ForgetAll:
    pass


@dataclass(frozen=True)
class ForgetLatest:
    pass


@dataclass(frozen=True)
class ForgetMatching:
    query: str


ForgetTarget = ForgetAll | ForgetLatest | ForgetMatching

_REMEMBER_WORDS = frozenset(
    {"hatirla", "hatirlasana", "hatirlayin", "hatirlamani", "unutma", "unutmayin", "unutmasana"}
)
_FORGET_WORDS = frozenset({"unut", "unutsana", "unutun", "unutur"})
_CLEAR_VERBS = frozenset({"sil", "temizle", "bosalt", "sifirla"})
_QUESTION_WORDS = frozenset({"ne", "neler", "neleri", "nedir"})
_FILLER_WORDS = frozenset({"sunu", "bunu", "lutfen"})
_FORGET_FILLERS = frozenset(
    {"ilgili", "hakkindaki", "bilgiyi", "bilgileri", "bilgi", "kaydi", "seyi", "olan", "musun", "misin", "artik"}
)
_KEEP_IN_MIND = frozenset({"tut", "olsun", "tutar"})


def parse(command: str, language: AssistantLanguage = AssistantLanguage.TURKISH) -> MemoryIntent | None:
    if language is AssistantLanguage.ENGLISH:
        return _english().parse(command)
    words = folded(command).split()
    if any(word.startswith("hatirlat") for word in words):
        return None
    mentions_memory = any(word.startswith("hafiza") for word in words)
    asks = any(word in _QUESTION_WORDS for word in words)
    if (
        ("hatirliyorsun" in words and asks)
        or ("hakkimda" in words and "biliyorsun" in words)
        or (mentions_memory and asks)
    ):
        return MemoryIntent.LIST
    if any(word in _FORGET_WORDS for word in words) or (
        mentions_memory and any(word in _CLEAR_VERBS for word in words)
    ):
        return MemoryIntent.FORGET
    if any(word in _REMEMBER_WORDS for word in words) or _contains_phrase(words, "aklinda", _KEEP_IN_MIND):
        return MemoryIntent.REMEMBER
    return None


def forget_target(command: str, language: AssistantLanguage = AssistantLanguage.TURKISH) -> ForgetTarget:
    """ "Her şeyi unut" → all, "Bunu unut" → the latest fact, "Kahveyle ilgili bilgiyi unut" → "Kahveyle"."""
    if language is AssistantLanguage.ENGLISH:
        return _english().forget_target(command)
    tokens = command.split()
    words = [folded(token) for token in tokens]
    clears_memory = any(word.startswith("hafiza") for word in words) and any(word in _CLEAR_VERBS for word in words)
    if clears_memory or _contains_phrase(words, "her", frozenset({"seyi"})) or "hepsini" in words:
        return ForgetAll()
    kept = [
        token
        for token, word in zip(tokens, words, strict=True)
        if word and word not in _FORGET_WORDS and word not in _FORGET_FILLERS and word not in _FILLER_WORDS
    ]
    query = trim(" ".join(kept))
    return ForgetMatching(query) if query else ForgetLatest()


def fact(command: str, language: AssistantLanguage = AssistantLanguage.TURKISH) -> str | None:
    """The fact itself, without the request words: "Şunu hatırla: kapı şifresi değişti" → "kapı şifresi değişti".
    None when nothing is left ("Bunu hatırla" refers to something said before)."""
    if language is AssistantLanguage.ENGLISH:
        return _english().fact(command)
    tokens = command.split()
    kept: list[str] = []
    previous = ""
    for token in tokens:
        word = folded(token)
        is_request = (
            word in _REMEMBER_WORDS
            or word in _FILLER_WORDS
            or (word == "istiyorum" and previous == "hatirlamani")
            or (word in _KEEP_IN_MIND and previous == "aklinda")
            or (word == "aklinda" and len(tokens) > 1)
        )
        if not is_request and word:
            kept.append(token)
        if word:
            previous = word
    result = trim(" ".join(kept))
    return result or None


def trim(text: str) -> str:
    """Strips whitespace and punctuation from both ends."""
    start, end = 0, len(text)
    while start < end and _is_trimmable(text[start]):
        start += 1
    while end > start and _is_trimmable(text[end - 1]):
        end -= 1
    return text[start:end]


def _is_trimmable(ch: str) -> bool:
    return ch.isspace() or unicodedata.category(ch).startswith("P")


def _contains_phrase(words: list[str], first: str, seconds: frozenset[str]) -> bool:
    return any(a == first and b in seconds for a, b in zip(words, words[1:], strict=False))


def _english() -> ModuleType:
    # Imported late: the English module builds on the types defined here.
    from bilge.core.memory import english_memory_intent

    return english_memory_intent
