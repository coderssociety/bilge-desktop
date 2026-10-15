"""Downloads model files from Hugging Face at a pinned commit and checks every file before it is used.

Large files are checked against the SHA-256 Hugging Face publishes, small ones against their git blob hash,
and a model only appears in its final folder once every file is in place, so a half-finished download is never
loaded.
"""

import hashlib
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from bilge.core.models import repository
from bilge.core.models.repository import RepositoryFile

HOST = "https://huggingface.co"
# Kept free beyond the download itself, so the computer does not run out of space.
SPARE_BYTES = 1_000_000_000
_CHUNK = 1 << 20
_TIMEOUT = httpx.Timeout(60.0, connect=15.0)


@dataclass(frozen=True)
class ModelSpec:
    repo_id: str
    revision: str
    patterns: tuple[str, ...]
    # Folder name under the models folder; several specs may share a repository with different files.
    name: str


class DownloadError(Exception):
    """The message is shown to the user."""


class DownloadCancelled(Exception):
    pass


Progress = Callable[[int, int], None]


class Downloader:
    def __init__(self, models_dir: Path, client: httpx.Client | None = None):
        self.models_dir = models_dir
        self._client = client or httpx.Client(timeout=_TIMEOUT, follow_redirects=True)

    def folder(self, spec: ModelSpec) -> Path:
        return self.models_dir / spec.name

    def is_downloaded(self, spec: ModelSpec) -> bool:
        return self.folder(spec).is_dir()

    def partial_folder(self, spec: ModelSpec) -> Path:
        return self.models_dir / f".{spec.name}.partial"

    def download(
        self, spec: ModelSpec, progress: Progress | None = None, cancelled: Callable[[], bool] = lambda: False
    ) -> Path:
        if not repository.is_valid_id(spec.repo_id) or not repository.is_pinned_revision(spec.revision):
            raise DownloadError(f"Invalid model: {spec.repo_id}@{spec.revision}")
        files = repository.select(self._list(spec), spec.patterns)
        if not files:
            raise DownloadError(f"Nothing to download in {spec.repo_id}")
        total = repository.total_size(files)
        if total is None:
            raise DownloadError(f"{spec.repo_id} lists impossible file sizes")
        partial = self.partial_folder(spec)
        partial.mkdir(parents=True, exist_ok=True)
        self._check_space(total - sum(f.size for f in files if _is_complete(partial / f.path, f)), partial)
        done = 0
        for file in files:
            target = partial / file.path
            if not _is_complete(target, file):
                self._fetch(
                    spec,
                    file,
                    target,
                    lambda received, base=done: progress and progress(base + received, total),
                    cancelled,
                )
            done += file.size
            if progress:
                progress(done, total)
        final = self.folder(spec)
        if final.exists():
            shutil.rmtree(final)
        partial.rename(final)
        return final

    def _list(self, spec: ModelSpec) -> list[RepositoryFile]:
        url = f"{HOST}/api/models/{spec.repo_id}/tree/{spec.revision}"
        try:
            response = self._client.get(url, params={"recursive": "true"})
        except httpx.HTTPError as error:
            raise DownloadError(f"Could not reach Hugging Face: {error}") from error
        if response.status_code != 200:
            raise DownloadError(f"Could not list {spec.repo_id} ({response.status_code})")
        try:
            return repository.parse_tree(response.json())
        except ValueError as error:
            raise DownloadError(f"Unexpected listing for {spec.repo_id}") from error

    def _fetch(
        self,
        spec: ModelSpec,
        file: RepositoryFile,
        target: Path,
        received: Callable[[int], None],
        cancelled: Callable[[], bool],
    ) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".download")
        hasher = _hasher(file)
        count = 0
        url = f"{HOST}/{spec.repo_id}/resolve/{spec.revision}/{file.path}"
        try:
            with self._client.stream("GET", url) as response, temporary.open("wb") as out:
                if response.status_code != 200:
                    raise DownloadError(f"Could not download {file.path} ({response.status_code})")
                for chunk in response.iter_bytes(_CHUNK):
                    if cancelled():
                        raise DownloadCancelled
                    count += len(chunk)
                    if count > file.size:
                        raise DownloadError(f"{file.path} is larger than listed")
                    hasher.update(chunk)
                    out.write(chunk)
                    received(count)
        except httpx.HTTPError as error:
            temporary.unlink(missing_ok=True)
            raise DownloadError(f"Could not download {file.path}: {error}") from error
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        if count != file.size or not _matches(hasher, file):
            temporary.unlink(missing_ok=True)
            raise DownloadError(f"{file.path} arrived damaged; try again")
        temporary.replace(target)

    def _check_space(self, needed: int, folder: Path) -> None:
        free = shutil.disk_usage(folder).free
        if free < needed + SPARE_BYTES:
            raise DownloadError(f"Not enough disk space: {(needed + SPARE_BYTES) / 1e9:.1f} GB needed")


def _hasher(file: RepositoryFile):
    if file.lfs_sha256:
        return hashlib.sha256()
    hasher = hashlib.sha1()  # noqa: S324 - git's blob id, used to check integrity only
    hasher.update(f"blob {file.size}\0".encode())
    return hasher


def _matches(hasher, file: RepositoryFile) -> bool:
    expected = file.lfs_sha256 or file.git_oid
    return expected is not None and hasher.hexdigest() == expected


def _is_complete(path: Path, file: RepositoryFile) -> bool:
    """A file left by an interrupted download counts only when its size and hash are right."""
    try:
        if path.stat().st_size != file.size:
            return False
        hasher = _hasher(file)
        with path.open("rb") as source:
            while chunk := source.read(_CHUNK):
                hasher.update(chunk)
        return _matches(hasher, file)
    except OSError:
        return False
