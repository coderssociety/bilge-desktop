import pytest

from bilge.core.wake.wake_phrase_matcher import WakePhraseMatcher

matcher = WakePhraseMatcher("Asistan")


@pytest.mark.parametrize(
    ("transcript", "command"),
    [
        ("Asistan, Safari'yi aç.", "Safari'yi aç."),
        ("hey asistan saat kaç", "saat kaç"),
        ("Asistanım müziği durdur", "müziği durdur"),
        ("asisstan sesi kıs", "sesi kıs"),
        ("A sistan, ekranı kilitle", "ekranı kilitle"),
        ("Şey, asistan, pil durumu nedir?", "pil durumu nedir?"),
    ],
)
def test_matches_the_phrase_at_the_start_and_returns_the_command_after_it(transcript: str, command: str) -> None:
    match = matcher.match(transcript)
    assert match is not None
    assert match.command == command


def test_a_bare_wake_phrase_matches_with_an_empty_command() -> None:
    match = matcher.match("Asistan?")
    assert match is not None
    assert match.command == ""


@pytest.mark.parametrize(
    "transcript",
    ["Bugün asistan olarak işe başladım", "İstanbul'a gidiyorum", "Asansör yine bozulmuş", ""],
)
def test_does_not_trigger_on_unrelated_speech(transcript: str) -> None:
    assert matcher.match(transcript) is None


def test_supports_custom_names_and_multi_word_phrases() -> None:
    assert WakePhraseMatcher("Defne").match("Hey Defne ışıkları kapat").command == "ışıkları kapat"
    assert WakePhraseMatcher("Hey Defne").match("hey defne saat kaç").command == "saat kaç"


def test_stricter_sensitivity_rejects_near_misses() -> None:
    strict = WakePhraseMatcher("Asistan", minimum_similarity=0.95)
    assert strict.match("asisstan sesi kıs") is None
    assert strict.match("asistan sesi kıs") is not None


def test_short_wake_words_allow_suffixes_but_no_misspellings() -> None:
    bilge = WakePhraseMatcher("Bilge")
    assert bilge.match("Bilge, saat kaç").command == "saat kaç"
    assert bilge.match("hey bilge müziği aç").command == "müziği aç"
    assert bilge.match("Bilgeciğim, sesi kıs").command == "sesi kıs"
    assert bilge.match("Bilgi almak istiyorum") is None
    assert bilge.match("Bilgisayarı kapat") is None
    assert bilge.match("Bilgin olsun yarın geliyorum") is None
