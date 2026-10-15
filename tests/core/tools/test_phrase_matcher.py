import pytest

from bilge.core.tools.phrase_matcher import best_match

REMINDERS = ["Süt al", "Faturayı öde", "Annemi ara", "Alarm kur"]


@pytest.mark.parametrize(
    ("query", "expected"),
    [("süt almayı", "Süt al"), ("faturayı ödemeyi", "Faturayı öde"), ("annemi aramayı", "Annemi ara")],
)
def test_finds_titles_from_suffixed_spoken_forms(query: str, expected: str) -> None:
    assert best_match(query, REMINDERS) == expected


def test_a_first_name_finds_the_full_contact_name() -> None:
    assert best_match("Ahmet", ["Ayşe Demir", "Ahmet Yılmaz"]) == "Ahmet Yılmaz"
    assert best_match("Ahmet'in", ["Ayşe Demir", "Ahmet Yılmaz"]) == "Ahmet Yılmaz"


def test_prefers_the_title_covering_more_of_the_phrase() -> None:
    assert best_match("yaz şarkıları", ["Yaz", "Yaz Şarkıları", "Kış Şarkıları"]) == "Yaz Şarkıları"


@pytest.mark.parametrize("query", ["ekmek", "", "ve"])
def test_returns_none_when_nothing_is_close(query: str) -> None:
    assert best_match(query, REMINDERS) is None


@pytest.mark.parametrize(
    ("query", "expected"),
    [("süt almayı tamamladım işaretle", "Süt al"), ("faturayı ödedim listeden düş", "Faturayı öde")],
)
def test_a_whole_spoken_sentence_still_finds_the_reminder(query: str, expected: str) -> None:
    assert best_match(query, REMINDERS) == expected
