import pytest

from bilge.core import text
from bilge.core.web import html_text, rss_headlines, weather_report


def test_weather_sentences() -> None:
    assert (
        weather_report.current(city="İstanbul", temperature=17.6, code=2)
        == "İstanbul'da şu an hava parçalı bulutlu, 18 derece."
    )
    assert (
        weather_report.daily(city="Ankara", day_name="yarın", minimum=4.2, maximum=12.5, code=63, rain_chance=80)
        == "Ankara'da yarın hava yağmurlu, sıcaklık 4 ile 13 derece arasında. Yağış ihtimali yüzde 80."
    )
    assert "Yağış" not in weather_report.daily(
        city="İzmir", day_name="bugün", minimum=20, maximum=28, code=0, rain_chance=10
    )


def test_page_text_drops_scripts_styles_and_tags_and_decodes_entities() -> None:
    page = """<html><head><title>Haber &amp; Yorum</title><style>p{color:red}</style></head>
<body><nav>Menü</nav><script>alert('x')</script><h1>Başlık</h1><p>Birinci&nbsp;paragraf &#8220;alıntı&#8221;.</p>
<p>İkinci <b>kalın</b> paragraf.</p><footer>Telif</footer></body></html>"""
    assert html_text.extract(page) == "Başlık\nBirinci paragraf “alıntı”.\nİkinci kalın paragraf."
    assert html_text.title(page) == "Haber & Yorum"


def test_rss_item_titles_skipping_the_channel_title() -> None:
    feed = """<?xml version="1.0"?><rss><channel><title>Kanal</title>
<item><title><![CDATA[Birinci haber]]></title></item>
<item><title>İkinci haber</title></item>
<item><title>Üçüncü haber</title></item>
</channel></rss>"""
    assert rss_headlines.parse(feed.encode(), limit=2) == ["Birinci haber", "İkinci haber"]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("İstanbul", "İstanbul'da"),
        ("Ankara", "Ankara'da"),
        ("İzmir", "İzmir'de"),
        ("Paris", "Paris'te"),
        ("Kars", "Kars'ta"),
        ("Berlin", "Berlin'de"),
        ("Tokyo", "Tokyo'da"),
        ("Muş", "Muş'ta"),
        ("Köln", "Köln'de"),
    ],
)
def test_locative_suffix_follows_vowel_harmony_and_hard_consonants(name: str, expected: str) -> None:
    assert text.locative(name) == expected
