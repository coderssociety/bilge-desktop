import unicodedata

from bilge.core.language import AssistantLanguage
from bilge.voice.supertonic import chunks, preprocess


def test_wraps_in_a_language_tag_and_ends_with_punctuation():
    assert (
        preprocess("Merhaba  dünya", AssistantLanguage.TURKISH)
        == "<tr>" + unicodedata.normalize("NFKD", "Merhaba dünya") + ".</tr>"
    )
    assert preprocess("Hello!", AssistantLanguage.ENGLISH) == "<en>Hello!</en>"


def test_drops_emoji_and_odd_symbols():
    assert preprocess("Tamam 👍 — oldu", AssistantLanguage.TURKISH) == "<tr>Tamam - oldu.</tr>"


def test_long_text_splits_at_sentence_ends():
    sentence = "Bu bir cümle. " * 40
    parts = chunks(sentence, max_length=100)
    assert all(len(p) <= 100 for p in parts)
    assert " ".join(parts) == sentence.strip()
