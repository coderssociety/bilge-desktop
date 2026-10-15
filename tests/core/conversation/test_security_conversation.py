"""The ConfirmationParser and TypedText parts of the Swift SecurityTests; the network and HTML cases
live with their modules."""

import pytest

from bilge.core.conversation.confirmation_parser import Answer, parse
from bilge.core.tools.typed_text import sanitized


def test_typed_text_cannot_press_return_tab_or_escape() -> None:
    assert sanitized("merhaba\rdünya\tnasılsın\x1b son\x85x\n") == "merhaba dünya nasılsın son x"
    assert sanitized("👩‍💻 kod") == "👩‍💻 kod"


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("evet", Answer.CONFIRMED),
        ("gönder", Answer.CONFIRMED),
        ("evet gönder", Answer.CONFIRMED),
        ("tamam", Answer.UNCLEAR),
        ("peki", Answer.UNCLEAR),
        ("yap", Answer.UNCLEAR),
        ("hayır", Answer.REJECTED),
    ],
)
def test_sending_needs_a_clear_yes(answer: str, expected: Answer) -> None:
    assert parse(answer, strict=True) is expected
