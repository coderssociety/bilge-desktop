import pytest

from bilge.core.dictation.dictation_command import DictationCommand, is_start, parse
from bilge.core.dictation.dictation_text import format as format_dictation
from bilge.core.language import AssistantLanguage

ENGLISH = AssistantLanguage.ENGLISH


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("New line", DictationCommand.NEW_LINE),
        ("New paragraph", DictationCommand.NEW_PARAGRAPH),
        ("Scratch that", DictationCommand.DELETE_LAST),
        ("Delete the last sentence", DictationCommand.DELETE_LAST),
        ("Stop dictation", DictationCommand.FINISH),
        ("I'm done", DictationCommand.FINISH),
        ("Delete that file from my desktop", None),
        ("A new line of products", None),
    ],
)
def test_whole_utterance_controls(text: str, expected: DictationCommand | None) -> None:
    assert parse(text, language=ENGLISH) is expected


def test_starting_dictation() -> None:
    assert is_start("Start dictation", language=ENGLISH)
    assert is_start("Turn on dictation mode", language=ENGLISH)
    assert not is_start("Start the timer", language=ENGLISH)


def test_spoken_punctuation_and_capitals() -> None:
    assert format_dictation("hello comma how are you question mark", after=None, language=ENGLISH) == (
        "Hello, how are you?"
    )
    assert format_dictation("it is ready period", after="Okay.", language=ENGLISH) == " It is ready."
    assert format_dictation("i think so", after=None, language=ENGLISH) == "I think so"
    assert format_dictation("see you open quote soon close quote", after="Bye", language=ENGLISH) == ' see you "soon"'
