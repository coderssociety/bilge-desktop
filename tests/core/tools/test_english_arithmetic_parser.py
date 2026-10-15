import pytest

from bilge.core.language import AssistantLanguage
from bilge.core.tools import arithmetic_evaluator, english_arithmetic_parser


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("How much is 15 percent of 240", "240 * 15 / 100"),
        ("What's 15% of 240?", "240 * 15 / 100"),
        ("48 divided by 6", "48 / 6"),
        ("What is 125 times 18", "125 * 18"),
        ("12 multiplied by 4", "12 * 4"),
        ("45 plus 17 minus 3", "45 + 17 - 3"),
        ("half of 80", "80 / 2"),
        ("What's a third of 90?", "90 / 3"),
        ("3 squared", "3 ^ 2"),
        ("2 to the power of 10", "2 ^ 10"),
        ("What is 1,250 plus 3.5", "1250 + 3.5"),
        ("What's the weather", None),
        ("Call 3 people", None),
    ],
)
def test_common_phrasings(command, expected):
    assert english_arithmetic_parser.expression(command) == expected


def test_a_model_written_expression_must_use_numbers_that_were_said():
    assert english_arithmetic_parser.is_grounded("240 * 15 / 100", "15 percent of 240")
    assert english_arithmetic_parser.is_grounded("80 / 2", "what's half of 80")
    assert not english_arithmetic_parser.is_grounded("125 * 18 / 100", "yes")
    assert not english_arithmetic_parser.is_grounded("7 * 9", "what's 7 times 8")


def test_results_read_with_a_decimal_point_in_english():
    assert arithmetic_evaluator.display(22.5, language=AssistantLanguage.ENGLISH) == "22.5"
    assert arithmetic_evaluator.display(22.5) == "22,5"
