"""Facts the user asked the assistant to keep ("eşimin adı Ayşe"). Kept small: every entry is part of
the conversation instructions, and the on-device model has an 8K window."""

import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from bilge.core.text import folded
from bilge.core.tools import phrase_matcher

MAX_ENTRIES = 50
MAX_ENTRY_LENGTH = 200
_STEM_LENGTH = 4
# Swift's JSONEncoder writes dates as seconds since 2001-01-01; the JSON stays readable by the Mac app.
_REFERENCE_DATE_TIMESTAMP = 978_307_200


class AddOutcome(StrEnum):
    ADDED = "added"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"
    # Added, and the oldest fact was dropped to make room.
    ADDED_DROPPING_OLDEST = "addedDroppingOldest"


@dataclass(frozen=True)
class MemoryEntry:
    id: uuid.UUID
    text: str
    created: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id).upper(),
            "text": self.text,
            "created": self.created.timestamp() - _REFERENCE_DATE_TIMESTAMP,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryEntry":
        created = datetime.fromtimestamp(float(data["created"]) + _REFERENCE_DATE_TIMESTAMP, UTC)
        return cls(id=uuid.UUID(data["id"]), text=str(data["text"]), created=created)


@dataclass(frozen=True)
class MemoryBook:
    entries: tuple[MemoryEntry, ...] = ()

    def adding(self, text: str, at: datetime) -> tuple["MemoryBook", AddOutcome]:
        # One line per fact: a line break inside one could pose as another fact or an instruction.
        cleaned = _trim(" ".join(text.split()))
        if not cleaned or len(cleaned) > MAX_ENTRY_LENGTH:
            return self, AddOutcome.REJECTED
        key = folded(cleaned)
        if any(folded(entry.text) == key for entry in self.entries):
            return self, AddOutcome.DUPLICATE
        kept = self.entries[-(MAX_ENTRIES - 1) :]
        outcome = AddOutcome.ADDED_DROPPING_OLDEST if len(kept) < len(self.entries) else AddOutcome.ADDED
        entry = MemoryEntry(id=uuid.uuid4(), text=cleaned, created=at)
        return MemoryBook(entries=(*kept, entry)), outcome

    def removing_matching(self, query: str) -> tuple["MemoryBook", MemoryEntry | None]:
        entry = self.entry_matching(query)
        if entry is None:
            return self, None
        return self.removing_id(entry.id), entry

    def entry_matching(self, query: str) -> MemoryEntry | None:
        """The fact `query` refers to ("kahveyle ilgili" → "Kahvemi şekersiz içerim"), None if none or unclear."""
        text = phrase_matcher.best_match(query, [entry.text for entry in self.entries])
        if text is None:
            text = self._stem_match(query)
        if text is None:
            return None
        return next((entry for entry in self.entries if entry.text == text), None)

    @property
    def latest(self) -> MemoryEntry | None:
        return self.entries[-1] if self.entries else None

    def _stem_match(self, query: str) -> str | None:
        """ "kahveyle" and "kahvemi" share no suffix-tolerant match but the same stem; only a single best
        entry counts."""
        stems = {word[:_STEM_LENGTH] for word in folded(query).split() if len(word) >= _STEM_LENGTH}
        scored = [
            (entry.text, sum(1 for word in folded(entry.text).split() if word[:_STEM_LENGTH] in stems))
            for entry in self.entries
        ]
        if not scored:
            return None
        best_count = max(count for _, count in scored)
        winners = [text for text, count in scored if count == best_count]
        if best_count == 0 or len(winners) != 1:
            return None
        return winners[0]

    def removing_id(self, entry_id: uuid.UUID) -> "MemoryBook":
        return MemoryBook(entries=tuple(entry for entry in self.entries if entry.id != entry_id))

    def prompt_lines(self, max_characters: int) -> str | None:
        """ "- fact" lines, newest first, as many as fit in `max_characters`; None when there is nothing to say."""
        lines: list[str] = []
        used = 0
        for entry in reversed(self.entries):
            line = f"- {entry.text}"
            if used + len(line) > max_characters:
                break
            lines.append(line)
            used += len(line) + 1
        return "\n".join(lines) if lines else None

    def to_dict(self) -> dict[str, Any]:
        return {"entries": [entry.to_dict() for entry in self.entries]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryBook":
        return cls(entries=tuple(MemoryEntry.from_dict(entry) for entry in data["entries"]))


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
