"""Turkish-aware text helpers shared by every parser."""

import unicodedata

_APOSTROPHES = frozenset("'’‘`´")
_DIACRITIC_FOLDS = str.maketrans(
    {"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u"}
)


def lowercased(text: str) -> str:
    """Lowercase with Turkish rules: "I" becomes "ı" and "İ" becomes "i" (Python's str.lower gets both wrong)."""
    text = unicodedata.normalize("NFC", text)
    return text.replace("I", "ı").replace("İ", "i").lower()


def normalized(text: str) -> str:
    """Lowercase words separated by single spaces; apostrophes are dropped so "Safari'yi" stays one word."""
    mapped = "".join(
        "" if ch in _APOSTROPHES else (ch if ch.isalpha() or ch.isnumeric() else " ") for ch in lowercased(text)
    )
    return " ".join(mapped.split())


def folded(text: str) -> str:
    """`normalized` without Turkish letters, for matching what recognizers spell either way."""
    return normalized(text).translate(_DIACRITIC_FOLDS)


def levenshtein(lhs: str | list, rhs: str | list) -> int:
    if not lhs:
        return len(rhs)
    if not rhs:
        return len(lhs)
    previous = list(range(len(rhs) + 1))
    for i, left in enumerate(lhs):
        current = [i + 1] + [0] * len(rhs)
        for j, right in enumerate(rhs):
            current[j + 1] = min(previous[j] + (left != right), previous[j + 1] + 1, current[j] + 1)
        previous = current
    return previous[len(rhs)]


def similarity(lhs: str, rhs: str) -> float:
    """1 for identical strings, 0 for completely different ones (normalized Levenshtein)."""
    longest = max(len(lhs), len(rhs))
    return 1.0 if longest == 0 else 1 - levenshtein(lhs, rhs) / longest


_BACK_VOWELS = frozenset("aıou")
_FRONT_VOWELS = frozenset("eiöü")
_HARD_CONSONANTS = frozenset("çfhkpsşt")


def locative(name: str) -> str:
    """Case suffix for a proper name: "İstanbul'da", "İzmir'de", "Paris'te", "Kars'ta"."""
    lower = lowercased(name)
    last_vowel = next((ch for ch in reversed(lower) if ch in _BACK_VOWELS or ch in _FRONT_VOWELS), None)
    vowel = "e" if last_vowel is None else ("a" if last_vowel in _BACK_VOWELS else "e")
    consonant = "t" if lower and lower[-1] in _HARD_CONSONANTS else "d"
    return f"{name}'{consonant}{vowel}"


def time_locative(hour: int, minute: int) -> str:
    """ "10:00'da", "11:00'de", "13:00'te", "15:40'ta": the ending follows the last number as spoken
    (the minutes, or the hour on the hour)."""
    spoken = minute if minute > 0 else hour
    ones, tens = spoken % 10, spoken // 10 % 10
    if ones in (1, 2, 7, 8):
        ending = "de"
    elif ones in (3, 4, 5):
        ending = "te"
    elif ones in (6, 9):
        ending = "da"
    elif tens in (2, 5):
        ending = "de"
    elif tens == 4:
        ending = "ta"
    else:
        ending = "da"
    return f"{hour:02d}:{minute:02d}'{ending}"
