import pytest

from bilge.core.agent.agent_step import Call, Done, compact_tool_signature, parse
from bilge.core.agent.compound_command import has_dependent_parts, split


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Safari'yi aç ve sesi yüzde 30 yap", ["Safari'yi aç", "sesi yüzde 30 yap"]),
        ("yarın 3'te toplantı ekle sonra da Ahmet'e haber ver", ["yarın 3'te toplantı ekle", "Ahmet'e haber ver"]),
        ("ekran görüntüsü al ardından Elif'e gönder", ["ekran görüntüsü al", "Elif'e gönder"]),
        ("müziği durdur ve sonra ekranı kilitle", ["müziği durdur", "ekranı kilitle"]),
    ],
)
def test_splits_sequenced_commands(text: str, expected: list[str]) -> None:
    assert split(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "kahve ve süt almayı hatırlat",
        "Ali ve Veli'ye mesaj at",
        "saat kaç",
        "yaz ve kış lastiklerini not al",
        "ekle ve",
        "Safari'yi aç ve",
    ],
)
def test_keeps_single_commands_whole(text: str) -> None:
    assert split(text) is None


def test_parses_planner_replies() -> None:
    assert parse('{"tool": "openApp", "arguments": {"appName": "Safari"}}') == Call(
        tool="openApp", arguments_json='{"appName":"Safari"}'
    )
    assert parse('Tamam.\n```json\n{"done": "İkisini de yaptım."}\n```') == Done("İkisini de yaptım.")
    assert parse('{"tool": "note", "arguments": {"body": "a } b"}}') == Call(
        tool="note", arguments_json='{"body":"a } b"}'
    )
    assert parse('{"tool": "sendMessage", "arguments": {"recipient": "Ali"}, "done": "Gönderdim."}') == Call(
        tool="sendMessage", arguments_json='{"recipient":"Ali"}', final_message="Gönderdim."
    )
    assert parse("JSON yok") is None
    assert parse('{"arguments": {}}') is None


def test_compact_tool_signatures() -> None:
    schema = (
        '{"properties":{"title":{"type":"string","description":"Adı"},'
        '"dayOffset":{"type":"integer","minimum":0,"maximum":60},"kind":{"type":"string","enum":["a","b"]}},'
        '"required":["title","kind"],"x-order":["title","dayOffset","kind"]}'
    )
    assert compact_tool_signature("addEvent", schema.encode()) == (
        'addEvent(title: string "Adı", dayOffset?: integer 0…60, kind: a|b)'
    )


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        (["Ahmet'in numarasını bul", "ona mesaj at"], True),
        (["son indirdiğim PDF'i özetle", "özeti panoya kopyala"], True),
        (["ekran görüntüsü al", "bunu Elif'e gönder"], True),
        (["sesi yüzde 25 yap", "müziği durdur"], False),
        (["Safari'yi aç", "ekranı kilitle"], False),
    ],
)
def test_later_parts_that_refer_back_need_planning(parts: list[str], expected: bool) -> None:
    assert has_dependent_parts(parts) is expected
