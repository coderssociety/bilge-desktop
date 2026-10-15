"""Finds the stored title a spoken phrase refers to ("süt almayı" → "Süt al", "Ahmet" → "Ahmet Yılmaz"),
tolerating Turkish case suffixes and extra or missing words."""

from bilge.core.text import folded, similarity

MINIMUM_SCORE = 0.6
_MAX_SUFFIX_LENGTH = 4
_STOP_WORDS = frozenset(
    {"ve", "ile", "bir", "bu", "su", "icin", "de", "da", "the", "a", "an", "my", "of", "and", "with"}
)


def best_match(query: str, titles: list[str]) -> str | None:
    query_words = _words(query)
    if not query_words:
        return None
    best: tuple[str, float] | None = None
    for title in titles:
        score = _score(query_words, _words(title))
        if score > (best[1] if best else 0):
            best = (title, score)
    if best is None or best[1] < MINIMUM_SCORE:
        return None
    return best[0]


def _words(text: str) -> list[str]:
    return [word for word in folded(text).split() if word not in _STOP_WORDS]


def _score(query: list[str], title: list[str]) -> float:
    if not title:
        return 0.0
    matched = sum(1 for title_word in title if any(_matches(word, title_word) for word in query))
    if matched == 0:
        return 0.0
    shorter = min(len(query), len(title))
    longer = max(len(query), len(title))
    return 0.7 * min(1, matched / shorter) + 0.3 * matched / longer


def _matches(lhs: str, rhs: str) -> bool:
    if lhs == rhs:
        return True
    short, long = (lhs, rhs) if len(lhs) <= len(rhs) else (rhs, lhs)
    if len(short) >= 2 and long.startswith(short) and len(long) - len(short) <= _MAX_SUFFIX_LENGTH:
        return True
    return len(short) >= 4 and similarity(short, long) >= 0.8
