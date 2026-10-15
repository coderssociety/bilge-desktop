"""Text that is safe to type as key events: control characters (Return, Tab, Escape, line and
paragraph separators…) would act as keys and could submit a form or a message."""

import unicodedata

_KEY_CATEGORIES = frozenset({"Cc", "Zl", "Zp"})


def sanitized(text: str) -> str:
    spaced = "".join(" " if unicodedata.category(ch) in _KEY_CATEGORIES else ch for ch in text)
    return " ".join(part for part in spaced.split(" ") if part)
