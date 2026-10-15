"""Resolves a spoken application name ("hesap makinesini", "spotifay") to an installed app."""

from dataclasses import dataclass

from bilge.core.text import folded, similarity

MINIMUM_SCORE = 0.72
_MAX_SUFFIX_LENGTH = 4
_NOISE_WORDS = frozenset(
    {"uygulamasi", "uygulamasini", "uygulama", "programi", "programini", "app", "application", "the"}
)


@dataclass(frozen=True)
class App:
    id: str
    names: tuple[str, ...]


class AppNameMatcher:
    def __init__(self, apps: list[App]) -> None:
        self._entries = [(app, [key for key in map(folded, app.names) if key]) for app in apps]

    def best_match(self, query: str) -> App | None:
        key = " ".join(word for word in folded(query).split() if word not in _NOISE_WORDS)
        if not key:
            return None

        best: tuple[App, float] | None = None
        for app, keys in self._entries:
            score = max((_score(key, name) for name in keys), default=0.0)
            if score > (best[1] if best else 0):
                best = (app, score)
        if best is None or best[1] < MINIMUM_SCORE:
            return None
        return best[0]


def _score(query: str, name: str) -> float:
    if query == name:
        return 1.0
    # Turkish case suffixes: "safariyi", "hesap makinesini", "muzigi" (final consonant softening).
    extra = len(query) - len(name)
    if 1 <= extra <= _MAX_SUFFIX_LENGTH:
        stem_score = similarity(query[: len(name)], name)
        if stem_score >= 0.8:
            return 0.95 * stem_score
    best = similarity(query, name)
    # A single distinctive word of a multi-word name ("word" → "microsoft word").
    name_words = name.split(" ")
    if len(name_words) > 1 and " " not in query and query in name_words and len(query) >= 4:
        best = max(best, 0.9)
    return best
