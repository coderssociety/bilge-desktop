import pytest

from bilge.core.tools import turkish_arithmetic_parser


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("125'in %18'i kaç eder", "125 * 18 / 100"),
        ("125'in yüzde 18'i ne kadar", "125 * 18 / 100"),
        ("1200'ün yüzde 20'si", "1200 * 20 / 100"),
        ("120'nin yarısı kaç", "120 / 2"),
        ("320'nin çeyreği", "320 / 4"),
        ("90'ın üçte biri", "90 / 3"),
        ("865 × 254", "865 * 254"),
        ("12 çarpı 15", "12 * 15"),
        ("600 bölü 4 kaç eder", "600 / 4"),
        ("45 artı 17 eksi 3", "45 + 17 - 3"),
        ("2'nin 10. kuvveti", "2 ^ 10"),
        ("3,5 kere 2 hesapla", "3,5 * 2"),
    ],
)
def test_turns_common_spoken_arithmetic_into_an_expression(command, expected):
    assert turkish_arithmetic_parser.expression(command) == expected


@pytest.mark.parametrize("command", ["Evet", "%20'nin yarısı kaç", "Safari'yi aç", "kaç tane alarm var", ""])
def test_returns_none_for_text_that_is_not_plain_arithmetic(command):
    assert turkish_arithmetic_parser.expression(command) is None


@pytest.mark.parametrize(
    ("expression", "command", "grounded"),
    [
        ("125 * 18 / 100", "125'in %18'i", True),
        ("120 / 2", "120'nin yarısı", True),
        ("125 * 18 / 100", "Evet", False),
        ("20 * 5 / 100", "%20'nin yarısı kaç", False),
        ("600 / 4", "600 bölü 4", True),
    ],
)
def test_an_expression_is_grounded_only_if_its_numbers_were_said(expression, command, grounded):
    assert turkish_arithmetic_parser.is_grounded(expression, command) == grounded
