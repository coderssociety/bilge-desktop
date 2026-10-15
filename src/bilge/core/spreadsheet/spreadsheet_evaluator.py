"""Answers spreadsheet questions ("B1'den B9'a kadar toplam kaç") from cell values read out of the sheet. Excel's
own `evaluate` is not reachable through AppleScript, and nothing is written to work it out. Covers the formulas
`spreadsheet_command` produces for `Evaluate`."""

import re
from collections.abc import Callable, Mapping, Sequence

from bilge.core.spreadsheet.spreadsheet_tokens import parse_double
from bilge.core.tools import arithmetic_evaluator
from bilge.core.tools.arithmetic_evaluator import EvaluationError

_REFERENCE = re.compile(r"\$?[A-Z]{1,3}\$?[0-9]*(?::\$?[A-Z]{1,3}\$?[0-9]*)?")
_FUNCTION = re.compile(r"([A-Z]+)\((.*)\)")


def references(formula: str) -> list[str]:
    """The cells and ranges the formula reads, e.g. ["B1:B9"] or ["B2", "B1"]."""
    body = formula.removeprefix("=")
    match = _FUNCTION.fullmatch(body)
    arguments = match.group(2) if match else body
    seen: list[str] = []
    for found in _REFERENCE.finditer(arguments):
        reference = found.group(0)
        is_address = any(character.isnumeric() for character in reference) or ":" in reference
        if is_address and reference not in seen:
            seen.append(reference)
    return seen


def evaluate(formula: str, values: Mapping[str, Sequence[str]]) -> float | None:
    """`values` holds what was read for each reference, one entry per cell, as text."""
    body = formula.removeprefix("=")
    match = _FUNCTION.fullmatch(body)
    if match:
        return _aggregate(match.group(1), _arguments(match.group(2), values))
    expression = body
    for reference in sorted(references(body), key=len, reverse=True):
        read = values.get(reference)
        if not read:
            return None
        value = 0.0 if read[0] == "" else _number(read[0])
        if value is None:
            return None
        expression = expression.replace(reference, f"({value!r})")
    try:
        return arithmetic_evaluator.evaluate(expression)
    except EvaluationError:
        return None


def _arguments(text: str, values: Mapping[str, Sequence[str]]) -> list[float]:
    numbers: list[float] = []
    for argument in text.split(","):
        if not argument:
            continue
        key = argument.strip(" \t")
        literal = parse_double(key)
        if literal is not None:
            numbers.append(literal)
            continue
        numbers.extend(number for cell in values.get(key, ()) if (number := _number(cell)) is not None)
    return numbers


_AGGREGATES: dict[str, Callable[[list[float]], float | None]] = {
    "SUM": lambda numbers: sum(numbers, 0.0),
    "AVERAGE": lambda numbers: sum(numbers, 0.0) / len(numbers) if numbers else None,
    "MAX": lambda numbers: max(numbers, default=None),
    "MIN": lambda numbers: min(numbers, default=None),
    "COUNT": lambda numbers: float(len(numbers)),
}


def _aggregate(function: str, numbers: list[float]) -> float | None:
    aggregate = _AGGREGATES.get(function)
    return aggregate(numbers) if aggregate else None


def _number(text: str) -> float | None:
    """Cell text as AppleScript gives it: "20.5", or "20,5" where the system uses a decimal comma."""
    trimmed = text.strip(" \t")
    value = parse_double(trimmed)
    if value is not None or "." in trimmed:
        return value
    return parse_double(trimmed.replace(",", "."))
