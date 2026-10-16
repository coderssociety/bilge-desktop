"""Items from an RSS 2.0 or Atom feed, in feed order."""

import contextlib
from dataclasses import dataclass
from urllib.parse import urlsplit
from xml.parsers import expat


@dataclass(frozen=True)
class Item:
    title: str
    # The article's address, when the feed gives one over http(s).
    link: str | None


class _LimitReached(Exception):
    pass


class _Collector:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.items: list[Item] = []
        self._in_item = False
        self._title: str | None = None
        self._link: str | None = None
        self._field: str | None = None
        self._current: list[str] | None = None

    def start(self, name: str, attributes: dict[str, str]) -> None:
        if name in ("item", "entry"):
            self._in_item = True
            self._title = self._link = None
        if not self._in_item or name not in ("title", "link"):
            return
        self._field, self._current = name, []
        # Atom gives the address as an attribute: <link rel="alternate" href="…"/>.
        if name == "link" and "href" in attributes and attributes.get("rel", "alternate") == "alternate":
            self._link = attributes["href"]

    def characters(self, text: str) -> None:
        if self._current is not None:
            self._current.append(text)

    def end(self, name: str) -> None:
        if name == self._field and self._current is not None:
            cleaned = "".join(self._current).strip()
            if cleaned and name == "title":
                self._title = cleaned
            elif cleaned:
                self._link = cleaned
            self._field = self._current = None
        if name not in ("item", "entry"):
            return
        self._in_item = False
        if self._title:
            link = self._link if self._link and urlsplit(self._link).scheme in ("http", "https") else None
            self.items.append(Item(self._title, link))
        if len(self.items) >= self.limit:
            raise _LimitReached


def items(data: bytes, limit: int) -> list[Item]:
    """Items found before the limit or the first XML error; a broken feed still yields what came before it."""
    collector = _Collector(limit)
    parser = expat.ParserCreate()
    parser.StartElementHandler = collector.start
    parser.CharacterDataHandler = collector.characters
    parser.EndElementHandler = collector.end
    with contextlib.suppress(_LimitReached, expat.ExpatError):
        parser.Parse(data, True)
    return collector.items


def parse(data: bytes, limit: int) -> list[str]:
    return [item.title for item in items(data, limit)]
