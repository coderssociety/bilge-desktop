"""Item titles from an RSS 2.0 or Atom feed, in feed order."""

import contextlib
from xml.parsers import expat


class _LimitReached(Exception):
    pass


class _Collector:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.titles: list[str] = []
        self._in_item = False
        self._current: list[str] | None = None

    def start(self, name: str, _attributes: dict[str, str]) -> None:
        if name in ("item", "entry"):
            self._in_item = True
        if self._in_item and name == "title":
            self._current = []

    def characters(self, text: str) -> None:
        if self._current is not None:
            self._current.append(text)

    def end(self, name: str) -> None:
        if name == "title" and self._current is not None:
            cleaned = "".join(self._current).strip()
            if cleaned:
                self.titles.append(cleaned)
            self._current = None
            if len(self.titles) >= self.limit:
                raise _LimitReached
        if name in ("item", "entry"):
            self._in_item = False


def parse(data: bytes, limit: int) -> list[str]:
    """Titles found before the limit or the first XML error; a broken feed still yields what came before it."""
    collector = _Collector(limit)
    parser = expat.ParserCreate()
    parser.StartElementHandler = collector.start
    parser.CharacterDataHandler = collector.characters
    parser.EndElementHandler = collector.end
    with contextlib.suppress(_LimitReached, expat.ExpatError):
        parser.Parse(data, True)
    return collector.titles
