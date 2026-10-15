import pytest

from bilge.brain.agent import resolve
from bilge.core.language import AssistantLanguage
from bilge.tools.base import ToolError
from bilge.tools.builtin.calculator import calculator

TR = calculator(AssistantLanguage.TURKISH)
EN = calculator(AssistantLanguage.ENGLISH)


def test_parses_what_was_said_over_the_model_expression():
    command = resolve("yüz yirmi beşin yüzde on sekizi kaç eder", AssistantLanguage.TURKISH)
    assert TR.refine({"expression": "1+1"}, command) == {"expression": "125 * 18 / 100"}


def test_drops_an_expression_with_numbers_nobody_said():
    assert TR.refine({"expression": "125 * 18 / 100"}, "Evet") == {"expression": ""}


def test_keeps_a_grounded_model_expression():
    assert EN.refine({"expression": "48 / 6"}, "how much is 48 split six ways, 48 over 6") == {"expression": "48 / 6"}


def test_results_use_the_language_number_format():
    assert TR.run({"expression": "7 / 2"}) == "Sonuç 3,5."
    assert EN.run({"expression": "7 / 2"}) == "The result is 3.5."


def test_unclear_or_broken_expressions_are_tool_errors():
    with pytest.raises(ToolError, match="anlayamadım"):
        TR.run({"expression": ""})
    with pytest.raises(ToolError, match="hesaplanamadı"):
        TR.run({"expression": "1 / 0"})
