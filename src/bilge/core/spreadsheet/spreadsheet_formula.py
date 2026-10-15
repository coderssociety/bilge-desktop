"""Checks a formula written by the language model before it goes into a cell. Formulas can reach outside the
sheet (fetch a URL, run a program, read another file), and text the model saw could steer what it writes, so
only plain calculation is let through."""

MAX_LENGTH = 300
# Network, programs, other files and links.
_BLOCKED_FUNCTIONS = (
    "WEBSERVICE",
    "FILTERXML",
    "HYPERLINK",
    "CALL",
    "REGISTER",
    "EXEC",
    "RTD",
    "IMAGE",
    "INFO",
    "CELL",
    "INDIRECT",
    "DDE",
)
_ALLOWED_SYMBOLS = frozenset('+-*/^():,;.%<>=&$! "')


def is_safe(formula: str) -> bool:
    if not formula.startswith("=") or not 1 < len(formula) <= MAX_LENGTH:
        return False
    if not all(_is_allowed(character) for character in formula):
        return False
    upper = formula.upper()
    return not any(name + "(" in upper for name in _BLOCKED_FUNCTIONS)


def _is_allowed(character: str) -> bool:
    return (character.isascii() and character.isalnum()) or character in _ALLOWED_SYMBOLS
