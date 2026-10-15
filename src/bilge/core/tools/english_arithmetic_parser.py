"""English counterpart of turkish_arithmetic_parser: "15 percent of 240", "48 divided by 6", "3 squared".
Recognizers write English numbers as digits, so only digits are read."""

import re

from bilge.core.language import AssistantLanguage
from bilge.core.tools.arithmetic_evaluator import display

_NUMBER = r"(\d+(?:\.\d+)?)"
_FILLERS = frozenset(
    [
        "what", "whats", "is", "how", "much", "calculate", "equals", "equal", "please", "tell", "me", "the",
        "answer", "can", "you", "work", "out", "do",
    ]
)  # fmt: skip
_PHRASES: tuple[tuple[str, str], ...] = (
    ("multiplied by", "times"),
    ("divided by", "over"),
    ("to the power of", "^"),
    ("raised to", "^"),
)
_OPERATOR_WORDS: dict[str, str] = {
    "plus": "+", "+": "+", "minus": "-", "-": "-", "times": "*", "x": "*", "×": "*", "*": "*",
    "over": "/", "÷": "/", "/": "/", "^": "^",
}  # fmt: skip
_OPERATORS = frozenset(_OPERATOR_WORDS.values())
_FRACTIONS: tuple[tuple[str, int], ...] = (("half", 2), ("quarter", 4), ("third", 3))

_THOUSANDS_SEPARATOR = re.compile(r"(?<=\d),(?=\d{3}\b)")
_PERCENT_SIGN = re.compile(r"(?<=\d)\s*%")
_PERCENT_OF = re.compile(rf"^{_NUMBER} percent of {_NUMBER}$")
_FRACTION_OF = {word: re.compile(rf"^(?:a |one )?{word} of {_NUMBER}$") for word, _ in _FRACTIONS}
_SQUARED = re.compile(rf"^{_NUMBER} squared$")
_CUBED = re.compile(rf"^{_NUMBER} cubed$")
_NUMBER_WORD = re.compile(r"\d+(?:\.\d+)?")


def expression(command: str) -> str | None:
    text = _normalized(command)
    return _percent_of(text) or _fraction_of(text) or _power(text) or _operator_chain(text)


def is_grounded(expression: str, command: str) -> bool:
    """True when every number in a model-written expression was said, allowing the 100 of a percentage
    and the divisor of "half"/"a third"/"a quarter"."""
    text = _normalized(command)
    allowed = set(_numbers(text))
    if "percent" in text or "%" in text:
        allowed.add(100)
    if "half" in text or "squared" in text:
        allowed.add(2)
    if "third" in text or "cubed" in text:
        allowed.add(3)
    if "quarter" in text:
        allowed.add(4)
    used = _numbers(expression)
    return bool(used) and all(number in allowed for number in used)


def _normalized(command: str) -> str:
    """Lowercased, thousands separators dropped ("1,000" -> "1000"), punctuation and fillers removed."""
    text = _THOUSANDS_SEPARATOR.sub("", command.lower())
    text = _PERCENT_SIGN.sub(" percent", text)
    text = text.replace("what's", "what")
    for phrase, replacement in _PHRASES:
        text = text.replace(phrase, replacement)
    words = [_trimmed(word) for word in text.split()]
    return " ".join(word for word in words if word and word not in _FILLERS)


def _trimmed(word: str) -> str:
    word = word.strip("?!, ")
    return word[:-1] if word.endswith(".") else word


def _percent_of(text: str) -> str | None:
    match = _PERCENT_OF.match(text)
    return f"{match.group(2)} * {match.group(1)} / 100" if match else None


def _fraction_of(text: str) -> str | None:
    for word, divisor in _FRACTIONS:
        match = _FRACTION_OF[word].match(text)
        if match:
            return f"{match.group(1)} / {divisor}"
    return None


def _power(text: str) -> str | None:
    if match := _SQUARED.match(text):
        return f"{match.group(1)} ^ 2"
    if match := _CUBED.match(text):
        return f"{match.group(1)} ^ 3"
    return None


def _operator_chain(text: str) -> str | None:
    """ "45 plus 17 minus 3" -> "45 + 17 - 3"; any other word rejects."""
    tokens: list[str] = []
    for word in (word for word in text.split(" ") if word):
        if word in _OPERATOR_WORDS:
            tokens.append(_OPERATOR_WORDS[word])
        elif _NUMBER_WORD.fullmatch(word):
            tokens.append(word)
        elif word.endswith("squared") and (base := _float(word[: -len("squared")])) is not None:
            tokens.append(f"{display(base, AssistantLanguage.ENGLISH)} ^ 2")
        else:
            return None
    is_alternating = (
        len(tokens) >= 3
        and len(tokens) % 2 == 1
        and all((index % 2 == 0) == (token not in _OPERATORS) for index, token in enumerate(tokens))
    )
    return " ".join(tokens) if is_alternating else None


def _float(text: str) -> float | None:
    # Swift's Double(String) takes no underscores or non-ASCII digits; float() would.
    if not text.isascii() or "_" in text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _numbers(text: str) -> list[float]:
    return [float(match) for match in _NUMBER_WORD.findall(text) if match.isascii()]
