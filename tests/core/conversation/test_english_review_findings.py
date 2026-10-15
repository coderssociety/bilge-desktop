"""Cases a review found: each English rule must leave ordinary requests alone and never read hesitation as yes.
The route guard cases are not ported (that module is not); the spreadsheet case lives with the spreadsheet tests."""

from datetime import UTC, datetime, timedelta

import pytest

from bilge.core.agent import compound_command
from bilge.core.browser import browser_command
from bilge.core.context import context_intent
from bilge.core.conversation import confirmation_parser
from bilge.core.conversation.confirmation_parser import Answer
from bilge.core.conversation.conversation_flow import ConversationFlow, RunWorkInput, WorkSession
from bilge.core.dictation import dictation_command
from bilge.core.dictation.dictation_command import DictationCommand
from bilge.core.language import AssistantLanguage
from bilge.core.tools import english_time_parser
from bilge.core.wake.wake_phrase_matcher import WakePhraseMatcher

ENGLISH = AssistantLanguage.ENGLISH


@pytest.mark.parametrize("text", ["I'm not sure", "not ok", "not yet", "please wait", "hold on", "maybe later"])
def test_hesitation_is_not_a_yes(text):
    assert confirmation_parser.parse(text, language=ENGLISH) != Answer.CONFIRMED


@pytest.mark.parametrize(
    "text",
    [
        "volume up",
        "volume down",
        "shut down",
        "what's up",
        "forward it to Sam",
        "call me back",
        "top stories",
        "turn it up",
    ],
)
def test_browser_rules_leave_ordinary_commands_alone(text):
    assert browser_command.parse(text, language=ENGLISH) is None


def test_screen_context_only_when_the_pointer_is_the_object():
    assert not context_intent.points("Tell Ali that I'm late", language=ENGLISH)
    assert context_intent.points("Send this to Ali", language=ENGLISH)
    assert context_intent.points("What does this link say", language=ENGLISH)
    assert context_intent.parse("Remind me to read this", language=ENGLISH) is None
    assert context_intent.parse("Open this evening's calendar", language=ENGLISH) is None


def test_a_reminders_content_is_not_split_into_commands():
    assert compound_command.split("Remind me to call the bank and send the invoice", language=ENGLISH) is None
    assert compound_command.split("Open Safari and then set the volume to 30", language=ENGLISH) == [
        "Open Safari",
        "set the volume to 30",
    ]


def test_dictation_off_is_not_a_start():
    assert not dictation_command.is_start("Turn off dictation", language=ENGLISH)
    assert dictation_command.parse("Turn off dictation", language=ENGLISH) == DictationCommand.FINISH


def test_dictated_stop_words_are_text_inside_a_work_session():
    flow = ConversationFlow(WakePhraseMatcher("bilge"))
    now = datetime.now(UTC)
    flow.heard("Bilge start dictation", at=now)
    flow.response_finished(at=now, allow_follow_up=True, session=WorkSession(window=60, accepts=lambda _: True))
    assert flow.heard("Nothing.", at=now + timedelta(seconds=1)) == RunWorkInput("Nothing.")


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("twenty five minutes", 1500), ("ninety minutes", 5400), ("an hour and a half", 5400), ("seventeen seconds", 17)],
)
def test_english_durations(text, seconds):
    parsed = english_time_parser.parse(text)
    assert parsed is not None
    assert parsed.duration_seconds == seconds
