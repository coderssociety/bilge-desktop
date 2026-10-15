"""English counterpart of `spreadsheet_command`'s Turkish rules. Turkish marks roles with case endings ("D3'e"
target, "B1'den" start); English uses word order and prepositions: "put the sum of B1 and B2 into D3", "set D3
to B2 plus B1", "sum of B1 to B9", "subtract B2 from B1", "copy D3 to E3"."""

import re
from dataclasses import dataclass

from bilge.core.spreadsheet.cell_reference import CellReference, SpreadsheetNumber, SpreadsheetText
from bilge.core.spreadsheet.spreadsheet_command import (
    Clear,
    Copy,
    Evaluate,
    Finish,
    Operation,
    Read,
    SetFormula,
    SetValue,
    SpreadsheetCommand,
    Undo,
    formula_number,
    function_name,
)
from bilge.core.spreadsheet.spreadsheet_tokens import parse_double, parse_int
from bilge.core.text import folded


@dataclass(frozen=True)
class _Cell:
    reference: CellReference


@dataclass(frozen=True)
class _Column:
    letter: str


@dataclass(frozen=True)
class _Number:
    value: float


@dataclass(frozen=True)
class _Word:
    text: str
    original: str


_Token = _Cell | _Column | _Number | _Word

_FINISH_PHRASES = frozenset({"done", "im done", "all done", "finish", "finished", "thats it"})
_EXIT_WORDS = frozenset({"exit", "leave", "quit", "close", "stop"})
_OPERATORS = {"plus": "+", "minus": "-", "times": "*", "over": "/", "+": "+", "-": "-", "*": "*", "/": "/"}
_WRITE_WORDS = frozenset({"write", "put", "type", "enter", "set", "make", "equals", "equal", "is"})
_READ_WORDS = frozenset({"read", "whats", "what", "value", "say", "says"})
_CLEAR_WORDS = frozenset({"clear", "delete", "erase", "empty", "remove"})
_RANGE_WORDS = frozenset({"to", "through", "thru", "until"})
_TARGET_WORDS = frozenset({"into", "in", "to"})
_SETTING_VERBS = frozenset({"set", "make"})
_EQUALS_WORDS = frozenset({"equals", "equal", "is", "="})
_FILLERS = frozenset(
    {
        "the",
        "of",
        "and",
        "a",
        "an",
        "cell",
        "cells",
        "please",
        "result",
        "answer",
        "number",
        "value",
        "by",
        "from",
        "with",
    }
)
_THOUSANDS_COMMA = re.compile(r"(?<=\d),(?=\d{3}\b)")
_TRIMMED = ",.?!:;\"'“”"


def parse(text: str) -> SpreadsheetCommand | None:
    folded_words = folded(text).split()
    if " ".join(folded_words) in _FINISH_PHRASES or ("excel" in folded_words and _EXIT_WORDS & set(folded_words)):
        return Finish()
    if folded_words[:1] == ["undo"]:
        return Undo()
    tokens = _tokenize(text)
    if not any(isinstance(token, _Cell | _Column) for token in tokens):
        return None
    operation = _operation([token.text for token in tokens if isinstance(token, _Word)])
    match operation:
        case None:
            return None
        case Operation.COPY:
            return _copy(tokens)
        case Operation.CLEAR | Operation.READ:
            cells = _cells(tokens)
            if len(cells) != 1:
                return None
            return Clear(cells[0]) if operation is Operation.CLEAR else Read(cells[0])
        case _:
            cell_range, tokens = _take_range(tokens)
            target, tokens = _take_target(tokens)
            return _compute(operation, cell_range, target, tokens)


def mentions_cells(text: str) -> bool:
    tokens = _tokenize(text)
    if any(isinstance(token, _Cell | _Column) for token in tokens):
        return True
    return any(isinstance(token, _Word) and token.text in ("cell", "column", "row", "formula") for token in tokens)


def _operation(words: list[str]) -> Operation | None:
    def has(*candidates: str) -> bool:
        return any(candidate in words for candidate in candidates)

    has_operator = any(word in _OPERATORS for word in words)
    has_write_word = any(word in _WRITE_WORDS for word in words)
    if has("copy"):
        return Operation.COPY
    if any(word in _CLEAR_WORDS for word in words):
        return Operation.CLEAR
    if has("average", "mean"):
        return Operation.AVERAGE
    if has("max", "maximum", "largest", "highest", "biggest"):
        return Operation.MAXIMUM
    if has("min", "minimum", "smallest", "lowest"):
        return Operation.MINIMUM
    if has("count") or (has("how") and has("many")):
        return Operation.COUNT
    if has_operator and (has_write_word or has("equals")):
        return Operation.WRITE
    asks = words[:1] in (["what"], ["whats"])
    computes = has("sum", "total", "add")
    if asks and not computes and not has_operator:
        return Operation.READ
    if computes:
        return Operation.SUM
    if has("subtract"):
        return Operation.SUBTRACT
    if has("multiply"):
        return Operation.MULTIPLY
    if has("divide"):
        return Operation.DIVIDE
    if has_write_word:
        return Operation.WRITE
    if any(word in _READ_WORDS for word in words):
        return Operation.READ
    return None


def _copy(tokens: list[_Token]) -> SpreadsheetCommand | None:
    to = next((index for index, token in enumerate(tokens) if _word(token) in ("to", "into")), None)
    if to is None:
        return None
    sources, destinations = _cells(tokens[:to]), _cells(tokens[to:])
    return Copy(sources[0], destinations[0]) if sources and destinations else None


def _compute(
    operation: Operation, cell_range: str | None, target: CellReference | None, tokens: list[_Token]
) -> SpreadsheetCommand | None:
    if operation is Operation.WRITE:
        return _write(target, tokens) if target else None
    expression = _expression(operation, cell_range, tokens)
    if expression is None:
        return None
    return Evaluate(expression) if target is None else SetFormula(target, "=" + expression)


def _expression(operation: Operation, cell_range: str | None, tokens: list[_Token]) -> str | None:
    operands = [token for token in tokens if _is_operand(token)]
    match operation:
        case Operation.AVERAGE | Operation.MAXIMUM | Operation.MINIMUM | Operation.COUNT:
            arguments = cell_range or (",".join(map(_operand, operands)) if len(operands) >= 2 else None)
            return f"{function_name(operation)}({arguments})" if arguments else None
        case Operation.SUM:
            if cell_range:
                return f"SUM({cell_range})"
            return "+".join(map(_operand, operands)) if len(operands) >= 2 else None
        case Operation.SUBTRACT:
            # "Subtract B2 from B1": what follows "from" is the minuend.
            if len(operands) != 2:
                return None
            from_index = next((index for index, token in enumerate(tokens) if _word(token) == "from"), None)
            after_from = [] if from_index is None else [t for t in tokens[from_index:] if _is_operand(t)]
            minuend = after_from[0] if after_from else operands[0]
            subtrahend = next((token for token in operands if token != minuend), operands[1])
            return f"{_operand(minuend)}-{_operand(subtrahend)}"
        case Operation.MULTIPLY:
            return "*".join(map(_operand, operands)) if len(operands) >= 2 else None
        case Operation.DIVIDE:
            return f"{_operand(operands[0])}/{_operand(operands[1])}" if len(operands) == 2 else None
        case _:
            return None


def _write(target: CellReference, tokens: list[_Token]) -> SpreadsheetCommand | None:
    """ "Write 1250 in C5" → a number; "set D3 to B2 plus B1" → a formula; "put Rent in A1" → text."""
    content = [token for token in tokens if not isinstance(token, _Word) or not _is_write_filler(token.text)]
    if not content:
        return None
    if any(isinstance(token, _Word) and token.text in _OPERATORS for token in content):
        parts: list[str] = []
        for token in content:
            if not isinstance(token, _Word):
                parts.append(_operand(token))
            elif token.text in _OPERATORS:
                parts.append(_OPERATORS[token.text])
            else:
                return None
        return SetFormula(target, "=" + "".join(parts))
    if len(content) == 1 and isinstance(content[0], _Number):
        return SetValue(target, SpreadsheetNumber(content[0].value))
    words: list[str] = []
    for token in content:
        match token:
            case _Word(_, original):
                words.append(original)
            case _Number():
                words.append(_operand(token))
            case _:
                return None
    return SetValue(target, SpreadsheetText(" ".join(words)))


def _is_write_filler(word: str) -> bool:
    return word in _WRITE_WORDS or word in _FILLERS or word in _TARGET_WORDS


def _take_range(tokens: list[_Token]) -> tuple[str | None, list[_Token]]:
    """ "B1 to B9", "from B1 through B9", "column B" → "B1:B9" / "B:B"; taken out of the tokens."""
    column_index = next((index for index, token in enumerate(tokens) if isinstance(token, _Column)), None)
    if column_index is not None:
        letter = tokens[column_index].letter
        return f"{letter}:{letter}", tokens[:column_index] + tokens[column_index + 1 :]
    for start, token in enumerate(tokens):
        if not isinstance(token, _Cell) or start + 2 >= len(tokens):
            continue
        word, end = _word(tokens[start + 1]), tokens[start + 2]
        if word not in _RANGE_WORDS or not isinstance(end, _Cell):
            continue
        # "copy B1 to B2" never gets here; "set D3 to B2" has no cell before "to" that starts a range of the same kind.
        if word == "to" and start > 0 and _word(tokens[start - 1]) in _SETTING_VERBS:
            continue
        return f"{token.reference.address}:{end.reference.address}", tokens[:start] + tokens[start + 3 :]
    return None, tokens


def _take_target(tokens: list[_Token]) -> tuple[CellReference | None, list[_Token]]:
    """The cell after "set"/"make" or before "equals"/"=", else the cell after a final "into"/"in"/"to"."""
    verb = next((index for index, token in enumerate(tokens) if _word(token) in _SETTING_VERBS), None)
    if verb is not None and verb + 1 < len(tokens) and isinstance(cell := tokens[verb + 1], _Cell):
        return cell.reference, _without(tokens, verb + 1)
    equals = next((index for index, token in enumerate(tokens) if _word(token) in _EQUALS_WORDS), None)
    if equals is not None and equals > 0 and isinstance(cell := tokens[equals - 1], _Cell):
        return cell.reference, _without(tokens, equals - 1)
    index = next(
        (
            index
            for index in reversed(range(1, len(tokens)))
            if isinstance(tokens[index], _Cell) and _word(tokens[index - 1]) in _TARGET_WORDS
        ),
        None,
    )
    if index is None:
        return None, tokens
    return tokens[index].reference, _without(tokens, index)


def _tokenize(text: str) -> list[_Token]:
    spaced = _THOUSANDS_COMMA.sub("", text).replace("=", " = ")
    pieces = [piece.strip(_TRIMMED) for piece in spaced.split()]
    pieces = [piece for piece in pieces if piece]
    tokens: list[_Token] = []
    index = 0
    while index < len(pieces):
        piece = pieces[index]
        following = pieces[index + 1] if index + 1 < len(pieces) else None
        word = folded(piece)
        if word == "column" and following is not None and len(following) <= 2 and _is_ascii_letters(following):
            tokens.append(_Column(following.upper()))
            index += 2
            continue
        # A recognizer may write "B 1" for B1.
        if (
            len(piece) == 1
            and piece.isalpha()
            and following is not None
            and parse_int(following) is not None
            and (cell := CellReference.parse(piece + following)) is not None
        ):
            tokens.append(_Cell(cell))
            index += 2
            continue
        tokens.append(_single_token(piece, word))
        index += 1
    return tokens


def _single_token(piece: str, word: str) -> _Token:
    if (cell := CellReference.parse(piece)) is not None and piece[0].isalpha():
        return _Cell(cell)
    if (value := parse_double(piece)) is not None:
        return _Number(value)
    if piece == "=":
        return _Word("=", "=")
    return _Word(word, piece)


def _is_ascii_letters(text: str) -> bool:
    return all(character.isascii() and character.isalpha() for character in text)


def _is_operand(token: _Token) -> bool:
    return isinstance(token, _Cell | _Number)


def _word(token: _Token) -> str | None:
    return token.text if isinstance(token, _Word) else None


def _cells(tokens: list[_Token]) -> list[CellReference]:
    return [token.reference for token in tokens if isinstance(token, _Cell)]


def _without(tokens: list[_Token], index: int) -> list[_Token]:
    return tokens[:index] + tokens[index + 1 :]


def _operand(token: _Token) -> str:
    match token:
        case _Cell(reference):
            return reference.address
        case _Number(value):
            return formula_number(value)
        case _Column(letter):
            return f"{letter}:{letter}"
        case _Word(text, _):
            return text
