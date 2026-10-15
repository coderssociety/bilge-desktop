"""Browser control by voice ("sonraki sekmeye geç", "geri git", "bu sayfada fiyatı ara"), recognized by
rules. Tab commands need the word "sekme"; history and scrolling need their own fixed phrases, so
"geri al" (undo) or "Safari'yi aç" never land here."""

import unicodedata
from dataclasses import dataclass

from bilge.core.language import AssistantLanguage
from bilge.core.text import folded


@dataclass(frozen=True)
class NextTab:
    pass


@dataclass(frozen=True)
class PreviousTab:
    pass


@dataclass(frozen=True)
class LastTab:
    pass


@dataclass(frozen=True)
class NewTab:
    pass


@dataclass(frozen=True)
class CloseTab:
    pass


@dataclass(frozen=True)
class ReopenTab:
    pass


@dataclass(frozen=True)
class Tab:
    index: int


@dataclass(frozen=True)
class TabNamed:
    title: str


@dataclass(frozen=True)
class Back:
    pass


@dataclass(frozen=True)
class Forward:
    pass


@dataclass(frozen=True)
class Reload:
    pass


@dataclass(frozen=True)
class ScrollDown:
    pass


@dataclass(frozen=True)
class ScrollUp:
    pass


@dataclass(frozen=True)
class Top:
    pass


@dataclass(frozen=True)
class Bottom:
    pass


@dataclass(frozen=True)
class Find:
    query: str


BrowserCommand = (
    NextTab
    | PreviousTab
    | LastTab
    | NewTab
    | CloseTab
    | ReopenTab
    | Tab
    | TabNamed
    | Back
    | Forward
    | Reload
    | ScrollDown
    | ScrollUp
    | Top
    | Bottom
    | Find
)

_ORDINALS: dict[str, int] = {
    "ilk": 1, "birinci": 1, "ikinci": 2, "ucuncu": 3, "dorduncu": 4, "besinci": 5, "altinci": 6, "yedinci": 7,
    "sekizinci": 8, "dokuzuncu": 9,
}  # fmt: skip
_APOSTROPHES = frozenset("'’‘`´")
_FIND_OBJECT_WORDS = frozenset({"kelimesini", "sozcugunu", "ifadesini", "yazisini"})


def parse(text: str, language: AssistantLanguage = AssistantLanguage.TURKISH) -> BrowserCommand | None:
    if language is AssistantLanguage.ENGLISH:
        from bilge.core.browser import english_browser_command

        return english_browser_command.parse(text)
    words = folded(text).split()
    if not words:
        return None

    def has(word: str) -> bool:
        return word in words

    def has_prefix(prefix: str) -> bool:
        return any(word.startswith(prefix) for word in words)

    tab_index = next((i for i, word in enumerate(words) if word.startswith("sekme")), None)
    if tab_index is not None:
        return _tab(words, tab_index, text)
    found = _find(words, text)
    if found is not None:
        return found
    if has("geri") and (has_prefix("git") or has_prefix("don")) and len(words) <= 3:
        return Back()
    if has_prefix("onceki") and has_prefix("sayfa") and len(words) <= 4:
        return Back()
    if has("ileri") and has_prefix("git") and len(words) <= 3:
        return Forward()
    if has_prefix("yenile") and (len(words) == 1 or has_prefix("sayfa")):
        return Reload()
    goes_end = has("en") or has_prefix("sayfanin")
    if goes_end and (has_prefix("alt") or has_prefix("sonu") or (has("en") and has_prefix("asagi"))):
        return Bottom()
    if goes_end and (has_prefix("ust") or has_prefix("basi") or (has("en") and has_prefix("yukari"))):
        return Top()
    scrolls = has_prefix("kaydir") or has_prefix("in") or has_prefix("cik") or len(words) <= 2
    if has_prefix("asagi") and scrolls and len(words) <= 3:
        return ScrollDown()
    if has_prefix("yukari") and scrolls and len(words) <= 3:
        return ScrollUp()
    return None


def _tab(words: list[str], index: int, original: str) -> BrowserCommand | None:
    if any(word.startswith("kapattig") for word in words):
        return ReopenTab()
    if "yeni" in words:
        return NewTab()
    if any(word.startswith("kapat") for word in words):
        return CloseTab()
    if any(word.startswith("sonraki") for word in words):
        return NextTab()
    if any(word.startswith("onceki") for word in words):
        return PreviousTab()
    ordinal = next((_ORDINALS[word] for word in words if word in _ORDINALS), None)
    if ordinal is not None:
        return Tab(ordinal)
    if "son" in words:
        return LastTab()
    # "YouTube sekmesine geç": the title is what comes before "sekmesi…".
    switches = any(word.startswith("gec") or word == "ac" or word.startswith("don") for word in words)
    if not switches or index == 0 or not words[index].startswith("sekmesi"):
        return None
    original_words = original.split()
    if len(original_words) != len(words):
        return None
    title = " ".join(original_words[:index])
    return TabNamed(title) if title else None


def _find(words: list[str], original: str) -> BrowserCommand | None:
    """ "Bu sayfada fiyat kelimesini ara", "sayfada iade koşulları'nı bul"."""
    if "sayfada" not in words:
        return None
    page = words.index("sayfada")
    verb = next((i for i in range(len(words) - 1, -1, -1) if words[i] in ("ara", "bul")), None)
    if verb is None or verb <= page + 1:
        return None
    original_words = original.split()
    if len(original_words) != len(words):
        return None
    phrase = original_words[page + 1 : verb]
    if folded(phrase[-1]) in _FIND_OBJECT_WORDS:
        phrase = phrase[:-1]
    if not phrase:
        return None
    last = phrase[-1]
    mark = next((i for i, ch in enumerate(last) if ch in _APOSTROPHES), None)
    if mark is not None:
        phrase = [*phrase[:-1], last[:mark]]
    query = trim_punctuation(" ".join(phrase))
    return Find(query) if query else None


def trim_punctuation(text: str) -> str:
    """Strips punctuation and spaces from both ends, like Swift's `.punctuationCharacters.union(.whitespaces)`."""
    start, end = 0, len(text)
    while start < end and _is_trimmable(text[start]):
        start += 1
    while end > start and _is_trimmable(text[end - 1]):
        end -= 1
    return text[start:end]


def _is_trimmable(ch: str) -> bool:
    category = unicodedata.category(ch)
    return category.startswith("P") or category == "Zs" or ch == "\t"
