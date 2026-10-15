import pytest

from bilge.core.browser import browser_command
from bilge.core.browser.browser_command import (
    Back,
    Bottom,
    CloseTab,
    Find,
    Forward,
    LastTab,
    NewTab,
    NextTab,
    PreviousTab,
    Reload,
    ReopenTab,
    ScrollDown,
    ScrollUp,
    Tab,
    TabNamed,
    Top,
)
from bilge.core.language import AssistantLanguage

ENGLISH = AssistantLanguage.ENGLISH


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Next tab", NextTab()),
        ("Go to the previous tab", PreviousTab()),
        ("Open a new tab", NewTab()),
        ("Close this tab", CloseTab()),
        ("Reopen the closed tab", ReopenTab()),
        ("Bring back the tab I closed", ReopenTab()),
        ("Switch to the third tab", Tab(3)),
        ("Go to tab 2", Tab(2)),
        ("Go to the last tab", LastTab()),
        ("Switch to the YouTube tab", TabNamed("YouTube")),
        ("Go back", Back()),
        ("Back", Back()),
        ("Go forward", Forward()),
        ("Refresh the page", Reload()),
        ("Scroll down", ScrollDown()),
        ("Page up", ScrollUp()),
        ("Go to the top", Top()),
        ("Scroll to the bottom", Bottom()),
        ("Find price on this page", Find("price")),
        ("Search for return policy on the page", Find("return policy")),
    ],
)
def test_recognized(text, expected):
    assert browser_command.parse(text, language=ENGLISH) == expected


@pytest.mark.parametrize(
    "text",
    [
        "I'll be back later today",
        "Turn the volume up",
        "Open Safari",
        "What's on the news",
        "Look up flights to Rome",
        "Search YouTube for cat videos",
    ],
)
def test_ordinary_sentences_are_left_to_the_router(text):
    assert browser_command.parse(text, language=ENGLISH) is None
