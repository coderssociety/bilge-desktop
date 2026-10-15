"""Splits "Safari'yi aç ve sesi yüzde 30 yap" into separate commands. Plain "ve" only splits after
a known imperative, so "kahve ve süt almayı hatırlat" or "Ali ve Veli'ye yaz" stay whole."""

import unicodedata
from collections.abc import Callable

from bilge.core.language import AssistantLanguage
from bilge.core.text import folded

_SEQUENCE_MARKERS: tuple[list[str], ...] = (
    ["ve", "sonra"], ["sonra", "da"], ["daha", "sonra"], ["ardindan"], ["ayrica"], ["bir", "de"],
)  # fmt: skip
_IMPERATIVES = frozenset(
    {
        "ac", "kapat", "yap", "ekle", "gonder", "at", "yaz", "oku", "cal", "kur", "bul", "soyle", "al", "ara",
        "goster", "durdur", "kilitle", "gizle", "olustur", "hatirlat", "sil", "kopyala", "ozetle", "cevir",
        "tamamla", "isaretle", "baslat", "degistir", "ayarla", "artir", "azalt", "kis", "getir", "git", "bak",
        "anlat", "kucult", "tasi", "kaydet", "cek", "gec", "yolla", "sor", "hesapla", "listele", "kontrol", "et",
    }
)  # fmt: skip
_MINIMUM_PART_WORDS = 2

_ENGLISH_MARKERS: tuple[list[str], ...] = (["and", "then"], ["then"], ["after", "that"], ["and", "also"], ["also"])
# English verbs come first, so plain "and" splits only before one: "open Safari and set the volume…",
# while "call Ali and Veli" or "remind me to buy milk and bread" stay whole.
_ENGLISH_IMPERATIVES = frozenset(
    {
        "open", "close", "quit", "set", "add", "send", "text", "email", "message", "write", "read", "play", "find",
        "tell", "show", "stop", "pause", "lock", "hide", "create", "make", "remind", "delete", "copy", "summarize",
        "translate", "mark", "start", "change", "turn", "increase", "decrease", "bring", "go", "look", "move",
        "save", "take", "switch", "ask", "calculate", "list", "check", "search", "put", "type", "call", "note",
    }
)  # fmt: skip
_ENGLISH_REFERENCES = frozenset(
    {"him", "her", "them", "it", "that", "this", "there", "summary", "result", "results", "same", "its", "their"}
)
# Requests whose content may itself contain "and <verb>": "remind me to call the bank and send the invoice".
_ENGLISH_WHOLE_REQUESTS = frozenset({"remind", "note", "text", "email", "message", "tell", "write"})

_REFERENCES = frozenset(
    {
        "ona", "onu", "onun", "ondan", "onlara", "onlari", "bunu", "buna", "bunun", "bundan", "sunu", "oraya",
        "orada", "ozeti", "ozetini", "ozetle", "sonucu", "sonucunu", "aynisini", "bulduğun", "buldugun",
        "bulduklarini", "icerigini", "numarasina", "adresine", "metni", "metnini",
    }
)  # fmt: skip

# Given the folded tokens, the index and the words collected so far, the separator length at that index.
_MarkerFinder = Callable[[list[str], int, list[str]], int | None]


def split(text: str, language: AssistantLanguage = AssistantLanguage.TURKISH) -> list[str] | None:
    if language is AssistantLanguage.ENGLISH:
        return _split_english(text)
    return _split(text, _turkish_marker)


def has_dependent_parts(parts: list[str], language: AssistantLanguage = AssistantLanguage.TURKISH) -> bool:
    """True when a later part refers to an earlier one's result ("Ahmet'in numarasını bul ve ona mesaj at",
    "PDF'i özetle ve özeti panoya kopyala"); such requests need planning, the others can run one by one."""
    words = _ENGLISH_REFERENCES if language is AssistantLanguage.ENGLISH else _REFERENCES
    return any(word in words for part in parts[1:] for word in folded(part).split())


def _split_english(text: str) -> list[str] | None:
    plain_and_splits = not any(word in _ENGLISH_WHOLE_REQUESTS for word in [folded(t) for t in text.split()][:2])

    def marker(tokens: list[str], index: int, current: list[str]) -> int | None:
        if not current:
            return None
        return _english_marker(tokens, index, plain_and_splits)

    return _split(text, marker)


def _split(text: str, marker: _MarkerFinder) -> list[str] | None:
    tokens = text.split()
    folded_tokens = [folded(token) for token in tokens]
    parts: list[list[str]] = []
    current: list[str] = []
    index = 0
    while index < len(tokens):
        length = marker(folded_tokens, index, current)
        if length is not None:
            parts.append(current)
            current = []
            index += length
            continue
        current.append(tokens[index])
        index += 1
    parts.append(current)
    commands = [_trim(" ".join(part)) for part in parts]
    if len(commands) < 2 or any(len(command.split()) < _MINIMUM_PART_WORDS for command in commands):
        return None
    return commands


def _english_marker(tokens: list[str], index: int, plain_and: bool) -> int | None:
    for marker in _ENGLISH_MARKERS:
        if tokens[index : index + len(marker)] == marker:
            return len(marker)
    if plain_and and tokens[index] == "and" and index + 1 < len(tokens) and tokens[index + 1] in _ENGLISH_IMPERATIVES:
        return 1
    return None


def _turkish_marker(tokens: list[str], index: int, current: list[str]) -> int | None:
    """Length of the separator starting at `index`, or None when there is none there."""
    if not current:
        return None
    for marker in _SEQUENCE_MARKERS:
        if tokens[index : index + len(marker)] == marker:
            return len(marker)
    previous = _trim(folded(current[-1]))
    if tokens[index] == "ve" and previous in _IMPERATIVES:
        return 1
    return None


def _trim(text: str) -> str:
    """Strips whitespace and punctuation from both ends."""
    start, end = 0, len(text)
    while start < end and _is_trimmable(text[start]):
        start += 1
    while end > start and _is_trimmable(text[end - 1]):
        end -= 1
    return text[start:end]


def _is_trimmable(ch: str) -> bool:
    return ch.isspace() or unicodedata.category(ch).startswith("P")
