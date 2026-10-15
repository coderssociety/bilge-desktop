import pytest

from bilge.core import text
from bilge.core.language import AssistantLanguage


def test_lowercases_with_turkish_dotted_and_dotless_i():
    assert text.lowercased("IŞIK İZMİR") == "ışık izmir"


def test_normalizes_punctuation_and_whitespace():
    assert text.normalized("  Hey,   Asistan!  Saat kaç? ") == "hey asistan saat kaç"


@pytest.mark.parametrize("phrase", ["Safari'yi aç", "Safari’yi aç"])
def test_keeps_apostrophe_separated_suffixes_in_the_word(phrase):
    assert text.normalized(phrase) == "safariyi aç"


def test_folds_turkish_diacritics():
    assert text.folded("Çığ Şövalyesi Üzgün") == "cig sovalyesi uzgun"


def test_punctuation_only_input_is_empty():
    assert text.normalized("...!?") == ""


def test_similarity():
    assert text.similarity("bilge", "bilge") == 1
    assert text.similarity("", "") == 1
    assert text.similarity("bilge", "bilgi") == pytest.approx(0.8)


@pytest.mark.parametrize(
    ("name", "expected"),
    [("İstanbul", "İstanbul'da"), ("İzmir", "İzmir'de"), ("Paris", "Paris'te"), ("Kars", "Kars'ta")],
)
def test_locative(name, expected):
    assert text.locative(name) == expected


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [(10, 0, "10:00'da"), (11, 0, "11:00'de"), (13, 0, "13:00'te"), (15, 40, "15:40'ta"), (20, 0, "20:00'de")],
)
def test_time_locative(hour, minute, expected):
    assert text.time_locative(hour, minute) == expected


def test_preferred_language():
    assert AssistantLanguage.preferred(["en-US", "tr-TR"]) is AssistantLanguage.ENGLISH
    assert AssistantLanguage.preferred(["de_DE"]) is AssistantLanguage.TURKISH
