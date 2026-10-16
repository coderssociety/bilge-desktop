from datetime import UTC, datetime, timedelta

import httpx
import pytest

from bilge import update

PAGE = "https://github.com/coderssociety/bilge-desktop/releases/tag/v0.2.0"


def client_answering(status: int, body: object = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL(update.LATEST_URL)
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    ("published", "running", "newer"),
    [
        ("v0.2.0", "0.1.0", True),
        ("0.1.1", "0.1.0", True),
        ("v0.1.0", "0.1.0.dev0", True),
        ("v0.1.0", "0.1.0", False),
        ("v0.1.0", "0.2.0", False),
        ("v1.0.0rc1", "0.9.0", True),
        ("nightly", "0.1.0", False),
        ("v0.2.0", "unknown", False),
    ],
)
def test_compares_versions(published: str, running: str, newer: bool) -> None:
    assert update.is_newer(published, running) is newer


def test_offers_a_newer_release() -> None:
    client = client_answering(200, {"tag_name": "v0.2.0", "html_url": PAGE})
    assert update.newer_release("0.1.0", client) == update.Release("0.2.0", PAGE)


def test_says_nothing_when_up_to_date() -> None:
    client = client_answering(200, {"tag_name": "v0.2.0", "html_url": PAGE})
    assert update.newer_release("0.2.0", client) is None


def test_a_copy_without_a_version_is_never_told_to_update() -> None:
    assert update.newer_release(None, client_answering(500)) is None


def test_no_release_yet_is_not_an_error() -> None:
    assert update.latest_release(client_answering(404, {"message": "Not Found"})) is None


def test_refuses_a_page_outside_the_project() -> None:
    client = client_answering(200, {"tag_name": "v9.0.0", "html_url": "https://example.com/bilge.exe"})
    with pytest.raises(update.UpdateError):
        update.latest_release(client)


@pytest.mark.parametrize("body", [{"tag_name": "v1.0.0"}, ["not", "an", "object"], {"tag_name": None}])
def test_refuses_a_malformed_answer(body: object) -> None:
    with pytest.raises(update.UpdateError):
        update.latest_release(client_answering(200, body))


def test_reports_errors_from_github() -> None:
    with pytest.raises(update.UpdateError):
        update.latest_release(client_answering(403, {"message": "rate limited"}))

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(update.UpdateError):
        update.latest_release(httpx.Client(transport=httpx.MockTransport(unreachable)))


def test_asks_once_a_day(tmp_path) -> None:
    record = update.CheckRecord(tmp_path / "update.json")
    now = datetime(2026, 10, 16, 12, tzinfo=UTC)
    assert record.is_due(now)
    record.record(now, None)
    assert not record.is_due(now + timedelta(hours=23))
    assert record.is_due(now + timedelta(hours=25))
    # A clock set back a week must not stop the checks for a week.
    assert record.is_due(now - timedelta(days=7))


def test_remembers_a_newer_release_until_it_is_installed(tmp_path) -> None:
    record = update.CheckRecord(tmp_path / "update.json")
    record.record(datetime.now(UTC), update.Release("0.2.0", PAGE))
    assert record.found("0.1.0") == update.Release("0.2.0", PAGE)
    assert record.found("0.2.0") is None
    assert record.found(None) is None


def test_a_remembered_page_outside_the_project_is_not_offered(tmp_path) -> None:
    path = tmp_path / "update.json"
    path.write_text('{"checked": "2026-10-16T12:00:00+00:00", "newer": {"version": "9.0", "url": "https://x.example"}}')
    assert update.CheckRecord(path).found("0.1.0") is None


@pytest.mark.parametrize("content", ["{not json", "[]", '{"checked": 5, "newer": "x"}'])
def test_a_damaged_record_means_checking_again(tmp_path, content: str) -> None:
    path = tmp_path / "update.json"
    path.write_text(content, encoding="utf-8")
    record = update.CheckRecord(path)
    assert record.is_due(datetime.now(UTC))
    assert record.found("0.1.0") is None


@pytest.mark.parametrize(
    ("page", "accepted"),
    [
        (PAGE, True),
        ("https://github.com/coderssociety/bilge-desktop/releases/../../evil/repo", False),
        ("https://github.com/coderssociety/bilge-desktop/releases/%2e%2e/%2e%2e/evil", False),
        ("https://github.com/coderssociety/bilge-desktop/releases/tag/v1/..", False),
        ("http://github.com/coderssociety/bilge-desktop/releases/tag/v1", False),
    ],
)
def test_only_this_projects_release_pages_are_opened(page: str, accepted: bool) -> None:
    assert update.is_project_page(page) is accepted
