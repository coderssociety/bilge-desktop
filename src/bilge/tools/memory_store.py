"""What the user asked Bilge to remember, kept in a file only they can read."""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from bilge.core.memory.memory_book import AddOutcome, MemoryBook, MemoryEntry

# The facts go into every request's instructions; this keeps them from crowding out the request.
PROMPT_CHARACTERS = 1500


class MemoryStore:
    def __init__(self, path: Path):
        self.path = path
        self.book = self._load()

    def _load(self) -> MemoryBook:
        try:
            return MemoryBook.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return MemoryBook(())
        except (OSError, ValueError, KeyError, TypeError) as error:
            # Starting empty would overwrite the user's facts on the next save.
            raise RuntimeError(f"Could not read the memory file {self.path}: {error}") from error

    def _save(self, book: MemoryBook) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(json.dumps(book.to_dict(), ensure_ascii=False))
        temporary.replace(self.path)
        self.book = book

    def remember(self, text: str) -> AddOutcome:
        book, outcome = self.book.adding(text, datetime.now())
        if outcome not in (AddOutcome.DUPLICATE, AddOutcome.REJECTED):
            self._save(book)
        return outcome

    def forget(self, entry_id: uuid.UUID) -> None:
        self._save(self.book.removing_id(entry_id))

    def forget_all(self) -> int:
        count = len(self.book.entries)
        self._save(MemoryBook(()))
        return count

    def entry_matching(self, query: str) -> MemoryEntry | None:
        return self.book.entry_matching(query)

    def prompt_lines(self) -> str | None:
        return self.book.prompt_lines(PROMPT_CHARACTERS)
