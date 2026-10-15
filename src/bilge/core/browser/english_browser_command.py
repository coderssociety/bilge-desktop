"""English counterpart of `browser_command`'s Turkish rules: "next tab", "go back", "find price on this page".
Tab commands need the word "tab"; history and scrolling are whole fixed phrases, so "volume up",
"call me back" or "forward it to Sam" never land here."""

from bilge.core.browser.browser_command import (
    Back,
    Bottom,
    BrowserCommand,
    CloseTab,
    Find,
    Forward,
    LastTab,
    NewTab,
    NextTab,
    PreviousTab,
    Reload,
    ReopenTab,
    ScrollDown,
    ScrollUp,
    Tab,
    TabNamed,
    Top,
    trim_punctuation,
)
from bilge.core.text import folded

_ORDINALS: dict[str, int] = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9,
}  # fmt: skip
_SWITCH_VERBS = frozenset({"switch", "go", "jump", "open", "show"})
_FIND_VERBS = frozenset({"find", "search", "look"})
_PHRASES: dict[str, BrowserCommand] = {
    "go back": Back(), "back": Back(), "go back a page": Back(), "previous page": Back(),
    "go to the previous page": Back(),
    "go forward": Forward(), "go forward a page": Forward(), "next page": Forward(),
    "reload": Reload(), "refresh": Reload(), "reload the page": Reload(), "refresh the page": Reload(),
    "reload page": Reload(), "refresh page": Reload(), "reload this page": Reload(), "refresh this page": Reload(),
    "scroll down": ScrollDown(), "page down": ScrollDown(), "scroll down a bit": ScrollDown(),
    "scroll up": ScrollUp(), "page up": ScrollUp(), "scroll up a bit": ScrollUp(),
    "go to the top": Top(), "scroll to the top": Top(), "scroll to top": Top(), "go to top": Top(),
    "top of the page": Top(), "go to the top of the page": Top(),
    "go to the bottom": Bottom(), "scroll to the bottom": Bottom(), "scroll to bottom": Bottom(),
    "go to bottom": Bottom(), "bottom of the page": Bottom(), "go to the bottom of the page": Bottom(),
    "end of the page": Bottom(),
}  # fmt: skip
_MAX_TAB_NUMBER = 99


def parse(text: str) -> BrowserCommand | None:
    words = folded(text).split()
    if not words:
        return None
    tab_index = next((i for i, word in enumerate(words) if word in ("tab", "tabs")), None)
    if tab_index is not None:
        return _tab(words, tab_index, text)
    found = _find(words, text)
    if found is not None:
        return found
    return _PHRASES.get(" ".join(word for word in words if word != "please"))


def _tab(words: list[str], index: int, original: str) -> BrowserCommand | None:
    if "reopen" in words or ("closed" in words and "close" not in words):
        return ReopenTab()
    if "new" in words:
        return NewTab()
    if "close" in words:
        return CloseTab()
    if "next" in words:
        return NextTab()
    if "previous" in words:
        return PreviousTab()
    ordinal = next((_ORDINALS[word] for word in words if word in _ORDINALS), None)
    if ordinal is not None:
        return Tab(ordinal)
    number = next((int(word) for word in words[index:] if word.isascii() and word.isdigit()), None)
    if number is not None and 1 <= number <= _MAX_TAB_NUMBER:
        return Tab(number)
    if "last" in words:
        return LastTab()
    # "Switch to the YouTube tab": the title sits between "to (the)" and "tab".
    if not any(word in _SWITCH_VERBS for word in words) or "to" not in words:
        return None
    to = words.index("to")
    if to >= index:
        return None
    original_words = original.split()
    if len(original_words) != len(words):
        return None
    start = to + 1
    if start < index and words[start] == "the":
        start += 1
    title = " ".join(original_words[start:index])
    return TabNamed(title) if title else None


def _find(words: list[str], original: str) -> BrowserCommand | None:
    """ "Find price on this page", "search for return policy on the page"."""
    if "page" not in words:
        return None
    verb = next((i for i, word in enumerate(words) if word in _FIND_VERBS), None)
    if verb is None:
        return None
    start = verb + 1
    if start < len(words) and words[start] == "for":
        start += 1
    end = next((i for i in range(start + 1, len(words)) if words[i] in ("on", "in")), None)
    if end is None:
        return None
    original_words = original.split()
    if len(original_words) != len(words):
        return None
    phrase = original_words[start:end]
    if len(phrase) > 1 and folded(phrase[0]) in ("the", "word"):
        phrase = phrase[1:]
    query = trim_punctuation(" ".join(phrase))
    return Find(query) if query else None
