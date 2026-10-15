from bilge.core.evaluation.word_error_rate import WordErrorRate


def test_identical_text_has_zero_errors_after_normalization() -> None:
    result = WordErrorRate.compute(reference="Safari'yi aç.", hypothesis="safariyi aç")
    assert result.errors == 0
    assert result.rate == 0


def test_counts_substitutions_insertions_and_deletions() -> None:
    result = WordErrorRate.compute(reference="sesi biraz kıs lütfen", hypothesis="sesi kes lütfen hemen")
    # biraz deleted, kıs→kes substituted, hemen inserted
    assert result.errors == 3
    assert result.reference_word_count == 4
    assert result.rate == 0.75


def test_digits_and_spelled_numbers_compare_equal() -> None:
    result = WordErrorRate.compute(reference="saat on dört otuzda uyandır", hypothesis="Saat 14:30'da uyandır.")
    assert result.errors == 0


def test_aggregates_over_a_corpus_by_total_reference_words() -> None:
    results = [
        WordErrorRate.compute(reference="bir iki", hypothesis="bir"),
        WordErrorRate.compute(reference="üç dört beş altı", hypothesis="üç dört beş altı"),
    ]
    assert WordErrorRate.aggregate(results) == 1.0 / 6.0
