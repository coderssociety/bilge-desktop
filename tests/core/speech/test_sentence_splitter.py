from bilge.core.speech.sentence_splitter import SentenceAccumulator, split


def test_splits_on_terminal_punctuation() -> None:
    assert split("Merhaba! Nasılsın? Bugün hava güzel.") == ["Merhaba!", "Nasılsın?", "Bugün hava güzel."]


def test_does_not_split_inside_decimals_times_or_common_abbreviations() -> None:
    assert split("Saat 14.30'da Dr. Ayşe ile görüşme var. Fiyat 3.5 lira.") == [
        "Saat 14.30'da Dr. Ayşe ile görüşme var.",
        "Fiyat 3.5 lira.",
    ]


def test_breaks_overly_long_sentences_at_commas() -> None:
    long = (
        "Bugün önce markete gideceğiz, sonra eczaneye uğrayıp ilaçları alacağız, "
        "ardından eve dönüp yemeği hazırlayacağız ve akşam da misafirleri ağırlayacağız."
    )
    parts = split(long, max_length=80)
    assert len(parts) > 1
    assert all(len(part) <= 80 for part in parts)
    assert " ".join(parts) == long


def test_ignores_blank_input() -> None:
    assert split("   \n ") == []


def test_emits_sentences_as_streamed_fragments_complete_them() -> None:
    accumulator = SentenceAccumulator()
    assert accumulator.append("Tamam, Safari") == []
    assert accumulator.append("'yi açıyorum. Başka bir") == ["Tamam, Safari'yi açıyorum."]
    assert accumulator.append(" şey var mı?") == []
    assert accumulator.finish() == ["Başka bir şey var mı?"]


def test_waits_for_the_next_character_before_treating_a_dot_as_a_sentence_end() -> None:
    accumulator = SentenceAccumulator()
    assert accumulator.append("Saat 14.") == []
    assert accumulator.append("30 oldu. ") == ["Saat 14.30 oldu."]
    assert accumulator.finish() == []


def test_a_filler_ending_in_a_space_is_spoken_before_the_rest_of_the_reply_arrives() -> None:
    accumulator = SentenceAccumulator()
    assert accumulator.append("Bir saniye. ") == ["Bir saniye."]
