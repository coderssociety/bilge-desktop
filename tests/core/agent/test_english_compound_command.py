import pytest

from bilge.core.agent.compound_command import has_dependent_parts, split
from bilge.core.language import AssistantLanguage

ENGLISH = AssistantLanguage.ENGLISH


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Open Safari and set the volume to 30", ["Open Safari", "set the volume to 30"]),
        ("Find Ahmet's number and then text him I'm late", ["Find Ahmet's number", "text him I'm late"]),
        ("Summarize the PDF, then copy the summary", ["Summarize the PDF", "copy the summary"]),
        ("Remind me to buy milk and bread", None),
        ("Text Ali and Veli that dinner is ready", None),
        ("What's the weather", None),
    ],
)
def test_splits_at_sequence_words_and_before_a_verb(text: str, expected: list[str] | None) -> None:
    assert split(text, language=ENGLISH) == expected


def test_later_parts_that_refer_to_an_earlier_result() -> None:
    assert has_dependent_parts(["Find Ahmet's number", "text him I'm late"], language=ENGLISH)
    assert has_dependent_parts(["Summarize the PDF", "copy the summary"], language=ENGLISH)
    assert not has_dependent_parts(["Open Safari", "set the volume to 30"], language=ENGLISH)
