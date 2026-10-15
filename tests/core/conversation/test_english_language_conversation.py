"""The conversation parts of the Swift EnglishLanguageTests; the speech and sentence cases live with
the speech modules."""

from datetime import datetime, timedelta

import pytest

from bilge.core.conversation.barge_in_detector import BargeInDetector, Command, NoBargeIn, Stop
from bilge.core.conversation.confirmation_parser import Answer, parse
from bilge.core.conversation.conversation_flow import ConversationFlow, ListeningForWake, NoAction, ReturnToIdle
from bilge.core.language import AssistantLanguage
from bilge.core.wake.wake_phrase_matcher import WakePhraseMatcher

ENGLISH = AssistantLanguage.ENGLISH


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Yes, send it", Answer.CONFIRMED),
        ("yeah sure", Answer.CONFIRMED),
        ("go ahead", Answer.CONFIRMED),
        ("No", Answer.REJECTED),
        ("cancel that", Answer.REJECTED),
        ("never mind", Answer.REJECTED),
        ("don't", Answer.REJECTED),
        ("maybe later", Answer.REJECTED),
        ("yes no", Answer.UNCLEAR),
    ],
)
def test_yes_and_no_in_english(text: str, expected: Answer) -> None:
    assert parse(text, language=ENGLISH) is expected


def test_sending_needs_a_clear_english_yes() -> None:
    assert parse("okay", strict=True, language=ENGLISH) is Answer.UNCLEAR
    assert parse("yes", strict=True, language=ENGLISH) is Answer.CONFIRMED
    assert parse("send it", strict=True, language=ENGLISH) is Answer.CONFIRMED


def test_one_languages_words_do_not_count_in_the_other() -> None:
    assert parse("süre", language=AssistantLanguage.TURKISH) is Answer.UNCLEAR
    assert parse("evet", language=ENGLISH) is Answer.UNCLEAR
    assert parse("yes", language=AssistantLanguage.TURKISH) is Answer.UNCLEAR


def test_english_stop_words_cut_in_filler_alone_does_not() -> None:
    detector = BargeInDetector(WakePhraseMatcher("bilge"), language=ENGLISH)
    assert detector.evaluate("stop", speaking="The weather is fine") == Stop()
    assert detector.evaluate("okay stop now", speaking="The weather is fine") == Stop()
    assert detector.evaluate("please", speaking="The weather is fine") == NoBargeIn()
    assert detector.evaluate("No.", speaking="Shall I add the event?") == Stop()
    assert detector.evaluate("Bilge, stop", speaking="The weather is fine") == Stop()
    assert detector.evaluate("Bilge, what time is it", speaking="Sunny and warm today") == Command("what time is it")


def test_the_wake_phrase_after_an_english_greeting() -> None:
    matcher = WakePhraseMatcher("bilge")
    assert matcher.match("Hey Bilge, what time is it?").command == "what time is it?"
    assert matcher.match("Okay Bilge open Safari").command == "open Safari"


def test_cancel_phrases_end_a_pending_command() -> None:
    flow = ConversationFlow(WakePhraseMatcher("bilge"))
    now = datetime.now()
    flow.heard("Bilge", at=now)
    assert flow.heard("never mind", at=now + timedelta(seconds=1)) == ReturnToIdle(timed_out=False)


@pytest.mark.parametrize("text", ["Bilge, stop", "Bilge iptal"])
def test_a_cancel_phrase_with_the_wake_word_does_nothing_when_idle(text: str) -> None:
    flow = ConversationFlow(WakePhraseMatcher("bilge"))
    assert flow.heard(text, at=datetime.now()) == NoAction()
    assert flow.phase == ListeningForWake()


@pytest.mark.parametrize(
    ("identifiers", "expected"),
    [
        (["en-US", "tr-TR"], AssistantLanguage.ENGLISH),
        (["tr-TR"], AssistantLanguage.TURKISH),
        (["de-DE", "en-GB"], AssistantLanguage.ENGLISH),
        (["fr-FR"], AssistantLanguage.TURKISH),
        ([], AssistantLanguage.TURKISH),
    ],
)
def test_the_systems_preferred_language_picks_the_assistants(
    identifiers: list[str], expected: AssistantLanguage
) -> None:
    assert AssistantLanguage.preferred(identifiers) is expected
