"""English counterpart of `memory_intent`. "Remember" (store a fact) and "remind" (a reminder) look alike,
so the router model is not trusted with either."""

from bilge.core.memory.memory_intent import (
    ForgetAll,
    ForgetLatest,
    ForgetMatching,
    ForgetTarget,
    MemoryIntent,
    trim,
)
from bilge.core.text import folded

_QUESTION_WORDS = frozenset({"what", "whats", "which", "anything", "show", "list", "tell"})
_CLEAR_VERBS = frozenset({"clear", "erase", "wipe", "reset", "delete", "empty"})
_REQUEST_WORDS = frozenset({"please", "can", "could", "you", "would"})
_FORGET_FILLERS = frozenset(
    {
        "forget", "about", "the", "that", "thing", "info", "information", "fact", "what", "i", "told", "you",
        "said", "please", "now", "can", "could", "would",
    }
)  # fmt: skip
_REFERENCE_WORDS = frozenset({"this", "that", "it"})
_REQUEST_PHRASES: tuple[list[str], ...] = (
    ["dont", "forget"],
    ["do", "not", "forget"],
    ["keep", "in", "mind"],
    ["remember"],
)


def parse(command: str) -> MemoryIntent | None:
    words = folded(command).split()
    if any(word.startswith("remind") for word in words):
        return None
    mentions_memory = any(word in ("memory", "memories") for word in words)
    asks = any(word in _QUESTION_WORDS for word in words)
    if (
        ("remember" in words and asks)
        or _contains_sequence(words, ["know", "about", "me"])
        or (mentions_memory and asks)
    ):
        return MemoryIntent.LIST
    if _contains_sequence(words, ["dont", "forget"]) or _contains_sequence(words, ["do", "not", "forget"]):
        return MemoryIntent.REMEMBER
    if "forget" in words or (mentions_memory and any(word in _CLEAR_VERBS for word in words)):
        return MemoryIntent.FORGET
    if "remember" in words or _contains_sequence(words, ["keep", "in", "mind"]):
        return MemoryIntent.REMEMBER
    return None


def forget_target(command: str) -> ForgetTarget:
    """ "Forget everything" → all, "Forget that" → the latest fact, "Forget my coffee order" → "my coffee order"."""
    tokens = command.split()
    words = [folded(token) for token in tokens]
    clears_memory = "memory" in words and any(word in _CLEAR_VERBS for word in words)
    if clears_memory or "everything" in words or _contains_sequence(words, ["it", "all"]):
        return ForgetAll()
    kept = [
        token
        for token, word in zip(tokens, words, strict=True)
        if word and word not in _FORGET_FILLERS and word not in _REFERENCE_WORDS
    ]
    query = trim(" ".join(kept))
    return ForgetMatching(query) if query else ForgetLatest()


def fact(command: str) -> str | None:
    """ "Remember that the door code changed" → "the door code changed"; None for "remember this"."""
    tokens = command.split()
    words = [folded(token) for token in tokens]
    start = _request_end(words)
    if start is None:
        return None
    kept = tokens[start:]
    if len(kept) > 1 and folded(kept[0]) in ("that", "this"):
        kept = kept[1:]
    result = trim(" ".join(kept))
    if not result or folded(result) in _REFERENCE_WORDS:
        return None
    return result


def _request_end(words: list[str]) -> int | None:
    """Index just past "please remember", "don't forget", "keep in mind" and the like."""
    for phrase in _REQUEST_PHRASES:
        index = _sequence_index(words, phrase)
        if index is None:
            continue
        if all(word in _REQUEST_WORDS for word in words[:index]):
            return index + len(phrase)
    return None


def _contains_sequence(words: list[str], sequence: list[str]) -> bool:
    return _sequence_index(words, sequence) is not None


def _sequence_index(words: list[str], sequence: list[str]) -> int | None:
    return next(
        (start for start in range(len(words) - len(sequence) + 1) if words[start : start + len(sequence)] == sequence),
        None,
    )
