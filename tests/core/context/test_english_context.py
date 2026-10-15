import pytest

from bilge.core.context import context_intent
from bilge.core.context.context_intent import Action, ContextIntent, Kind
from bilge.core.language import AssistantLanguage

ENGLISH = AssistantLanguage.ENGLISH


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("Summarize this", ContextIntent(action=Action.SUMMARIZE, wanted=None)),
        ("Translate the selected text", ContextIntent(action=Action.TRANSLATE, wanted=Kind.TEXT)),
        ("What does this error mean", ContextIntent(action=Action.EXPLAIN, wanted=None)),
        ("Open this file", ContextIntent(action=Action.OPEN, wanted=Kind.FILE)),
        ("Read this page to me", ContextIntent(action=Action.READ, wanted=Kind.PAGE)),
        ("Give me a summary of this article", ContextIntent(action=Action.SUMMARIZE, wanted=Kind.PAGE)),
        ("Explain the highlighted paragraph", ContextIntent(action=Action.EXPLAIN, wanted=Kind.TEXT)),
        ("What's on this evening", None),
        ("Play this song", None),
        ("Open Safari", None),
    ],
)
def test_requests_about_what_is_on_screen(command, expected):
    assert context_intent.parse(command, language=ENGLISH) == expected


def test_pointing():
    assert context_intent.points("Send this to Ahmet", language=ENGLISH)
    assert not context_intent.points("What are you doing this weekend", language=ENGLISH)
    assert not context_intent.points("Send Ahmet a message", language=ENGLISH)


def test_message_bodies_that_only_point():
    assert context_intent.only_points("this", language=ENGLISH)
    assert context_intent.only_points("that link", language=ENGLISH)
    assert context_intent.only_points("the file", language=ENGLISH) is False
    assert not context_intent.only_points("I'll be late", language=ENGLISH)
    assert context_intent.wanted_kind("this link", language=ENGLISH) == Kind.PAGE
