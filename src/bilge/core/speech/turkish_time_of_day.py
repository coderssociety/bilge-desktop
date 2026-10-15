"""Resolves "akşam 8'de" / "öğleden sonra 3 buçukta" (after digitizing) to 24-hour "20:00'de" / "15:30'da",
so the model never has to do the AM/PM arithmetic it gets wrong."""

import re

from bilge.core.text import lowercased

# [^\W\d_] is a Unicode letter; Python's re has no \p{L}.
_PATTERN = re.compile(
    r"(?<![^\W\d_])(sabah|öğleden sonra|öğlen|öğleyin|akşam|gece)\s+(\d{1,2})(?:'([^\W\d_]+))?"
    r"(?:\s+buçuk([^\W\d_]*))?(?![^\W\d_])",
    re.IGNORECASE,
)


def resolve(text: str) -> str:
    return _PATTERN.sub(_replacement, text)


def _replacement(match: re.Match[str]) -> str:
    hour24 = _hour24(int(match.group(2)), lowercased(match.group(1)))
    if hour24 is None:
        return match.group(0)
    has_half = match.group(4) is not None
    suffix = _softened(match.group(4)) if has_half else (match.group(3) or "")
    clock = f"{hour24:02d}:{30 if has_half else 0:02d}"
    return clock + ("'" + suffix if suffix else "")


def _hour24(hour: int, part_of_day: str) -> int | None:
    if not 0 <= hour <= 12:
        return None
    match part_of_day:
        case "sabah":
            return 0 if hour == 12 else hour
        case "öğlen" | "öğleyin":
            return 12 if hour == 12 else hour + 12 if 1 <= hour <= 5 else hour
        case "öğleden sonra" | "akşam":
            return 12 if hour == 12 else hour + 12
        case "gece":
            return 0 if hour == 12 else hour + 12 if 6 <= hour <= 11 else hour
        case _:
            return None


def _softened(suffix: str) -> str:
    """ "buçukta" ends in a hardened consonant; after "HH:30" ("otuz") the suffix is "da"/"de"."""
    return "d" + suffix[1:] if suffix.startswith("t") else suffix
