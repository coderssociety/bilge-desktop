from pathlib import Path

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

# The routing benchmark lives in the Swift repo next to this one.
BENCH = Path(__file__).resolve().parents[3] / "bench"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Sonraki sekmeye geç", NextTab()),
        ("bir sonraki sekme", NextTab()),
        ("Önceki sekmeye dön", PreviousTab()),
        ("Üçüncü sekmeye geç", Tab(3)),
        ("ilk sekmeye geç", Tab(1)),
        ("Son sekmeye geç", LastTab()),
        ("Yeni sekme aç", NewTab()),
        ("Bu sekmeyi kapat", CloseTab()),
        ("Kapattığım sekmeyi geri aç", ReopenTab()),
        ("Geri git", Back()),
        ("Önceki sayfaya dön", Back()),
        ("İleri git", Forward()),
        ("Sayfayı yenile", Reload()),
        ("Aşağı kaydır", ScrollDown()),
        ("biraz aşağı in", ScrollDown()),
        ("Yukarı kaydır", ScrollUp()),
        ("En alta in", Bottom()),
        ("Sayfanın sonuna git", Bottom()),
        ("En üste çık", Top()),
        ("Sayfanın başına dön", Top()),
    ],
)
def test_tab_history_and_page_commands(text, expected):
    assert browser_command.parse(text) == expected


def test_switching_to_a_tab_by_its_title_and_finding_text_on_the_page():
    assert browser_command.parse("YouTube sekmesine geç") == TabNamed("YouTube")
    assert browser_command.parse("Hürriyet sekmesini aç") == TabNamed("Hürriyet")
    assert browser_command.parse("Bu sayfada fiyat kelimesini ara") == Find("fiyat")
    assert browser_command.parse("Sayfada iade koşulları'nı bul") == Find("iade koşulları")


@pytest.mark.parametrize(
    "text",
    [
        "geri al",
        "Safari'yi aç",
        "Sesi aç",
        "Bilgisayarı yeniden başlat",
        "Ekran görüntüsü al",
        "yarın hava nasıl",
        "Ahmet'e geri dönüş yap diye mesaj at",
        "Google'da sekme ara",
    ],
)
def test_commands_for_other_things_are_left_alone(text):
    assert browser_command.parse(text) is None


def test_none_of_the_routing_benchmark_commands_is_taken_for_a_browser_command():
    files = [file for file in BENCH.glob("*.tsv") if not file.name.startswith("chat")]
    assert files
    for file in files:
        for line in file.read_text(encoding="utf-8").split("\n"):
            if not line:
                continue
            command = line.split("\t")[0]
            assert browser_command.parse(command) is None, f"{file.name}: {command}"
