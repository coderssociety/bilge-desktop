"""A spoken spreadsheet command split into cells, numbers and words. Turkish case endings carry the grammar:
"D3'e" is where something goes, "B1'den" where a range or a subtraction starts."""

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from bilge.core.spreadsheet.cell_reference import CellReference
from bilge.core.text import lowercased


class GrammaticalCase(Enum):
    NONE = "none"
    DATIVE = "dative"
    ABLATIVE = "ablative"
    ACCUSATIVE = "accusative"
    LOCATIVE = "locative"
    GENITIVE = "genitive"


@dataclass(frozen=True)
class Cell:
    reference: CellReference


@dataclass(frozen=True)
class Column:
    """A whole column, "C sütunu" → "C:C"."""

    letter: str


@dataclass(frozen=True)
class Number:
    value: float


@dataclass(frozen=True)
class Word:
    text: str


TokenKind = Cell | Column | Number | Word


@dataclass(frozen=True)
class SpreadsheetToken:
    kind: TokenKind
    grammatical_case: GrammaticalCase
    # As spoken, for text written into a cell.
    original: str

    @property
    def word(self) -> str | None:
        return self.kind.text if isinstance(self.kind, Word) else None

    @property
    def cell(self) -> CellReference | None:
        return self.kind.reference if isinstance(self.kind, Cell) else None

    @property
    def is_number(self) -> bool:
        return isinstance(self.kind, Number)

    @property
    def is_column(self) -> bool:
        return isinstance(self.kind, Column)


# Spoken letter names, as dictation writes them when a column is said on its own ("de üç").
# "ve" is left out: it is "and" far more often than column V; "x" too, which may be "times".
_LETTER_NAMES: dict[str, str] = {
    "a": "A", "be": "B", "b": "B", "ce": "C", "c": "C", "de": "D", "d": "D", "e": "E", "fe": "F", "f": "F",
    "ge": "G", "g": "G", "he": "H", "ha": "H", "h": "H", "i": "I", "je": "J", "j": "J", "ke": "K", "ka": "K",
    "k": "K", "le": "L", "l": "L", "me": "M", "m": "M", "ne": "N", "n": "N", "o": "O", "pe": "P", "p": "P",
    "ku": "Q", "q": "Q", "re": "R", "r": "R", "se": "S", "s": "S", "te": "T", "t": "T", "u": "U",
    "w": "W", "iks": "X", "ye": "Y", "y": "Y", "ze": "Z", "z": "Z",
}  # fmt: skip
_SYMBOL_WORDS = (
    ("+", " artı "),
    ("×", " çarpı "),
    ("*", " çarpı "),
    ("=", " eşittir "),
    ("/", " bölü "),
    (" - ", " eksi "),
)
_APOSTROPHES = frozenset("'’‘`´")
_TRIMMED = '.,;:!?()"“”'
_DIACRITIC_FOLDS = str.maketrans(
    {"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u"}
)
_CASE_ENDINGS: dict[str, GrammaticalCase] = {
    **dict.fromkeys(("e", "a", "ye", "ya", "ne", "na"), GrammaticalCase.DATIVE),
    **dict.fromkeys(("den", "dan", "ten", "tan", "nden", "ndan"), GrammaticalCase.ABLATIVE),
    **dict.fromkeys(("i", "u", "yi", "yu", "ni", "nu"), GrammaticalCase.ACCUSATIVE),
    **dict.fromkeys(("de", "da", "te", "ta", "nde", "nda"), GrammaticalCase.LOCATIVE),
    **dict.fromkeys(("in", "un", "nin", "nun"), GrammaticalCase.GENITIVE),
}


def tokens(text: str) -> list[SpreadsheetToken]:
    spaced = text
    for symbol, word in _SYMBOL_WORDS:
        spaced = spaced.replace(symbol, word)
    pieces = [piece.strip(_TRIMMED) for piece in spaced.split()]
    pieces = [piece for piece in pieces if piece]
    result: list[SpreadsheetToken] = []
    index = 0
    while index < len(pieces):
        piece = pieces[index]
        base, suffix = _split(piece)
        joined = _spoken_cell_or_column(pieces, index, base, suffix)
        if joined is not None:
            result.append(joined)
            index += 2
            continue
        result.append(_token(piece, base, suffix))
        index += 1
    return _attach_cell_words(result)


def parse_double(text: str) -> float | None:
    """Swift's Double(String): no surrounding spaces, underscores or non-ASCII digits, which float() accepts."""
    if not text.isascii() or "_" in text or text != text.strip():
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(text: str) -> int | None:
    """Swift's Int(String)."""
    if not text.isascii() or "_" in text or text != text.strip():
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _spoken_cell_or_column(pieces: list[str], index: int, base: str, suffix: str) -> SpreadsheetToken | None:
    """A letter name followed by a row number ("de üç") or by "sütunu"."""
    letter = _LETTER_NAMES.get(base)
    if letter is None or suffix or index + 1 >= len(pieces):
        return None
    piece, following = pieces[index], pieces[index + 1]
    spoken_base, next_suffix = _split(following)
    # Number parsing leaves "bir" alone (it is usually "a"), but after a column letter it is 1.
    next_base = "1" if spoken_base == "bir" else spoken_base
    if parse_int(next_base) is not None and (cell := CellReference.parse(letter + next_base)) is not None:
        return SpreadsheetToken(Cell(cell), _grammatical_case(next_suffix), piece + " " + following)
    if next_base.startswith("sutun"):
        return SpreadsheetToken(Column(letter), GrammaticalCase.NONE, piece)
    return None


def _split(piece: str) -> tuple[str, str]:
    """ "D3'e" → ("d3", "e"); "d3e" → ("d3", "e"); "topla" → ("topla", "")."""
    lowered = lowercased(piece)
    mark = next((index for index, character in enumerate(lowered) if character in _APOSTROPHES), None)
    if mark is not None:
        return _fold(lowered[:mark]), _fold(lowered[mark + 1 :])
    folded = _fold(lowered)
    letters = _prefix(folded, lambda character: character.isascii() and character.isalpha())
    digits = _prefix(folded[len(letters) :], str.isnumeric)
    rest = folded[len(letters) + len(digits) :]
    if len(letters) <= 3 and digits and all(c.isalpha() for c in rest) and not (not letters and rest):
        return letters + digits, rest
    return folded, ""


def _prefix(text: str, predicate: Callable[[str], bool]) -> str:
    end = 0
    while end < len(text) and predicate(text[end]):
        end += 1
    return text[:end]


def _token(piece: str, base: str, suffix: str) -> SpreadsheetToken:
    grammatical = _grammatical_case(suffix)
    starts_with_letter = base[:1].isalpha()
    if (cell := CellReference.parse(base)) is not None and starts_with_letter:
        return SpreadsheetToken(Cell(cell), grammatical, piece)
    number = parse_double(base.replace(",", "."))
    if number is not None and base[:1].isnumeric():
        return SpreadsheetToken(Number(number), grammatical, piece)
    return SpreadsheetToken(Word(base + suffix), GrammaticalCase.NONE, piece)


def _attach_cell_words(tokens: list[SpreadsheetToken]) -> list[SpreadsheetToken]:
    """ "D3 hücresine" gives D3 the case of "hücresine"; "d3 e", where dictation split off the ending, gives it
    the case of "e"."""
    result: list[SpreadsheetToken] = []
    for token in tokens:
        previous = result[-1] if result else None
        word = token.word
        if (
            previous is not None
            and (previous.cell is not None or previous.is_number)
            and previous.grammatical_case is GrammaticalCase.NONE
            and word is not None
        ):
            ending = word.removeprefix("hucresi")
            attached = _grammatical_case(ending)
            if word.startswith("hucre") or attached is not GrammaticalCase.NONE:
                result[-1] = dataclasses.replace(previous, grammatical_case=attached)
                continue
        result.append(token)
    return result


def _grammatical_case(suffix: str) -> GrammaticalCase:
    return _CASE_ENDINGS.get(suffix, GrammaticalCase.NONE)


def _fold(text: str) -> str:
    """Lowercase without Turkish letters, keeping digits and the decimal comma ("12,5") intact."""
    return lowercased(text).translate(_DIACRITIC_FOLDS)
