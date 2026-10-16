import pytest

from bilge.core.speech.hallucinations import is_made_up, without_made_up


@pytest.mark.parametrize(
    "text",
    [
        "Altyazı M.K.",
        "altyazı m.k",
        "Altyazı: Ahmet Yılmaz",
        "ALTYAZI: M.K.",
        "İzlediğiniz için teşekkür ederim.",
        "Abone olmayı unutmayın!",
        "Thanks for watching!",
        "Thank you for watching.",
        "Subtitles by the Amara.org community",
        "Transcribed by ESO, translated by —",
        "you",
        "You.",
    ],
)
def test_recognises_the_closing_lines_whisper_invents(text: str) -> None:
    assert is_made_up(text)
    assert without_made_up(text) == ""


@pytest.mark.parametrize(
    "text",
    [
        "Teşekkürler.",
        "Thank you.",
        "Altyazıyı aç",
        "altyazı aç",
        "Bilge, çeviri yap",
        "Bilge, YouTube'da izlediğim videoyu aç",
        "you know what time it is",
        "Subscribe me to the newsletter",
    ],
)
def test_keeps_what_people_actually_say(text: str) -> None:
    assert without_made_up(text) == text


def test_drops_only_the_invented_sentence() -> None:
    assert without_made_up("Bilge, saat kaç? Altyazı M.K.") == "Bilge, saat kaç?"
    assert without_made_up("Thanks for watching! Bilge, stop.") == "Bilge, stop."


def test_empty_stays_empty() -> None:
    assert without_made_up("   ") == ""
