import pytest

from bilge.core.language import AssistantLanguage
from bilge.core.memory.memory_intent import (
    ForgetAll,
    ForgetLatest,
    ForgetMatching,
    ForgetTarget,
    MemoryIntent,
    fact,
    forget_target,
    parse,
)

ENGLISH = AssistantLanguage.ENGLISH


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("Remember that my wife's birthday is in May", MemoryIntent.REMEMBER),
        ("Please remember I take my coffee black", MemoryIntent.REMEMBER),
        ("Don't forget that the door code is 4512", MemoryIntent.REMEMBER),
        ("Keep in mind that I'm vegetarian", MemoryIntent.REMEMBER),
        ("What do you remember about me", MemoryIntent.LIST),
        ("What do you know about me", MemoryIntent.LIST),
        ("Show me your memory", MemoryIntent.LIST),
        ("Forget that", MemoryIntent.FORGET),
        ("Forget my coffee order", MemoryIntent.FORGET),
        ("Clear your memory", MemoryIntent.FORGET),
        ("Remind me to call mom", None),
        ("Remind me tomorrow that I have to remember the keys", None),
        ("What's the weather", None),
    ],
)
def test_recognizes_memory_requests(command: str, expected: MemoryIntent | None) -> None:
    assert parse(command, language=ENGLISH) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("Remember that my wife's birthday is in May", "my wife's birthday is in May"),
        ("Please remember: I take my coffee black.", "I take my coffee black"),
        ("Don't forget the door code is 4512", "the door code is 4512"),
        ("Remember this", None),
        ("Remember that", None),
    ],
)
def test_extracts_the_fact(command: str, expected: str | None) -> None:
    assert fact(command, language=ENGLISH) == expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("Forget everything", ForgetAll()),
        ("Clear your memory", ForgetAll()),
        ("Forget it all", ForgetAll()),
        ("Forget that", ForgetLatest()),
        ("Forget my coffee order", ForgetMatching("my coffee order")),
        ("Please forget what I told you about the door code", ForgetMatching("door code")),
    ],
)
def test_what_to_forget(command: str, expected: ForgetTarget) -> None:
    assert forget_target(command, language=ENGLISH) == expected
