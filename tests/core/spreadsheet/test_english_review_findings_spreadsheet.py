"""The SpreadsheetCommand case of the Swift EnglishReviewFindingsTests; the other cases belong to other modules."""

from bilge.core.language import AssistantLanguage
from bilge.core.spreadsheet.cell_reference import CellReference
from bilge.core.spreadsheet.spreadsheet_command import Read, parse


def test_what_is_a_cell_reads_it() -> None:
    assert parse("What is B2", language=AssistantLanguage.ENGLISH) == Read(CellReference("B", 2))
