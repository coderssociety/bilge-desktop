import pytest

from bilge.core.conversation.confirmation_parser import Answer, parse


@pytest.mark.parametrize(
    "text",
    ["Evet", "evet lütfen", "Olur.", "tamam", "onaylıyorum", "Gönder", "yap", "tabii ki", "aynen öyle", "evet evet"],
)
def test_recognizes_approvals(text: str) -> None:
    assert parse(text) is Answer.CONFIRMED


@pytest.mark.parametrize(
    "text",
    ["Hayır", "hayır yapma", "iptal", "vazgeç", "Yok.", "istemiyorum", "dur", "gönderme", "silme", "boş ver"],
)
def test_recognizes_refusals(text: str) -> None:
    assert parse(text) is Answer.REJECTED


@pytest.mark.parametrize("text", ["", "bilmiyorum", "evet ama hayır", "saat kaç", "belki"])
def test_anything_unclear_or_contradictory_is_unclear(text: str) -> None:
    assert parse(text) is Answer.UNCLEAR
