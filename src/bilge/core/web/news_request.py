"""What a news request asks for, read from its own words (the router model has answered "teknoloji haberlerinden
başlık var mı" with the general headlines), and which headlines have been read out already, so asking again goes on
with the next ones instead of repeating them."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from bilge.core import text

TOPICS = ("general", "economy", "sports", "world", "technology")
_TOPIC_WORDS = (
    ("teknoloj", "technology"), ("bilim", "technology"), ("tech", "technology"), ("science", "technology"),
    ("ekonom", "economy"), ("econom", "economy"), ("borsa", "economy"), ("piyasa", "economy"),
    ("finans", "economy"), ("financ", "economy"), ("business", "economy"),
    ("spor", "sports"), ("sport", "sports"), ("futbol", "sports"), ("football", "sports"), ("basketbol", "sports"),
    ("dunya", "world"), ("world", "world"), ("uluslararas", "world"), ("international", "world"),
    ("gundem", "general"),
)  # fmt: skip
_NEWS_WORDS = ("haber", "baslik", "manset", "gundem", "news", "headline")
# After this the news is read from the top again.
LIFETIME = timedelta(minutes=30)
# How long "bu kadar mı" still means the topic just read.
CONTINUATION_WINDOW = timedelta(minutes=5)


def _words(command: str) -> list[str]:
    return [word for word in re.split(r"[^\w]+|_", text.folded(command)) if word and not word.isdigit()]


def topic(command: str) -> str | None:
    """The topic the command names, if it names one."""
    for word in _words(command):
        for prefix, named in _TOPIC_WORDS:
            if word.startswith(prefix):
                return named
    return None


def is_continuation(command: str) -> bool:
    """A follow-up such as "bu kadar mı" or "başka var mı": routed to the news without asking for news or naming a
    topic, it goes on with the headlines just read."""
    return topic(command) is None and not any(w.startswith(n) for w in _words(command) for n in _NEWS_WORDS)


class Kind(Enum):
    # The latest headlines.
    FIRST = "first"
    # The ones after those read before.
    NEXT = "next"
    # Nothing new since the last reading: the same headlines again.
    AGAIN = "again"


@dataclass(frozen=True)
class Reading:
    headlines: list[str]
    kind: Kind


class HeadlineMemory:
    def __init__(self) -> None:
        self._read: dict[str, tuple[frozenset[str], datetime]] = {}
        self._last: tuple[str, datetime] | None = None

    def recent_topic(self, at: datetime) -> str | None:
        if self._last is None or at - self._last[1] >= CONTINUATION_WINDOW:
            return None
        return self._last[0]

    def next(self, headlines: list[str], topic: str, count: int, at: datetime) -> Reading:
        """The next `count` of `headlines` (the feed, newest first) not yet read for `topic`."""
        titles, read_at = self._read.get(topic, (frozenset(), at))
        earlier = titles if at - read_at < LIFETIME else frozenset()
        fresh = [headline for headline in headlines if headline not in earlier]
        if not fresh:
            reading = Reading(headlines[:count], Kind.AGAIN)
            self._read[topic] = (frozenset(reading.headlines), at)
        else:
            reading = Reading(fresh[:count], Kind.NEXT if earlier else Kind.FIRST)
            self._read[topic] = (earlier | frozenset(reading.headlines), at)
        self._last = (topic, at)
        return reading
