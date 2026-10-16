import pytest

from bilge.core.web import news_article
from bilge.core.web.news_article import Request
from bilge.core.web.rss_headlines import Item

READING = [
    Item(title, f"https://www.aa.com.tr/tr/haber/{n}")
    for n, title in enumerate([
        "Şanlıurfa'da TEKNOFEST Güneydoğu'da finale yükselen takımlar ödüllendirildi",
        'Tesla, "havada ilerlemek için yüksek basınçlı hava tankları" kullanılan yeni aracını tanıttı',
        "Meta'nın iş ilanı algoritmasındaki ayrımcılık Hollanda'da tescillendi",
        "Claude'un \"keşfettiği\" buluş üzerinde yıllardır çalışan biyolog, otonom keşif tanımına şüpheyle yaklaşıyor",
        "Telegram'a yeni özellikler geldi, Claude Code'a da güncelleme",
    ])
]  # fmt: skip


def find(command: str) -> Request | None:
    return news_article.find(command, READING, READING)


@pytest.mark.parametrize(
    ("command", "index", "in_browser"),
    [
        ("Cloud'un keşfettiği buluşu açar mısın", 3, True),
        ("Tesla'nın yeni aracı haberini anlat", 1, False),
        ("Meta'daki ayrımcılık haberinin detayı ne", 2, False),
        ("tell me more about the Tesla news", 1, False),
    ],
)
def test_finds_a_headline_by_its_words_even_misheard(command: str, index: int, in_browser: bool) -> None:
    assert find(command) == Request(READING[index], in_browser)


@pytest.mark.parametrize(
    ("command", "index"),
    [
        ("üçüncü haberi aç", 2),
        ("ikincisini anlat", 1),
        ("sonuncusunu oku", 4),
        ("ilk haberin detayı", 0),
        ("open the second one", 1),
    ],
)
def test_finds_a_headline_by_its_place_in_the_last_reading(command: str, index: int) -> None:
    found = find(command)
    assert found is not None and found.item == READING[index]


@pytest.mark.parametrize(
    "command",
    [
        "Telegram'ı aç",
        "Safari'yi aç",
        "ikinci sekmeyi aç",
        "Teknoloji haberlerini oku",
        "son haberleri oku",
        "Bu kadar mı",
        "ilkbahar haberini aç",
        "Tesla",
        "open the last tab",
        "open the second app",
        "Claude Code'u aç",
    ],
)
def test_leaves_requests_that_dont_point_at_a_headline_to_the_other_tools(command: str) -> None:
    assert find(command) is None


def test_finds_nothing_before_any_news_was_read() -> None:
    assert news_article.find("üçüncü haberi aç", [], []) is None


def test_the_models_words_need_no_open_or_tell_word() -> None:
    found = news_article.find("üçüncü", READING, READING, asked=True)
    assert found is not None and found.item == READING[2]
