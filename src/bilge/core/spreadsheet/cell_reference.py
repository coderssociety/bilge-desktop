import re
from dataclasses import dataclass
from typing import Self

_MAX_COLUMN = 16_384
_MAX_ROW = 1_048_576
# Swift's Int(String) takes an optional sign and ASCII digits only; int() would also take spaces and underscores.
_INTEGER = re.compile(r"[+-]?[0-9]+")


@dataclass(frozen=True)
class CellReference:
    """An A1-style cell address such as "D3" or "AA12", within Excel's limits (XFD1048576)."""

    column: str
    row: int

    @classmethod
    def parse(cls, text: str) -> Self | None:
        upper = text.upper()
        letter_count = 0
        while letter_count < len(upper) and _is_ascii_letter(upper[letter_count]):
            letter_count += 1
        letters, digits = upper[:letter_count], upper[letter_count:]
        if not 1 <= len(letters) <= 3 or not _INTEGER.fullmatch(digits):
            return None
        row = int(digits)
        if not 1 <= row <= _MAX_ROW or _column_number(letters) > _MAX_COLUMN:
            return None
        return cls(column=letters, row=row)

    @property
    def address(self) -> str:
        return f"{self.column}{self.row}"


@dataclass(frozen=True)
class SpreadsheetNumber:
    value: float


@dataclass(frozen=True)
class SpreadsheetText:
    value: str


SpreadsheetValue = SpreadsheetNumber | SpreadsheetText


def _is_ascii_letter(character: str) -> bool:
    return character.isascii() and character.isalpha()


def _column_number(letters: str) -> int:
    number = 0
    for letter in letters:
        number = number * 26 + ord(letter) - 64
    return number
