import pytest

from bilge.core.tools import phone_number


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0532 123 45 67", "+905321234567"),
        ("+90 (532) 123-45-67", "+905321234567"),
        ("532 123 4567", "+905321234567"),
        ("0090 532 123 45 67", "+905321234567"),
        ("+44 20 7946 0958", "+442079460958"),
    ],
)
def test_normalizes_turkish_and_international_formats(text, expected):
    assert phone_number.normalized(text) == expected


@pytest.mark.parametrize("text", ["ahmet@example.com", "123", "abc 0532"])
def test_rejects_non_numbers(text):
    assert phone_number.normalized(text) is None
