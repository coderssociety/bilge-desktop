import hashlib
import json

import httpx
import pytest

from bilge.models.downloader import DownloadCancelled, Downloader, DownloadError, ModelSpec

REV = "a" * 40
SMALL = b'{"sample_rate": 44100}'
BIG = b"\x01" * 3000


def git_oid(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


LISTING = [
    {"type": "file", "path": "onnx/tts.json", "size": len(SMALL), "oid": git_oid(SMALL)},
    {"type": "file", "path": "onnx/vocoder.onnx", "size": len(BIG), "oid": "x",
     "lfs": {"oid": hashlib.sha256(BIG).hexdigest(), "size": len(BIG)}},
    {"type": "file", "path": "README.md", "size": 3, "oid": "r"},
]  # fmt: skip
SPEC = ModelSpec("Supertone/supertonic-3", REV, ("onnx/*",), "supertonic-3")


def server(files=None, requests=None):
    files = files or {"onnx/tts.json": SMALL, "onnx/vocoder.onnx": BIG}

    def handler(request):
        if requests is not None:
            requests.append(request.url.path)
        if "/api/models/" in request.url.path:
            return httpx.Response(200, json=LISTING)
        name = request.url.path.split(f"/resolve/{REV}/")[1]
        return httpx.Response(200, content=files[name])

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_downloads_only_the_wanted_files_and_reports_progress(tmp_path):
    seen = []
    folder = Downloader(tmp_path, server()).download(SPEC, progress=lambda done, total: seen.append((done, total)))
    assert (folder / "onnx" / "vocoder.onnx").read_bytes() == BIG
    assert not (folder / "README.md").exists()
    assert seen[-1] == (len(SMALL) + len(BIG), len(SMALL) + len(BIG))
    assert Downloader(tmp_path, server()).is_downloaded(SPEC)


def test_a_damaged_file_is_rejected_and_nothing_appears(tmp_path):
    damaged = server({"onnx/tts.json": SMALL, "onnx/vocoder.onnx": b"\x02" * 3000})
    with pytest.raises(DownloadError, match="damaged"):
        Downloader(tmp_path, damaged).download(SPEC)
    assert not Downloader(tmp_path, damaged).is_downloaded(SPEC)


def test_an_interrupted_download_resumes_without_fetching_good_files_again(tmp_path):
    downloader = Downloader(tmp_path, server())
    partial = downloader.partial_folder(SPEC) / "onnx"
    partial.mkdir(parents=True)
    (partial / "vocoder.onnx").write_bytes(BIG)
    requests = []
    Downloader(tmp_path, server(requests=requests)).download(SPEC)
    assert not any(path.endswith("vocoder.onnx") for path in requests)


def test_cancelling_leaves_no_half_file(tmp_path):
    with pytest.raises(DownloadCancelled):
        Downloader(tmp_path, server()).download(SPEC, cancelled=lambda: True)
    assert not list(tmp_path.rglob("*.download"))


def test_unpinned_or_odd_models_are_refused(tmp_path):
    for spec in [ModelSpec("Supertone/supertonic-3", "main", ("*",), "x"), ModelSpec("../x", REV, ("*",), "x")]:
        with pytest.raises(DownloadError, match="Invalid model"):
            Downloader(tmp_path, server()).download(spec)


def test_a_file_larger_than_listed_is_refused(tmp_path):
    with pytest.raises(DownloadError, match="larger than listed"):
        Downloader(tmp_path, server({"onnx/tts.json": SMALL + b"x" * 10, "onnx/vocoder.onnx": BIG})).download(SPEC)


def test_listing_is_json_checked(tmp_path):
    def handler(request):
        return httpx.Response(200, content=json.dumps({"error": "no"}))

    with pytest.raises(DownloadError, match="Nothing to download"):
        Downloader(tmp_path, httpx.Client(transport=httpx.MockTransport(handler))).download(SPEC)
