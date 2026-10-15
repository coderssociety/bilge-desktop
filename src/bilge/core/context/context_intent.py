"""'Bunu özetle', 'bu sayfayı çevir', 'şu dosyayı aç': a request about something on screen, recognized
by a pointing word together with what to do with it."""

from dataclasses import dataclass
from enum import StrEnum

from bilge.core.language import AssistantLanguage
from bilge.core.text import folded


class Action(StrEnum):
    SUMMARIZE = "summarize"
    TRANSLATE = "translate"
    EXPLAIN = "explain"
    READ = "read"
    OPEN = "open"


class Kind(StrEnum):
    TEXT = "text"
    FILE = "file"
    PAGE = "page"
    DOCUMENT = "document"


@dataclass(frozen=True)
class ContextIntent:
    action: Action
    wanted: Kind | None


_POINTING_WORDS = frozenset(
    {
        "bu", "bunu", "buna", "bunun", "bunlari", "su", "sunu", "suna", "sunun", "secili", "secilen", "sectigim",
        "isaretledigim", "isaretli", "acik", "ondeki",
    }
)  # fmt: skip
_SELECTION_WORDS = frozenset({"secili", "secilen", "sectigim", "isaretledigim", "isaretli"})
_KIND_PREFIXES: tuple[tuple[str, Kind], ...] = (
    ("metn", Kind.TEXT), ("metin", Kind.TEXT), ("yazi", Kind.TEXT), ("paragraf", Kind.TEXT), ("cumle", Kind.TEXT),
    ("dosya", Kind.FILE), ("belge", Kind.DOCUMENT), ("dokuman", Kind.DOCUMENT), ("pdf", Kind.DOCUMENT),
    ("sayfa", Kind.PAGE), ("site", Kind.PAGE), ("link", Kind.PAGE), ("baglanti", Kind.PAGE), ("makale", Kind.PAGE),
    ("haber", Kind.PAGE),
)  # fmt: skip
_ACTION_PREFIXES: tuple[tuple[str, Action], ...] = (
    ("ozetle", Action.SUMMARIZE), ("ozet", Action.SUMMARIZE), ("cevir", Action.TRANSLATE),
    ("acikla", Action.EXPLAIN), ("anlat", Action.EXPLAIN), ("ne demek", Action.EXPLAIN), ("oku", Action.READ),
    ("ne yaziyor", Action.READ), ("ac", Action.OPEN),
)  # fmt: skip
# Words that point at something else than the screen: "bu akşam", "bu şarkı".
_OTHER_REFERENTS = ("aksam", "sabah", "gece", "hafta", "ay", "yil", "sarki", "parca", "sefer", "kez")
# Shorter prefixes ("ac") must match a whole word, or "acil" would read as "aç".
_MIN_PREFIX_MATCH_LENGTH = 3


def parse(command: str, language: AssistantLanguage = AssistantLanguage.TURKISH) -> ContextIntent | None:
    if language is AssistantLanguage.ENGLISH:
        from bilge.core.context import english_context_words

        return english_context_words.parse(command)
    words = folded(command).split()
    pointer = next((i for i, word in enumerate(words) if word in _POINTING_WORDS), None)
    if pointer is None or _is_other_referent(words, pointer + 1):
        return None
    wanted = _kind(words)
    if wanted is None and any(word in _SELECTION_WORDS for word in words):
        wanted = Kind.TEXT
    action = _action(words)
    return ContextIntent(action=action, wanted=wanted) if action is not None else None


def points(command: str, language: AssistantLanguage = AssistantLanguage.TURKISH) -> bool:
    """Whether the command points at something ("bunu", "şu dosya"), so the screen is worth reading."""
    if language is AssistantLanguage.ENGLISH:
        from bilge.core.context import english_context_words

        return english_context_words.points(command)
    words = folded(command).split()
    return any(word in _POINTING_WORDS and not _is_other_referent(words, i + 1) for i, word in enumerate(words))


def wanted_kind(text: str, language: AssistantLanguage = AssistantLanguage.TURKISH) -> Kind | None:
    """The kind a pointing phrase names: "bu linki" is a page, "şu dosyayı" a file."""
    if language is AssistantLanguage.ENGLISH:
        from bilge.core.context import english_context_words

        return english_context_words.wanted_kind(text)
    return _kind(folded(text).split())


def only_points(text: str, language: AssistantLanguage = AssistantLanguage.TURKISH) -> bool:
    """A message body that only points at the screen ("bunu", "bu linki") rather than saying something."""
    if language is AssistantLanguage.ENGLISH:
        from bilge.core.context import english_context_words

        return english_context_words.only_points(text)
    words = folded(text).split()
    if not words:
        return True
    if words[0] not in _POINTING_WORDS or len(words) > 2:
        return False
    return len(words) == 1 or any(words[1].startswith(prefix) for prefix, _ in _KIND_PREFIXES)


def _is_other_referent(words: list[str], index: int) -> bool:
    return index < len(words) and words[index].startswith(_OTHER_REFERENTS)


def _kind(words: list[str]) -> Kind | None:
    for word in words:
        kind = next((kind for prefix, kind in _KIND_PREFIXES if word.startswith(prefix)), None)
        if kind is not None:
            return kind
    return None


def _action(words: list[str]) -> Action | None:
    text = " ".join(words)
    for prefix, action in _ACTION_PREFIXES:
        if " " in prefix:
            if prefix in text:
                return action
        elif any(
            word == prefix or (word.startswith(prefix) and len(prefix) >= _MIN_PREFIX_MATCH_LENGTH) for word in words
        ):
            return action
    return None
