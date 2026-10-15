"""Recursive-descent evaluator for + - * / % ^ and parentheses. Deliberately not `eval`,
which can run arbitrary code when fed model-generated text."""

import math
from dataclasses import dataclass

from bilge.core.language import AssistantLanguage

_MAX_FRACTION_DIGITS = 4
_OPERATORS = "+-*/%^×÷"


class EvaluationError(Exception):
    pass


@dataclass
class Empty(EvaluationError):
    pass


@dataclass
class UnexpectedCharacter(EvaluationError):
    character: str


@dataclass
class UnexpectedEnd(EvaluationError):
    pass


@dataclass
class UnbalancedParentheses(EvaluationError):
    pass


@dataclass
class DivisionByZero(EvaluationError):
    pass


@dataclass
class NotFinite(EvaluationError):
    pass


@dataclass(frozen=True)
class _Number:
    value: float


@dataclass(frozen=True)
class _Operator:
    symbol: str


@dataclass(frozen=True)
class _Open:
    pass


@dataclass(frozen=True)
class _Close:
    pass


_Token = _Number | _Operator | _Open | _Close


def evaluate(expression: str) -> float:
    parser = _Parser(_tokenize(expression))
    if not parser.tokens:
        raise Empty()
    value = parser.parse_expression()
    if not parser.is_at_end:
        raise UnbalancedParentheses()
    if not math.isfinite(value):
        raise NotFinite()
    return value


def display(value: float, language: AssistantLanguage = AssistantLanguage.TURKISH) -> str:
    """Decimal comma in Turkish ("22,5"), point in English ("22.5")."""
    text = f"{value:.{_MAX_FRACTION_DIGITS}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",") if language is AssistantLanguage.TURKISH else text


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character.isspace():
            index += 1
        elif character.isnumeric():
            end = index
            while end < len(text) and (text[end].isnumeric() or text[end] in ".,"):
                end += 1
            tokens.append(_Number(_parse_literal(text[index:end].replace(",", "."), character)))
            index = end
        elif character in _OPERATORS:
            tokens.append(_Operator("*" if character == "×" else "/" if character == "÷" else character))
            index += 1
        elif character == "(":
            tokens.append(_Open())
            index += 1
        elif character == ")":
            tokens.append(_Close())
            index += 1
        else:
            raise UnexpectedCharacter(character)
    return tokens


def _parse_literal(literal: str, first: str) -> float:
    # Python's float() also takes non-ASCII digits, which Swift's Double(String) rejects.
    if not literal.isascii():
        raise UnexpectedCharacter(first)
    try:
        return float(literal)
    except ValueError:
        raise UnexpectedCharacter(first) from None


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self.tokens = tokens
        self.position = 0

    @property
    def is_at_end(self) -> bool:
        return self.position == len(self.tokens)

    def parse_expression(self) -> float:
        value = self.parse_term()
        while (op := self._peek_operator()) in ("+", "-"):
            self.position += 1
            rhs = self.parse_term()
            value = value + rhs if op == "+" else value - rhs
        return value

    def parse_term(self) -> float:
        value = self.parse_power()
        while (op := self._peek_operator()) in ("*", "/", "%"):
            self.position += 1
            rhs = self.parse_power()
            if op != "*" and rhs == 0:
                raise DivisionByZero()
            if op == "*":
                value = value * rhs
            elif op == "/":
                value = value / rhs
            else:
                value = _remainder(value, rhs)
        return value

    def parse_power(self) -> float:
        base = self.parse_unary()
        if self._peek_operator() != "^":
            return base
        self.position += 1
        exponent = self.parse_power()
        try:
            result = math.pow(base, exponent)
        except (OverflowError, ValueError):
            raise NotFinite() from None
        if not math.isfinite(result):
            raise NotFinite()
        return result

    def parse_unary(self) -> float:
        op = self._peek_operator()
        if op in ("-", "+"):
            self.position += 1
            value = self.parse_unary()
            return -value if op == "-" else value
        return self.parse_primary()

    def parse_primary(self) -> float:
        token = self._next()
        match token:
            case None:
                raise UnexpectedEnd()
            case _Number(value):
                return value
            case _Open():
                value = self.parse_expression()
                if not isinstance(self._next(), _Close):
                    raise UnbalancedParentheses()
                return value
            case _Close():
                raise UnbalancedParentheses()
            case _Operator(symbol):
                raise UnexpectedCharacter(symbol)

    def _peek(self) -> _Token | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def _peek_operator(self) -> str | None:
        token = self._peek()
        return token.symbol if isinstance(token, _Operator) else None

    def _next(self) -> _Token | None:
        token = self._peek()
        self.position += 1
        return token


def _remainder(value: float, divisor: float) -> float:
    """Swift's truncatingRemainder: NaN instead of an exception for an infinite dividend."""
    try:
        return math.fmod(value, divisor)
    except ValueError:
        return math.nan
