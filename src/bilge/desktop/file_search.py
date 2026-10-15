"""Finding files by name in the user's home folder, newest first.

There is no search index every Linux desktop has, so the home folder is walked directly: the usual folders first,
hidden and bulky folders (caches, dependencies, version control) skipped, and the walk stops after a time budget.
"""

import os
import time
from collections.abc import Iterator
from pathlib import Path

from bilge.core.text import folded

BUDGET_SECONDS = 3.0
MAX_DEPTH = 8
_SKIPPED = frozenset(
    {
        "node_modules", "__pycache__", "site-packages", "venv", ".venv", "target", "build", "dist", "snap",
        "Library", "AppData", "Steam", "steamapps",
    }
)  # fmt: skip


def find(query: str, roots: list[Path], limit: int, budget: float = BUDGET_SECONDS) -> list[Path]:
    """Files whose name contains every word of `query` (Turkish letters and case ignored)."""
    words = folded(query).split()
    if not words:
        return []
    found: list[Path] = []
    deadline = time.monotonic() + budget
    for path in _walk(roots, deadline):
        name = folded(path.name)
        if all(word in name for word in words):
            found.append(path)
    return newest_first(found)[:limit]


def newest_first(paths: list[Path]) -> list[Path]:
    def modified(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    return sorted(paths, key=modified, reverse=True)


def _walk(roots: list[Path], deadline: float) -> Iterator[Path]:
    seen: set[Path] = set()
    for root in roots:
        stack = [(root, 0)]
        while stack:
            folder, depth = stack.pop()
            if folder in seen or time.monotonic() > deadline:
                continue
            seen.add(folder)
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                path = Path(entry.path)
                if is_dir:
                    if entry.name not in _SKIPPED and depth < MAX_DEPTH:
                        stack.append((path, depth + 1))
                else:
                    yield path
