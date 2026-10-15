"""Rewrites spelled-out Turkish numbers as digits before text reaches the language model, which is
unreliable at compound numbers ("üç yüz yirmi" became 300). Ambiguous words are only converted
in an unmistakably numeric context: "bir" (also "a"), "on" with a suffix ("onu" = "it"), "yüz" ("face")."""

import unicodedata
from dataclasses import dataclass

from bilge.core.text import lowercased, normalized

_WORDS: dict[str, int] = {
    "sıfır": 0,
    "bir": 1,
    "iki": 2,
    "üç": 3,
    "dört": 4,
    "dörd": 4,
    "beş": 5,
    "altı": 6,
    "yedi": 7,
    "sekiz": 8,
    "dokuz": 9,
    "on": 10,
    "yirmi": 20,
    "otuz": 30,
    "kırk": 40,
    "elli": 50,
    "altmış": 60,
    "yetmiş": 70,
    "seksen": 80,
    "doksan": 90,
    "yüz": 100,
    "bin": 1000,
    "milyon": 1_000_000,
    "milyar": 1_000_000_000,
    "trilyon": 1_000_000_000_000,
}
# Case, possessive and ordinal endings that follow numbers. Deliberately excludes "na/nda/ne/nde",
# which turn "altı" into "altına/altında" (under it).
_SUFFIXES = frozenset(
    [
        "sını", "sini", "sunu", "sünü", "nın", "nin", "nun", "nün", "ıncı", "inci", "uncu", "üncü", "ncı", "nci",
        "ncu", "ncü", "lık", "lik", "luk", "lük", "yla", "yle", "dan", "den", "tan", "ten", "dır", "dir", "dur",
        "dür", "tır", "tir", "tur", "tür", "şar", "şer", "da", "de", "ta", "te", "ya", "ye", "yı", "yi", "yu", "yü",
        "ın", "in", "un", "ün", "sı", "si", "su", "sü", "la", "le", "ar", "er", "a", "e", "ı", "i", "u", "ü",
    ]
)  # fmt: skip
_UNIT_WORDS = frozenset(
    [
        "dakika", "dakikalık", "saniye", "saniyelik", "saat", "saatlik", "gün", "günlük", "hafta", "ay", "yıl",
        "kez", "kere", "tane", "adet", "kişi", "lira", "dolar", "avro", "euro", "derece", "kilo", "metre", "litre",
        "sayfa",
    ]
)  # fmt: skip
_AMBIGUOUS = frozenset(["bir", "on", "yüz"])


@dataclass(frozen=True)
class _NumberToken:
    value: int
    suffix: str
    stem: str


def digitize(text: str) -> str:
    tokens = text.split(" ")
    output: list[str] = []
    index = 0
    while index < len(tokens):
        run = _number_run(tokens, index)
        if not run or not _is_unambiguous(run, tokens, index):
            output.append(tokens[index])
            index += 1
            continue
        last = run[-1]
        trailing = _trailing_punctuation(tokens[index + len(run) - 1])
        output.append(str(_value(run)) + ("'" + last.suffix if last.suffix else "") + trailing)
        index += len(run)
    return " ".join(output)


def _number_run(tokens: list[str], start: int) -> list[_NumberToken]:
    """Longest sequence of number words; only the final word may carry a suffix."""
    run: list[_NumberToken] = []
    index = start
    while index < len(tokens):
        token = _parse(tokens[index])
        if token is None:
            break
        if run and not _can_follow(token.value, run[-1].value):
            break
        run.append(token)
        index += 1
        if token.suffix or _trailing_punctuation(tokens[index - 1]):
            break
    return run


def _parse(raw: str) -> _NumberToken | None:
    punctuation = _trailing_punctuation(raw)
    core = lowercased(raw[: len(raw) - len(punctuation)])
    if not core or core == "yüzde":
        return None
    if core in _WORDS:
        return _NumberToken(_WORDS[core], "", core)
    for stem, value in _WORDS.items():
        if not core.startswith(stem):
            continue
        rest = core[len(stem) :].replace("'", "")
        if rest in _SUFFIXES:
            return _NumberToken(value, rest, stem)
    return None


def _can_follow(next_value: int, previous: int) -> bool:
    """Rejects "bir iki" (counting) or "beş on" style sequences that are not one number."""
    if next_value >= 100 or previous >= 100:
        return True
    return previous >= 10 and previous % 10 == 0 and next_value < 10


def _is_unambiguous(run: list[_NumberToken], tokens: list[str], start: int) -> bool:
    if len(run) != 1 or run[0].stem not in _AMBIGUOUS:
        return True
    previous = lowercased(tokens[start - 1]) if start > 0 else ""
    next_word = normalized(tokens[start + 1]) if start + 1 < len(tokens) else ""
    numeric_context = previous == "saat" or next_word in _UNIT_WORDS
    if run[0].stem == "on":
        return not run[0].suffix or numeric_context
    return numeric_context


def _value(run: list[_NumberToken]) -> int:
    total = 0
    current = 0
    for token in run:
        if token.value < 100:
            current += token.value
        elif token.value == 100:
            current = max(current, 1) * 100
        else:
            total += max(current, 1) * token.value
            current = 0
    return total + current


def _is_punctuation(character: str) -> bool:
    return unicodedata.category(character).startswith("P") and character not in "'’"


def _trailing_punctuation(token: str) -> str:
    end = len(token)
    while end > 0 and _is_punctuation(token[end - 1]):
        end -= 1
    return token[end:]
