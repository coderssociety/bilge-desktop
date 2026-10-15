"""The SentenceSplitter, SpokenText and TurkishSpeechNormalizer cases of the Swift EnglishLanguageTests."""

import pytest

from bilge.core.language import AssistantLanguage
from bilge.core.speech import spoken_text, turkish_speech_normalizer
from bilge.core.speech.sentence_splitter import split


def test_english_abbreviations_do_not_end_a_sentence() -> None:
    assert split("Mr. Smith is here. He is waiting.") == ["Mr. Smith is here.", "He is waiting."]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("It is 25% cheaper.", "It is 25 percent cheaper."),
        ("**Today** it is 18°C. ☀️", "Today it is 18 degrees Celsius."),
        ("The dollar is 49.39 TL", "The dollar is 49.39 lira"),
        ("It is 3:30 now", "It is 3:30 now"),
    ],
)
def test_english_speech_text_spells_out_symbols_and_keeps_digits(text: str, expected: str) -> None:
    assert spoken_text.normalize(text, AssistantLanguage.ENGLISH) == expected


def test_turkish_speech_text_is_unchanged_by_the_split() -> None:
    assert spoken_text.normalize("Saat 14:30", AssistantLanguage.TURKISH) == turkish_speech_normalizer.normalize(
        "Saat 14:30"
    )
    assert spoken_text.normalize("**Önemli:** %25", AssistantLanguage.TURKISH) == "Önemli: yüzde yirmi beş"
