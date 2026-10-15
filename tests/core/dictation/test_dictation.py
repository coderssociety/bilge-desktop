import pytest

from bilge.core.dictation.dictation_command import DictationCommand, is_start, parse
from bilge.core.dictation.dictation_text import format as format_dictation


@pytest.mark.parametrize("text", ["Dikte modunu başlat", "dikte başlat", "Dikteye başla", "Yazdırmaya başlayalım"])
def test_starting_dictation(text: str) -> None:
    assert is_start(text)


@pytest.mark.parametrize("text", ["Şunu yaz merhaba", "Dikte nedir", "yarın hava nasıl"])
def test_not_a_request_to_start_dictation(text: str) -> None:
    assert not is_start(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("yeni satır", DictationCommand.NEW_LINE),
        ("Alt satıra geç", DictationCommand.NEW_LINE),
        ("yeni paragraf", DictationCommand.NEW_PARAGRAPH),
        ("son cümleyi sil", DictationCommand.DELETE_LAST),
        ("Sonuncuyu sil", DictationCommand.DELETE_LAST),
        ("geri al", DictationCommand.DELETE_LAST),
        ("dikteyi bitir", DictationCommand.FINISH),
        ("Dikte bitti", DictationCommand.FINISH),
        ("tamam bitti", DictationCommand.FINISH),
    ],
)
def test_commands_inside_dictation(text: str, expected: DictationCommand) -> None:
    assert parse(text) is expected


@pytest.mark.parametrize("text", ["yeni bir satır alalım dedi", "sil baştan başladık"])
def test_ordinary_speech_is_text_not_a_command(text: str) -> None:
    assert parse(text) is None


@pytest.mark.parametrize(
    ("spoken", "previous", "expected"),
    [
        ("merhaba virgül nasılsın soru işareti", None, "Merhaba, nasılsın?"),
        ("toplantı yarın nokta", "Merhaba.", " Toplantı yarın."),
        ("ve bütçe onaylandı", "Toplantı yarın", " ve bütçe onaylandı"),
        ("Fiyatlar şöyle iki nokta", None, "Fiyatlar şöyle:"),
        ("tırnak aç selam tırnak kapat dedi", None, '"selam" dedi'),
        ("yeni başlık", "Satır\n", "Yeni başlık"),
        ("Zaten noktalı.", "Önceki.", " Zaten noktalı."),
    ],
)
def test_spoken_punctuation_spacing_and_capitals(spoken: str, previous: str | None, expected: str) -> None:
    assert format_dictation(spoken, after=previous) == expected
