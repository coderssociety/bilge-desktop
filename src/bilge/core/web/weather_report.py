"""Turns Open-Meteo values into a short spoken sentence in the assistant's language."""

import math

from bilge.core.language import AssistantLanguage
from bilge.core.text import locative

_RAIN_CHANCE_WORTH_MENTIONING = 30

# WMO weather interpretation codes, as Open-Meteo reports them.
_TURKISH_CONDITIONS = {
    0: "açık",
    1: "çoğunlukla açık",
    2: "parçalı bulutlu",
    3: "kapalı",
    45: "sisli",
    48: "sisli",
    **dict.fromkeys((51, 53, 55, 56, 57), "çiseleyen yağmurlu"),
    61: "hafif yağmurlu",
    80: "hafif yağmurlu",
    63: "yağmurlu",
    81: "yağmurlu",
    65: "sağanak yağışlı",
    82: "sağanak yağışlı",
    66: "dondurucu yağmurlu",
    67: "dondurucu yağmurlu",
    71: "hafif karlı",
    85: "hafif karlı",
    **dict.fromkeys((73, 75, 77, 86), "karlı"),
    95: "gök gürültülü fırtınalı",
    96: "dolulu fırtınalı",
    99: "dolulu fırtınalı",
}
_ENGLISH_CONDITIONS = {
    0: "clear",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "foggy",
    **dict.fromkeys((51, 53, 55, 56, 57), "drizzly"),
    61: "lightly rainy",
    80: "lightly rainy",
    63: "rainy",
    81: "rainy",
    65: "pouring",
    82: "pouring",
    66: "freezing rain",
    67: "freezing rain",
    71: "lightly snowy",
    85: "lightly snowy",
    **dict.fromkeys((73, 75, 77, 86), "snowy"),
    95: "stormy with thunder",
    96: "stormy with hail",
    99: "stormy with hail",
}


def condition(code: int, language: AssistantLanguage = AssistantLanguage.TURKISH) -> str:
    if language is AssistantLanguage.ENGLISH:
        return _ENGLISH_CONDITIONS.get(code, "changeable")
    return _TURKISH_CONDITIONS.get(code, "değişken")


def current(city: str, temperature: float, code: int, language: AssistantLanguage = AssistantLanguage.TURKISH) -> str:
    if language is AssistantLanguage.ENGLISH:
        return f"In {city} it's {condition(code, language)} right now, {_rounded(temperature)} degrees."
    return f"{locative(city)} şu an hava {condition(code)}, {_rounded(temperature)} derece."


def daily(
    city: str,
    day_name: str,
    minimum: float,
    maximum: float,
    code: int,
    rain_chance: int | None,
    language: AssistantLanguage = AssistantLanguage.TURKISH,
) -> str:
    """`day_name` is "bugün", "yarın" or a weekday ("today", "tomorrow" or a weekday in English)."""
    mentions_rain = rain_chance is not None and rain_chance >= _RAIN_CHANCE_WORTH_MENTIONING
    low, high = _rounded(minimum), _rounded(maximum)
    if language is AssistantLanguage.ENGLISH:
        sentence = f"In {city} {day_name} it will be {condition(code, language)}, between {low} and {high} degrees."
        return sentence + (f" There's a {rain_chance} percent chance of rain." if mentions_rain else "")
    sentence = f"{locative(city)} {day_name} hava {condition(code)}, sıcaklık {low} ile {high} derece arasında."
    return sentence + (f" Yağış ihtimali yüzde {rain_chance}." if mentions_rain else "")


def _rounded(value: float) -> int:
    """Half away from zero like Swift's rounded(); Python's round() rounds half to even."""
    return int(math.copysign(math.floor(abs(value) + 0.5), value))
