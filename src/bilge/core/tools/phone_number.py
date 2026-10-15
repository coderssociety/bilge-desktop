"""Phone numbers as messaging apps expect them: digits only, with a country code."""

_MIN_DIGITS = 7
_MAX_DIGITS = 15
_ALLOWED_SEPARATORS = frozenset(" +-().")


def normalized(text: str, default_country_code: str = "90") -> str | None:
    """ "0532 123 45 67" -> "+905321234567"; "+90 (532) 123-45-67" -> "+905321234567";
    "532 123 4567" -> "+905321234567". None when the text is not a plausible phone number."""
    has_plus = text.strip().startswith("+")
    digits = "".join(character for character in text if character.isnumeric())
    is_plausible = _MIN_DIGITS <= len(digits) <= _MAX_DIGITS and all(
        character.isnumeric() or character in _ALLOWED_SEPARATORS for character in text
    )
    if not is_plausible:
        return None
    if has_plus:
        return "+" + digits
    if digits.startswith("00"):
        return "+" + digits[2:]
    if digits.startswith("0"):
        return "+" + default_country_code + digits[1:]
    if len(digits) == 10:
        return "+" + default_country_code + digits
    return "+" + digits
