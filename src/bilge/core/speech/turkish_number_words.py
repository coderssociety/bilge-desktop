_ONES = ("", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz")
_TENS = ("", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan")
_SCALES = ((1_000_000_000_000, "trilyon"), (1_000_000_000, "milyar"), (1_000_000, "milyon"), (1000, "bin"))
_MAX_CARDINAL_DIGITS = 15

MONTH_NAMES = (
    "ocak",
    "şubat",
    "mart",
    "nisan",
    "mayıs",
    "haziran",
    "temmuz",
    "ağustos",
    "eylül",
    "ekim",
    "kasım",
    "aralık",
)


def cardinal(value: int) -> str:
    if value == 0:
        return "sıfır"
    if value < 0:
        return "eksi " + cardinal(-value)
    words: list[str] = []
    rest = value
    for scale, word in _SCALES:
        if rest < scale:
            continue
        count, rest = divmod(rest, scale)
        # Turkish says "bin", not "bir bin"; larger scales keep "bir".
        if not (word == "bin" and count == 1):
            words.append(_below_thousand(count))
        words.append(word)
    if rest > 0:
        words.append(_below_thousand(rest))
    return " ".join(words)


def digits_preserving_leading_zeros(digits: str) -> str:
    """Reads a digit string such as minutes ("05") or decimals ("05") keeping leading zeros audible."""
    remainder = digits.lstrip("0")
    zeros = len(digits) - len(remainder)
    words = ["sıfır"] * (zeros if remainder else max(zeros, 1))
    # Swift reads nothing for a remainder that overflows Int and crashes on one past trillions.
    if remainder.isascii() and remainder.isdigit() and len(remainder) <= _MAX_CARDINAL_DIGITS:
        words.append(cardinal(int(remainder)))
    return " ".join(words)


def _below_thousand(value: int) -> str:
    words: list[str] = []
    hundreds = value // 100
    if hundreds > 0:
        words.append("yüz" if hundreds == 1 else _ONES[hundreds] + " yüz")
    tens_digit = value % 100 // 10
    if tens_digit > 0:
        words.append(_TENS[tens_digit])
    ones_digit = value % 10
    if ones_digit > 0:
        words.append(_ONES[ones_digit])
    return " ".join(words)
