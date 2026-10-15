import pytest

from bilge.core.tools import arithmetic_evaluator
from bilge.core.tools.arithmetic_evaluator import EvaluationError


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1 + 2 * 3", 7.0),
        ("(1 + 2) * 3", 9.0),
        ("125 * 18 / 100", 22.5),
        ("-4 + 10", 6.0),
        ("2 ^ 10", 1024.0),
        ("3,5 * 2", 7.0),
        ("10 % 3", 1.0),
        ("((2))", 2.0),
        ("2 * -3", -6.0),
    ],
)
def test_evaluates_with_operator_precedence_and_parentheses(expression, expected):
    assert arithmetic_evaluator.evaluate(expression) == expected


@pytest.mark.parametrize(
    "expression", ["", "1 +", "(1 + 2", "1 + 2)", "FUNCTION(1, 'exit')", "abc", "1 / 0", "2 ^ 99999"]
)
def test_rejects_anything_that_is_not_plain_arithmetic(expression):
    with pytest.raises(EvaluationError):
        arithmetic_evaluator.evaluate(expression)


def test_renders_results_for_turkish_speech():
    assert arithmetic_evaluator.display(22.5) == "22,5"
    assert arithmetic_evaluator.display(1024) == "1024"
    assert arithmetic_evaluator.display(1.0 / 3.0) == "0,3333"
