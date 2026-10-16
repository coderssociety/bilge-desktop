from datetime import datetime, timedelta

import pytest

from bilge.core.web import news_request
from bilge.core.web.news_request import HeadlineMemory, Kind, Reading
from bilge.core.web.rss_headlines import Item

START = datetime(2026, 10, 16, 20, 0)
FEED = [Item(f"Başlık {n}", None) for n in range(1, 13)]


@pytest.mark.parametrize(
    ("command", "topic"),
    [
        ("Teknoloji haberlerinden başlık var mı", "technology"),
        ("bilim dünyasından ne var", "technology"),
        ("Ekonomi haberleri", "economy"),
        ("borsada bugün ne oldu", "economy"),
        ("Spor haberlerini oku", "sports"),
        ("dünyadan haberler", "world"),
        ("What's new in tech?", "technology"),
        ("latest business news", "economy"),
        ("gündemde ne var", "general"),
        ("Bugünün önemli haberleri var mı", None),
    ],
)
def test_reads_the_topic_from_the_command(command: str, topic: str | None) -> None:
    assert news_request.topic(command) == topic


@pytest.mark.parametrize(
    ("command", "continues"),
    [
        ("Bu kadar mı", True),
        ("başka var mı", True),
        ("Is that all?", True),
        ("Bugünün önemli haberleri var mı", False),
        ("son başlıklar", False),
        ("spor", False),
    ],
)
def test_a_follow_up_without_news_words_or_a_topic_continues(command: str, continues: bool) -> None:
    assert news_request.is_continuation(command) is continues


def test_asking_again_goes_on_with_the_headlines_not_yet_read() -> None:
    memory = HeadlineMemory()
    assert memory.next(FEED, "general", 5, START) == Reading(FEED[:5], Kind.FIRST)
    assert memory.next(FEED, "general", 5, START + timedelta(seconds=30)) == Reading(FEED[5:10], Kind.NEXT)


def test_a_newer_headline_at_the_top_is_read_first() -> None:
    memory = HeadlineMemory()
    memory.next(FEED, "general", 5, START)
    newer = Item("Yeni", None)
    assert memory.next([newer, *FEED], "general", 5, START + timedelta(minutes=1)).items == [newer, *FEED[5:9]]


def test_with_nothing_new_the_latest_are_read_again_and_said_to_be_the_same() -> None:
    memory = HeadlineMemory()
    memory.next(FEED[:3], "general", 5, START)
    assert memory.next(FEED[:3], "general", 5, START + timedelta(seconds=10)) == Reading(FEED[:3], Kind.AGAIN)


def test_topics_are_remembered_apart_and_the_memory_fades() -> None:
    memory = HeadlineMemory()
    memory.next(FEED, "general", 5, START)
    assert memory.next(FEED, "technology", 5, START).items == FEED[:5]
    later = START + news_request.LIFETIME + timedelta(seconds=1)
    assert memory.next(FEED, "general", 5, later) == Reading(FEED[:5], Kind.FIRST)


def test_the_topic_just_read_is_remembered_for_a_follow_up_for_a_few_minutes() -> None:
    memory = HeadlineMemory()
    memory.next(FEED, "technology", 5, START)
    assert memory.recent_topic(START + timedelta(minutes=1)) == "technology"
    assert memory.recent_topic(START + news_request.CONTINUATION_WINDOW + timedelta(seconds=1)) is None


def test_what_was_read_is_kept_for_a_request_about_one_of_the_headlines_the_last_reading_first() -> None:
    memory = HeadlineMemory()
    memory.next(FEED, "general", 2, START)
    memory.next(FEED, "general", 2, START + timedelta(seconds=10))
    assert memory.heard_items(START + timedelta(seconds=20)) == (FEED[2:4], [*FEED[2:4], *FEED[:2]])
    assert memory.heard_items(START + news_request.LIFETIME + timedelta(seconds=11)) == ([], [])
