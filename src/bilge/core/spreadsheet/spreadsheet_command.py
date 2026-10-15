"""A spoken spreadsheet edit, parsed without a language model so cell names and numbers are never guessed:
"D3'e B2 ile B1'i topla" → D3 = "=B2+B1". Formulas use Excel's English function names, which it accepts
whatever the user interface language."""

from dataclasses import dataclass
from enum import Enum, auto
from itertools import pairwise

from bilge.core.language import AssistantLanguage
from bilge.core.speech.turkish_number_parser import digitize
from bilge.core.spreadsheet.cell_reference import CellReference, SpreadsheetNumber, SpreadsheetText, SpreadsheetValue
from bilge.core.spreadsheet.spreadsheet_tokens import (
    Cell,
    Column,
    GrammaticalCase,
    Number,
    SpreadsheetToken,
    Word,
    tokens,
)
from bilge.core.text import folded


@dataclass(frozen=True)
class SetFormula:
    target: CellReference
    formula: str


@dataclass(frozen=True)
class SetValue:
    target: CellReference
    value: SpreadsheetValue


@dataclass(frozen=True)
class Read:
    cell: CellReference


@dataclass(frozen=True)
class Clear:
    cell: CellReference


@dataclass(frozen=True)
class Copy:
    source: CellReference
    destination: CellReference


@dataclass(frozen=True)
class Evaluate:
    """A question ("B1'den B9'a kadar toplam kaç"): computed and spoken, nothing is written."""

    formula: str


@dataclass(frozen=True)
class Undo:
    pass


@dataclass(frozen=True)
class Finish:
    """Leaves spreadsheet mode."""


SpreadsheetCommand = SetFormula | SetValue | Read | Clear | Copy | Evaluate | Undo | Finish


class Operation(Enum):
    SUM = auto()
    SUBTRACT = auto()
    MULTIPLY = auto()
    DIVIDE = auto()
    AVERAGE = auto()
    MAXIMUM = auto()
    MINIMUM = auto()
    COUNT = auto()
    WRITE = auto()
    READ = auto()
    CLEAR = auto()
    COPY = auto()


_FUNCTIONS = {
    Operation.AVERAGE: "AVERAGE",
    Operation.MAXIMUM: "MAX",
    Operation.MINIMUM: "MIN",
    Operation.COUNT: "COUNT",
}
_FINISH_PHRASES = frozenset({"bitti", "tamam bitti", "tamamdir bitti", "is bitti", "excel bitti"})
_OPERATORS = {"arti": "+", "eksi": "-", "carpi": "*", "bolu": "/"}
_WRITE_WORDS = frozenset({"yaz", "yazar", "yazsana", "yazin", "koy", "gir"})
_READ_WORDS = frozenset({"oku", "okur", "okusana", "kac", "degeri", "degerini"})
_CLEAR_WORDS = frozenset({"sil", "silsene", "temizle", "bosalt"})
_EQUALS_WORDS = frozenset({"esittir", "esit"})


def parse(text: str, language: AssistantLanguage = AssistantLanguage.TURKISH) -> SpreadsheetCommand | None:
    if language is AssistantLanguage.ENGLISH:
        from bilge.core.spreadsheet import english_spreadsheet_command

        return english_spreadsheet_command.parse(text)
    folded_text = folded(text)
    folded_words = folded_text.split()
    leaves_excel = "excel" in folded_words and any(
        word in ("cik", "kapat", "bitir") or word.startswith("modundan") for word in folded_words
    )
    if folded_text in _FINISH_PHRASES or leaves_excel:
        return Finish()
    if "geri al" in folded_text or "geri getir" in folded_text:
        return Undo()

    spoken = tokens(text)
    if not any(token.cell is not None or token.is_column for token in spoken):
        return None
    words = [token.word for token in spoken if token.word is not None]
    operation = _operation(words)
    return None if operation is None else _build(operation, spoken)


def mentions_cells(text: str, language: AssistantLanguage = AssistantLanguage.TURKISH) -> bool:
    """True when the command talks about cells at all ("D2'ye KDV'li fiyatı hesapla"), even if no rule understood
    it: in spreadsheet mode such requests go to the language model for a formula."""
    if language is AssistantLanguage.ENGLISH:
        from bilge.core.spreadsheet import english_spreadsheet_command

        return english_spreadsheet_command.mentions_cells(text)
    spoken = tokens(digitize(text))
    if any(token.cell is not None or token.is_column for token in spoken):
        return True
    prefixes = ("hucre", "sutun", "satir", "formul")
    return any(token.word is not None and token.word.startswith(prefixes) for token in spoken)


def formula_number(value: float) -> str:
    """1250.0 → "1250", 1.2 → "1.2"."""
    return str(int(value)) if value.is_integer() and abs(value) < 1e15 else repr(value)


def function_name(operation: Operation) -> str:
    return _FUNCTIONS.get(operation, "SUM")


# Recognizing the operation


def _operation(words: list[str]) -> Operation | None:
    def has(prefix: str) -> bool:
        return any(word.startswith(prefix) for word in words)

    def after(first: str, prefixes: tuple[str, ...]) -> bool:
        return any(word == first and following.startswith(prefixes) for word, following in pairwise(words))

    if has("kopyala"):
        return Operation.COPY
    if any(word in _CLEAR_WORDS for word in words):
        return Operation.CLEAR
    if has("ortalama"):
        return Operation.AVERAGE
    if after("en", ("buyu", "yuksek", "fazla")) or has("maksimum"):
        return Operation.MAXIMUM
    if after("en", ("kucu", "dusuk", "az")) or has("minimum"):
        return Operation.MINIMUM
    if has("topla") or has("toplam"):
        return Operation.SUM
    if has("cikar"):
        return Operation.SUBTRACT
    if any(word.startswith("carp") and word != "carpi" for word in words):
        return Operation.MULTIPLY
    if any(word.startswith("bol") and word != "bolu" for word in words):
        return Operation.DIVIDE
    if "say" in words or has("sayisi"):
        return Operation.COUNT
    if any(word in _WRITE_WORDS or word in _EQUALS_WORDS for word in words):
        return Operation.WRITE
    if any(word in _READ_WORDS for word in words) or ("ne" in words and "var" in words):
        return Operation.READ
    return None


# Building the command


def _build(operation: Operation, spoken: list[SpreadsheetToken]) -> SpreadsheetCommand | None:
    cells = [token.cell for token in spoken if token.cell is not None]
    match operation:
        case Operation.COPY:
            source = next((t.cell for t in spoken if t.cell and t.grammatical_case is not GrammaticalCase.DATIVE), None)
            destination = next(
                (t.cell for t in spoken if t.cell and t.grammatical_case is GrammaticalCase.DATIVE), None
            )
            return Copy(source, destination) if source and destination else None
        case Operation.CLEAR:
            return Clear(cells[0]) if len(cells) == 1 else None
        case Operation.READ:
            return Read(cells[0]) if len(cells) == 1 else None
        case _:
            return _compute(operation, spoken)


def _compute(operation: Operation, spoken: list[SpreadsheetToken]) -> SpreadsheetCommand | None:
    cell_range, remaining = _take_range(spoken)
    target, remaining = _take_target(remaining, operation)
    if operation is Operation.WRITE:
        return _write(target, remaining) if target else None
    operands = [token for token in remaining if token.cell is not None or token.is_number]
    expression = _expression(operation, cell_range, operands)
    if expression is None:
        return None
    return Evaluate(expression) if target is None else SetFormula(target, "=" + expression)


def _expression(operation: Operation, cell_range: str | None, operands: list[SpreadsheetToken]) -> str | None:
    match operation:
        case Operation.AVERAGE | Operation.MAXIMUM | Operation.MINIMUM | Operation.COUNT:
            arguments = cell_range or (",".join(map(_operand, operands)) if len(operands) >= 2 else None)
            return f"{function_name(operation)}({arguments})" if arguments else None
        case Operation.SUM:
            if cell_range:
                return f"SUM({cell_range})"
            return "+".join(map(_operand, operands)) if len(operands) >= 2 else None
        case Operation.SUBTRACT:
            if len(operands) < 2:
                return None
            minuend = next((t for t in operands if t.grammatical_case is GrammaticalCase.ABLATIVE), operands[0])
            rest = [token for token in operands if token != minuend]
            return "-".join(map(_operand, [minuend, *rest]))
        case Operation.MULTIPLY:
            return "*".join(map(_operand, operands)) if len(operands) >= 2 else None
        case Operation.DIVIDE:
            if len(operands) != 2:
                return None
            divisor = next((t for t in operands if t.grammatical_case is GrammaticalCase.DATIVE), operands[1])
            dividend = next((token for token in operands if token != divisor), operands[0])
            return f"{_operand(dividend)}/{_operand(divisor)}"
        case _:
            return None


def _write(target: CellReference, remaining: list[SpreadsheetToken]) -> SpreadsheetCommand | None:
    """ "C5'e 1250 yaz" → a number; "D3'e B2 artı B1 yaz" → a formula; "A1'e Kira Gideri yaz" → text."""
    content = [
        token
        for token in remaining
        if token.word is None or (token.word not in _WRITE_WORDS and token.word not in _EQUALS_WORDS | {"olsun"})
    ]
    if not content:
        return None
    if any(token.word in _OPERATORS for token in content if token.word is not None):
        parts: list[str] = []
        for token in content:
            if token.word is None:
                parts.append(_operand(token))
            elif token.word in _OPERATORS:
                parts.append(_OPERATORS[token.word])
            else:
                return None
        return SetFormula(target, "=" + "".join(parts))
    if len(content) == 1 and isinstance(content[0].kind, Number):
        return SetValue(target, SpreadsheetNumber(content[0].kind.value))
    if not all(token.word is not None or token.is_number for token in content):
        return None
    return SetValue(target, SpreadsheetText(" ".join(token.original for token in content)))


def _take_range(spoken: list[SpreadsheetToken]) -> tuple[str | None, list[SpreadsheetToken]]:
    """ "B1'den B9'a kadar", "C2 ile C11 arası", "C sütunu" → "B1:B9"; the cells are taken out of the tokens."""
    column_index = next((index for index, token in enumerate(spoken) if token.is_column), None)
    if column_index is not None:
        letter = spoken[column_index].kind.letter
        return f"{letter}:{letter}", spoken[:column_index] + spoken[column_index + 1 :]
    for start, token in enumerate(spoken):
        first = token.cell
        following = start + 1
        if first is None or following >= len(spoken):
            continue
        end = spoken[following].cell
        if (
            token.grammatical_case is GrammaticalCase.ABLATIVE
            and end is not None
            and spoken[following].grammatical_case is GrammaticalCase.DATIVE
            and following + 1 < len(spoken)
            and spoken[following + 1].word == "kadar"
        ):
            return f"{first.address}:{end.address}", spoken[:start] + spoken[following + 2 :]
        if (
            spoken[following].word == "ile"
            and following + 2 < len(spoken)
            and (end := spoken[following + 1].cell) is not None
            and (spoken[following + 2].word or "").startswith("arasi")
        ):
            return f"{first.address}:{end.address}", spoken[:start] + spoken[following + 3 :]
    return None, spoken


def _take_target(
    spoken: list[SpreadsheetToken], operation: Operation
) -> tuple[CellReference | None, list[SpreadsheetToken]]:
    """Where the result goes: the cell before "eşittir", the cell just before "yaz", or else the first cell in the
    dative ("D3'e"). A divisor ("B1'e böl") is in the dative too, so it is skipped."""
    equals = next((index for index, token in enumerate(spoken) if token.word in _EQUALS_WORDS), None)
    if equals is not None and equals > 0 and (cell := spoken[equals - 1].cell) is not None:
        return cell, _without(spoken, equals - 1)
    datives = [
        index
        for index, token in enumerate(spoken)
        if token.cell is not None and token.grammatical_case is GrammaticalCase.DATIVE
    ]
    candidates = datives
    if operation is Operation.DIVIDE and datives:
        divide_index = next(
            (i for i, t in enumerate(spoken) if t.word and t.word.startswith("bol") and t.word != "bolu"), len(spoken)
        )
        divisor = next((index for index in reversed(datives) if index < divide_index), None)
        if divisor is not None and (len(datives) >= 2 or divisor == divide_index - 1):
            candidates = [index for index in candidates if index != divisor]
    write_index = next((index for index, token in enumerate(spoken) if token.word in _WRITE_WORDS), None)
    if write_index is not None:
        before_write = next((index for index in reversed(candidates) if index < write_index), None)
        if before_write is not None:
            return spoken[before_write].cell, _without(spoken, before_write)
    if not candidates:
        return None, spoken
    return spoken[candidates[0]].cell, _without(spoken, candidates[0])


def _without(spoken: list[SpreadsheetToken], index: int) -> list[SpreadsheetToken]:
    return spoken[:index] + spoken[index + 1 :]


def _operand(token: SpreadsheetToken) -> str:
    match token.kind:
        case Cell(reference):
            return reference.address
        case Number(value):
            return formula_number(value)
        case Column(letter):
            return f"{letter}:{letter}"
        case Word(text):
            return text
