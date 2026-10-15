"""Hugging Face repository listings, checked before anything is downloaded: the listing comes from the network."""

import fnmatch
import re
from dataclasses import dataclass
from typing import Any

_REVISION = re.compile(r"[0-9a-f]{40}")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
# Sizes are stored as 64-bit numbers by Hugging Face; anything larger is a hostile listing.
_MAX_TOTAL = 2**63 - 1


@dataclass(frozen=True)
class RepositoryFile:
    path: str
    size: int
    # Git blob SHA-1 for ordinary files, SHA-256 of the content for large (LFS) files.
    git_oid: str | None = None
    lfs_sha256: str | None = None
    type: str = "file"


def parse_tree(listing: Any) -> list[RepositoryFile]:
    """Entries of `/api/models/<id>/tree/<revision>?recursive=true`; malformed ones are skipped."""
    files = []
    for entry in listing if isinstance(listing, list) else []:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("path"), str)
            or not isinstance(entry.get("size"), int)
        ):
            continue
        lfs = entry.get("lfs") if isinstance(entry.get("lfs"), dict) else {}
        files.append(
            RepositoryFile(
                path=entry["path"],
                size=entry["size"],
                git_oid=str(entry["oid"]).lower() if isinstance(entry.get("oid"), str) else None,
                lfs_sha256=str(lfs["oid"]).lower() if isinstance(lfs.get("oid"), str) else None,
                type=str(entry.get("type", "file")),
            )
        )
    return files


def select(files: list[RepositoryFile], patterns: tuple[str, ...]) -> list[RepositoryFile]:
    """The files a model needs, matched by glob patterns; anything that could leave the model's folder is dropped."""
    return [
        f
        for f in files
        if f.type == "file" and f.size >= 0 and is_safe_relative_path(f.path)
        and any(fnmatch.fnmatchcase(f.path, pattern) for pattern in patterns)
    ]  # fmt: skip


def is_safe_relative_path(path: str) -> bool:
    """A relative path inside the model folder: no "..", no absolute path, no hidden parts."""
    if not path or path.startswith("/"):
        return False
    return all(part and not part.startswith(".") and _NAME.fullmatch(part) for part in path.split("/"))


def is_valid_id(repo_id: str) -> bool:
    """ "owner/name", each part a plain name."""
    parts = repo_id.split("/")
    return len(parts) == 2 and all(_NAME.fullmatch(p) and not p.startswith(".") for p in parts)


def is_pinned_revision(revision: str) -> bool:
    """A full commit hash, so a download is pinned to exactly what was reviewed."""
    return _REVISION.fullmatch(revision) is not None


def total_size(files: list[RepositoryFile]) -> int | None:
    """None when a size is negative or the sum is beyond what a real listing can hold."""
    total = 0
    for f in files:
        if f.size < 0:
            return None
        total += f.size
        if total > _MAX_TOTAL:
            return None
    return total
