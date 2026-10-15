"""Checks a formula written by the language model before it goes into a cell. Formulas can reach outside the
sheet (fetch a URL, run a program, read another file), and text the model saw could steer what it writes, so
only plain calculation is let through."""

import re

MAX_LENGTH = 300
# Plain calculation only. A list of what is allowed rather than what isn't: Calc also runs a document's own Basic
# functions when a formula names them, and spaces before "(" would slip past a list of forbidden names.
ALLOWED_FUNCTIONS = frozenset(
    {
        "SUM", "AVERAGE", "MIN", "MAX", "COUNT", "COUNTA", "COUNTBLANK", "COUNTIF", "COUNTIFS", "SUMIF", "SUMIFS",
        "AVERAGEIF", "AVERAGEIFS", "SUMPRODUCT", "PRODUCT", "MEDIAN", "MODE", "STDEV", "VAR", "ROUND", "ROUNDUP",
        "ROUNDDOWN", "INT", "TRUNC", "ABS", "SQRT", "POWER", "MOD", "IF", "IFS", "IFERROR", "AND", "OR", "NOT",
        "TODAY", "NOW", "DATE", "YEAR", "MONTH", "DAY", "WEEKDAY", "DAYS", "EDATE", "LEFT", "RIGHT", "MID", "LEN",
        "UPPER", "LOWER", "PROPER", "TRIM", "CONCATENATE", "CONCAT", "TEXT", "VALUE", "VLOOKUP", "HLOOKUP",
        "XLOOKUP", "INDEX", "MATCH", "PERCENTAGE", "RANK", "LARGE", "SMALL", "CEILING", "FLOOR", "PI",
    }
)  # fmt: skip
_ALLOWED_SYMBOLS = frozenset('+-*/^():,;.%<>=&$! "')
_QUOTED = re.compile(r'"[^"]*"')
_CALL = re.compile(r"([A-Za-z_][A-Za-z0-9_.]*)\s*\(")


def is_safe(formula: str) -> bool:
    if not formula.startswith("=") or not 1 < len(formula) <= MAX_LENGTH:
        return False
    if not all(_is_allowed(character) for character in formula):
        return False
    outside_quotes = _QUOTED.sub('""', formula)
    if outside_quotes.count('"') % 2:
        return False
    return all(name.upper() in ALLOWED_FUNCTIONS for name in _CALL.findall(outside_quotes))


def _is_allowed(character: str) -> bool:
    return (character.isascii() and character.isalnum()) or character in _ALLOWED_SYMBOLS
