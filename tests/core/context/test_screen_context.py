import pytest

from bilge.core.context import context_intent, screen_context
from bilge.core.context.context_intent import Action, ContextIntent, Kind
from bilge.core.context.screen_context import Document, Files, Page, ScreenContext, Text

PDF = "/Users/u/Downloads/rapor.pdf"
PAGE = "https://ntv.com.tr/haber"


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("Bunu özetle", ContextIntent(action=Action.SUMMARIZE, wanted=None)),
        ("Seçili metni İngilizceye çevir", ContextIntent(action=Action.TRANSLATE, wanted=Kind.TEXT)),
        ("Bu sayfayı özetle", ContextIntent(action=Action.SUMMARIZE, wanted=Kind.PAGE)),
        ("Şu dosyayı aç", ContextIntent(action=Action.OPEN, wanted=Kind.FILE)),
        ("Bu belgede ne yazıyor", ContextIntent(action=Action.READ, wanted=Kind.DOCUMENT)),
        ("Bunu açıklar mısın", ContextIntent(action=Action.EXPLAIN, wanted=None)),
        ("Açık PDF'i özetle", ContextIntent(action=Action.SUMMARIZE, wanted=Kind.DOCUMENT)),
    ],
)
def test_requests_that_point_at_something_on_screen(command, expected):
    assert context_intent.parse(command) == expected


@pytest.mark.parametrize(
    "command",
    [
        "Safari'yi aç",
        "Son indirdiğim PDF'i özetle",
        "Bugün hava nasıl",
        "Bu akşam ne var",
        "Ahmet'e mesaj at",
        "Bu şarkıyı değiştir",
    ],
)
def test_commands_that_do_not_point_at_the_screen(command):
    assert context_intent.parse(command) is None


def test_what_bu_refers_to_by_what_is_on_screen():
    everything = ScreenContext(
        selected_text="Seçili paragraf", selected_files=(PDF,), page_url=PAGE, page_title="Haber", document_url=PDF
    )
    assert screen_context.resolve(None, everything) == Text("Seçili paragraf")
    assert screen_context.resolve(Kind.PAGE, everything) == Page(PAGE, title="Haber")
    assert screen_context.resolve(Kind.FILE, everything) == Files((PDF,))
    browsing = ScreenContext(selected_text=None, selected_files=(), page_url=PAGE, page_title=None, document_url=None)
    assert screen_context.resolve(None, browsing) == Page(PAGE, title=None)
    assert screen_context.resolve(Kind.TEXT, browsing) is None
    reading = ScreenContext(selected_text="  ", selected_files=(), page_url=None, page_title=None, document_url=PDF)
    assert screen_context.resolve(None, reading) == Document(PDF)
    assert screen_context.resolve(Kind.FILE, reading) == Files((PDF,))
    assert screen_context.resolve(None, ScreenContext()) is None


@pytest.mark.parametrize(
    ("text", "pointing"),
    [
        ("", True),
        ("bunu", True),
        ("Şunu", True),
        ("bu linki", True),
        ("seçili metni", True),
        ("bu dosyayı", True),
        ("Yarın gelemeyeceğim", False),
        ("bunu yarın konuşalım", False),
    ],
)
def test_a_message_body_that_only_points_at_the_screen(text, pointing):
    assert context_intent.only_points(text) == pointing


def test_commands_worth_reading_the_screen_for():
    assert context_intent.points("Bunu Ahmet'e gönder")
    assert context_intent.points("Şu dosyayı Zeynep'e mail at")
    assert not context_intent.points("Bu akşam ne yapsak")
    assert not context_intent.points("Ahmet'e geç kalacağımı yaz")
    assert context_intent.wanted_kind("bu linki") == Kind.PAGE
    assert context_intent.wanted_kind("bunu") is None
