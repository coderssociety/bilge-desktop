import pytest

from bilge.core.language import AssistantLanguage
from bilge.core.spreadsheet.cell_reference import CellReference, SpreadsheetNumber, SpreadsheetText
from bilge.core.spreadsheet.spreadsheet_command import (
    Clear,
    Copy,
    Evaluate,
    Finish,
    Read,
    SetFormula,
    SetValue,
    Undo,
    mentions_cells,
    parse,
)

ENGLISH = AssistantLanguage.ENGLISH


def cell(address: str) -> CellReference:
    reference = CellReference.parse(address)
    assert reference is not None
    return reference


@pytest.mark.parametrize(
    ("text", "target", "formula"),
    [
        ("Put the sum of B1 and B2 into D3", "D3", "=B1+B2"),
        ("Add B1 and B2 into D3", "D3", "=B1+B2"),
        ("Put the sum of B1 to B9 in B10", "B10", "=SUM(B1:B9)"),
        ("Set D3 to B2 plus B1", "D3", "=B2+B1"),
        ("D3 equals B2 times 1.2", "D3", "=B2*1.2"),
        ("Subtract B2 from B1 into C1", "C1", "=B1-B2"),
        ("Divide B1 by B2 into C1", "C1", "=B1/B2"),
        ("Multiply B1 by C1 into D1", "D1", "=B1*C1"),
        ("Put the average of B1 through B9 in B11", "B11", "=AVERAGE(B1:B9)"),
    ],
)
def test_formulas_into_a_cell(text: str, target: str, formula: str) -> None:
    assert parse(text, language=ENGLISH) == SetFormula(cell(target), formula)


def test_values_reads_and_edits() -> None:
    assert parse("Write 1250 in C5", language=ENGLISH) == SetValue(cell("C5"), SpreadsheetNumber(1250))
    assert parse("Put 1,250 into C5", language=ENGLISH) == SetValue(cell("C5"), SpreadsheetNumber(1250))
    assert parse("Type Rent in A1", language=ENGLISH) == SetValue(cell("A1"), SpreadsheetText("Rent"))
    assert parse("What's in D3?", language=ENGLISH) == Read(cell("D3"))
    assert parse("Read B 4", language=ENGLISH) == Read(cell("B4"))
    assert parse("Clear D3", language=ENGLISH) == Clear(cell("D3"))
    assert parse("Copy D3 to E3", language=ENGLISH) == Copy(cell("D3"), cell("E3"))
    assert parse("Undo", language=ENGLISH) == Undo()
    assert parse("I'm done", language=ENGLISH) == Finish()
    assert parse("Exit Excel mode", language=ENGLISH) == Finish()


def test_questions_are_computed_not_written() -> None:
    assert parse("What's the total of column B", language=ENGLISH) == Evaluate("SUM(B:B)")
    assert parse("What is the sum of B1 to B9", language=ENGLISH) == Evaluate("SUM(B1:B9)")
    assert parse("What's the largest value in C2 through C11", language=ENGLISH) == Evaluate("MAX(C2:C11)")


def test_other_requests_are_not_spreadsheet_commands() -> None:
    assert parse("Open Safari", language=ENGLISH) is None
    assert parse("Add milk to my list", language=ENGLISH) is None
    assert mentions_cells("Calculate the tax in D2", language=ENGLISH)
    assert not mentions_cells("What's the weather", language=ENGLISH)
