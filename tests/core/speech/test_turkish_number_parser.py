import pytest

from bilge.core.speech import turkish_number_parser, turkish_time_of_day


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("üç yüz yirminin yarısı kaç", "320'nin yarısı kaç"),
        ("on iki çarpı on beş", "12 çarpı 15"),
        ("kırk beş dakikalık zamanlayıcı", "45 dakikalık zamanlayıcı"),
        ("sesi elliye getir", "sesi 50'ye getir"),
        ("iki bin yirmi altı yılı", "2026 yılı"),
        ("bin beş yüz lira", "1500 lira"),
        ("yüz yirmi beşin yüzde on sekizi", "125'in yüzde 18'i"),
        ("on dakika sonra", "10 dakika sonra"),
        ("üç milyon iki yüz bin", "3200000"),
        ("sesi yüzde otuz yap", "sesi yüzde 30 yap"),
        ("bin iki yüzün yüzde yirmisi ne kadar", "1200'ün yüzde 20'si ne kadar"),
    ],
)
def test_converts_spelled_out_numbers_to_digits_keeping_case_suffixes(text, expected):
    assert turkish_number_parser.digitize(text) == expected


@pytest.mark.parametrize(
    "text",
    ["bir not oluştur", "onu kapat", "ondan sonra müziği aç", "ona bir mesaj yaz", "masanın altında", "Safari'yi aç"],
)
def test_leaves_non_numeric_uses_alone(text):
    assert turkish_number_parser.digitize(text) == text


def test_bir_counts_when_part_of_a_larger_number_or_before_a_unit():
    assert turkish_number_parser.digitize("bir milyon") == "1000000"
    assert turkish_number_parser.digitize("bir dakika bekle") == "1 dakika bekle"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("akşam sekizde ilacımı hatırlat", "20:00'de ilacımı hatırlat"),
        ("Akşam sekizde ilacımı hatırlat", "20:00'de ilacımı hatırlat"),
        ("sabah yedide beni uyandır", "07:00'de beni uyandır"),
        ("öğleden sonra üç buçukta toplantı", "15:30'da toplantı"),
        ("gece on birde", "23:00'de"),
        ("gece ikide", "02:00'de"),
        ("öğlen on ikide", "12:00'de"),
        ("yarın sabah dokuz buçukta", "yarın 09:30'da"),
    ],
)
def test_time_of_day_resolves_part_of_day_expressions_to_24_hour_clock_times(text, expected):
    assert turkish_time_of_day.resolve(turkish_number_parser.digitize(text)) == expected


def test_time_of_day_leaves_text_without_a_part_of_day_unchanged():
    assert turkish_time_of_day.resolve("10 dakika sonra") == "10 dakika sonra"
