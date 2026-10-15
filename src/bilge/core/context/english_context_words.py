"""English counterpart of `context_intent`'s Turkish words: "summarize this", "translate the selected text",
"send this to Ahmet"."""

from bilge.core.context.context_intent import Action, ContextIntent, Kind
from bilge.core.text import folded

_POINTING_WORDS = frozenset({"this", "that", "these", "those", "selected", "highlighted", "current"})
# Words after a pointer that name something other than the screen: "this evening", "this song".
_OTHER_REFERENTS = (
    "morning", "afternoon", "evening", "night", "week", "weekend", "month", "year", "song", "track", "time", "one",
    "is", "was", "will", "would", "should", "could",
)  # fmt: skip
_KINDS: dict[str, Kind] = {
    "text": Kind.TEXT, "paragraph": Kind.TEXT, "sentence": Kind.TEXT, "passage": Kind.TEXT, "selection": Kind.TEXT,
    "file": Kind.FILE, "document": Kind.DOCUMENT, "doc": Kind.DOCUMENT, "pdf": Kind.DOCUMENT,
    "report": Kind.DOCUMENT,
    "page": Kind.PAGE, "site": Kind.PAGE, "website": Kind.PAGE, "link": Kind.PAGE, "article": Kind.PAGE,
    "tab": Kind.PAGE,
}  # fmt: skip
_ACTIONS: tuple[tuple[frozenset[str], Action], ...] = (
    (frozenset({"summarize", "summarise", "summary", "sum", "tldr"}), Action.SUMMARIZE),
    (frozenset({"translate", "translation"}), Action.TRANSLATE),
    (frozenset({"explain", "mean", "means"}), Action.EXPLAIN),
    (frozenset({"read"}), Action.READ),
    (frozenset({"open"}), Action.OPEN),
)
_SELECTION_WORDS = frozenset({"selected", "highlighted"})
# Verbs that take what is on screen as their object: "send this", "summarize that".
_OBJECT_VERBS = frozenset(
    {
        "send", "share", "email", "text", "message", "copy", "summarize", "summarise", "translate", "explain", "read",
        "open", "save", "forward", "attach", "show",
    }
)  # fmt: skip
# Requests about later or about memory, where "this" is not the screen: "remind me to read this".
_LATER_WORDS = frozenset({"remind", "remember", "note"})


def parse(command: str) -> ContextIntent | None:
    words = _words(command)
    if any(word in _LATER_WORDS for word in words) or _pointing_index(words) is None:
        return None
    action = next((action for verbs, action in _ACTIONS if not verbs.isdisjoint(words)), None)
    if action is None:
        return None
    wanted = _kind(words)
    if wanted is None and any(word in _SELECTION_WORDS for word in words):
        wanted = Kind.TEXT
    return ContextIntent(action=action, wanted=wanted)


def points(command: str) -> bool:
    """Only when the pointer is the object ("send this", "this link"), not "tell Ali that…"."""
    if parse(command) is not None:
        return True
    words = _words(command)
    for index, word in enumerate(words):
        if word not in _POINTING_WORDS or _is_other_referent(words, index):
            continue
        named = index + 1 < len(words) and _kind([words[index + 1]]) is not None
        is_object = index > 0 and words[index - 1] in _OBJECT_VERBS
        if named or is_object:
            return True
    return False


def wanted_kind(text: str) -> Kind | None:
    return _kind(_words(text))


def only_points(text: str) -> bool:
    """ "this", "that link": a message body that points at the screen instead of saying something."""
    words = [word for word in _words(text) if word != "the"]
    if not words:
        return True
    if words[0] not in _POINTING_WORDS or len(words) > 2:
        return False
    return len(words) == 1 or words[1] in _KINDS


def _pointing_index(words: list[str]) -> int | None:
    return next(
        (i for i, word in enumerate(words) if word in _POINTING_WORDS and not _is_other_referent(words, i)), None
    )


def _is_other_referent(words: list[str], index: int) -> bool:
    """ "this evening's", "that song": prefixes, so possessives and plurals count too."""
    return index + 1 < len(words) and words[index + 1].startswith(_OTHER_REFERENTS)


def _kind(words: list[str]) -> Kind | None:
    for word in words:
        kind = _KINDS.get(word)
        if kind is None:
            kind = _KINDS.get(word[:-1])
        if kind is not None:
            return kind
    return None


def _words(text: str) -> list[str]:
    return folded(text).split()
