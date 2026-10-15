import pytest

from bilge.core.speech import turkish_number_words, turkish_speech_normalizer


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "sıfır"),
        (7, "yedi"),
        (10, "on"),
        (15, "on beş"),
        (100, "yüz"),
        (101, "yüz bir"),
        (1000, "bin"),
        (1001, "bin bir"),
        (2026, "iki bin yirmi altı"),
        (17_350, "on yedi bin üç yüz elli"),
        (1_000_000, "bir milyon"),
        (2_500_000_000, "iki milyar beş yüz milyon"),
        (-4, "eksi dört"),
    ],
)
def test_cardinal_numbers(value: int, expected: str) -> None:
    assert turkish_number_words.cardinal(value) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Saat 14:30", "Saat on dört otuz"),
        ("Saat 09:05'te", "Saat dokuz sıfır beşte"),
        ("Saat 14.30'da", "Saat on dört otuzda"),
        ("Pil %25 dolu", "Pil yüzde yirmi beş dolu"),
        ("Sıcaklık 3,5 °C", "Sıcaklık üç virgül beş derece"),
        ("Toplam 1.250 TL", "Toplam bin iki yüz elli lira"),
        ("Fiyatı 99₺", "Fiyatı doksan dokuz lira"),
        ("1 $ kaç lira", "bir dolar kaç lira"),
        ("Bilet 40€", "Bilet kırk avro"),
        ("3 toplantın var", "üç toplantın var"),
        ("13.10.2026 tarihinde", "on üç ekim iki bin yirmi altı tarihinde"),
    ],
)
def test_verbalizes_text_for_speech(text: str, expected: str) -> None:
    assert turkish_speech_normalizer.normalize(text) == expected


def test_strips_markdown_that_would_be_read_aloud() -> None:
    assert turkish_speech_normalizer.normalize("**Önemli:** `ls` komutu") == "Önemli: ls komutu"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("En bilinen romanı *Kürk Mantolu Madonna*.", "En bilinen romanı Kürk Mantolu Madonna."),
        ("Ankara başkent oldu. 🇹🇷", "Ankara başkent oldu."),
        ("Mona Lisa'yı Leonardo da Vinci çizdi. 🎨😊", "Mona Lisa'yı Leonardo da Vinci çizdi."),
        ("Teşekkürler ❤️ görüşürüz 👨‍👩‍👧", "Teşekkürler görüşürüz"),
        ("dosya_adi.txt hazır", "dosya_adi.txt hazır"),
        ("7 * 24 eder", "yedi * yirmi dört eder"),
        ("3*(4+5) kaç", "üç*(dört+beş) kaç"),
        ("_önemli_ not", "önemli not"),
    ],
)
def test_strips_emphasis_and_emoji_but_keeps_word_internal_symbols(text: str, expected: str) -> None:
    assert turkish_speech_normalizer.normalize(text) == expected
