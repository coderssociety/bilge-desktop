"""Turns common spoken Turkish arithmetic (already digitized by turkish_number_parser) into an
expression for arithmetic_evaluator, and checks that a model-written expression only uses numbers
the user actually said. The model has invented whole calculations for a bare "Evet"."""

import re

from bilge.core.text import folded, lowercased

_NUMBER = r"(\d+(?:[.,]\d+)?)"
# [^\W\d_] is a Unicode letter; Python's re has no \p{L}.
_SUFFIX = r"(?:'[^\W\d_]+)?"
_FILLERS = frozenset(
    ["kac", "eder", "kactir", "ne", "kadar", "hesapla", "nedir", "olur", "yapar", "acaba", "bana", "lutfen", "soyle"]
)
_OPERATOR_WORDS: dict[str, str] = {
    "arti": "+", "+": "+", "eksi": "-", "-": "-", "carpi": "*", "kere": "*", "x": "*", "×": "*", "*": "*",
    "bolu": "/", "÷": "/", "/": "/", "ussu": "^", "^": "^",
}  # fmt: skip
_OPERATORS = frozenset(_OPERATOR_WORDS.values())
_FRACTIONS: tuple[tuple[str, int], ...] = (("yarisi", 2), ("ceyregi", 4), ("ucte biri", 3))

_PERCENT_OF = re.compile(rf"^{_NUMBER}{_SUFFIX}\s+(?:%|yüzde\s*){_NUMBER}{_SUFFIX}(.*)$")
_FRACTION_OF = re.compile(rf"^{_NUMBER}{_SUFFIX}\s+(.+)$")
_POWER_OF = re.compile(rf"^{_NUMBER}{_SUFFIX}\s+{_NUMBER}\.?\s*kuvveti(.*)$")
_NUMBER_WORD = re.compile(r"\d+(?:[.,]\d+)?")
_NUMBER_SEARCH = re.compile(_NUMBER)


def expression(command: str) -> str | None:
    text = lowercased(command).strip()
    return _percent_of(text) or _fraction_of(text) or _power_of(text) or _operator_chain(text)


def is_grounded(expression: str, command: str) -> bool:
    folded_command = folded(command)
    allowed = set(_numbers(command))
    if "%" in command or "yuzde" in folded_command:
        allowed.add(100)
    if "yari" in folded_command:
        allowed.add(2)
    if "ceyrek" in folded_command:
        allowed.add(4)
    if "ucte" in folded_command:
        allowed.add(3)
    used = _numbers(expression)
    return bool(used) and all(number in allowed for number in used)


def _percent_of(text: str) -> str | None:
    match = _PERCENT_OF.match(text)
    if match is None or not _only_fillers(match.group(3)):
        return None
    return f"{match.group(1)} * {match.group(2)} / 100"


def _fraction_of(text: str) -> str | None:
    match = _FRACTION_OF.match(text)
    if match is None:
        return None
    rest = folded(match.group(2))
    for word, divisor in _FRACTIONS:
        if rest.startswith(word) and _only_fillers(rest[len(word) :]):
            return f"{match.group(1)} / {divisor}"
    return None


def _power_of(text: str) -> str | None:
    match = _POWER_OF.match(text)
    if match is None or not _only_fillers(match.group(3)):
        return None
    return f"{match.group(1)} ^ {match.group(2)}"


def _operator_chain(text: str) -> str | None:
    """ "45 artı 17 eksi 3" -> "45 + 17 - 3"; everything except numbers, operators and filler words rejects."""
    tokens: list[str] = []
    for raw in (word for word in text.split(" ") if word):
        word = raw.strip("?.!,")
        key = folded(word)
        op = _OPERATOR_WORDS.get(key) or _OPERATOR_WORDS.get(word)
        if op is not None:
            tokens.append(op)
        elif _NUMBER_WORD.fullmatch(word):
            tokens.append(word)
        elif key in _FILLERS or not key:
            continue
        else:
            return None
    is_alternating = (
        len(tokens) >= 3
        and len(tokens) % 2 == 1
        and all((index % 2 == 0) == (token not in _OPERATORS) for index, token in enumerate(tokens))
    )
    return " ".join(tokens) if is_alternating else None


def _only_fillers(rest: str) -> bool:
    return all(word in _FILLERS for word in folded(rest).split())


def _numbers(text: str) -> list[float]:
    return [float(match.replace(",", ".")) for match in _NUMBER_SEARCH.findall(text) if match.isascii()]
