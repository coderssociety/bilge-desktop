from typing import Any

from bilge.core.language import AssistantLanguage
from bilge.core.tools import arithmetic_evaluator, english_arithmetic_parser, turkish_arithmetic_parser
from bilge.tools.base import Tool, ToolError

_TEXTS = {
    AssistantLanguage.TURKISH: {
        "description": "Aritmetik hesap yapar. Yüzde hesabını çarpma/bölmeye çevir: '125'in yüzde 18'i' → '125 * 18 / 100'.",
        "expression": "Sadece sayılar ve + - * / % ^ ( ) içeren ifade",
        "unclear": "Hesabı tam anlayamadım, sayılarla tekrar söyler misin?",
        "failed": "'{expression}' hesaplanamadı.",
        "result": "Sonuç {value}.",
    },
    AssistantLanguage.ENGLISH: {
        "description": "Does arithmetic. Turn percentages into multiplication/division: '18 percent of 125' → '125 * 18 / 100'.",
        "expression": "An expression with only numbers and + - * / % ^ ( )",
        "unclear": "I didn't quite get the calculation; could you say it again with the numbers?",
        "failed": "Couldn't calculate '{expression}'.",
        "result": "The result is {value}.",
    },
}


def calculator(language: AssistantLanguage) -> Tool:
    texts = _TEXTS[language]
    parser = english_arithmetic_parser if language is AssistantLanguage.ENGLISH else turkish_arithmetic_parser

    def refine(arguments: dict[str, Any], command: str) -> dict[str, Any]:
        # Common phrasings are parsed exactly; a model-written expression is only trusted when every number
        # in it was actually said (a local model once computed "125 * 18 / 100" for a bare "Evet").
        expression = str(arguments.get("expression") or "")
        parsed = parser.expression(command)
        if parsed:
            return {"expression": parsed}
        return {"expression": expression if parser.is_grounded(expression, command) else ""}

    def run(arguments: dict[str, Any]) -> str:
        expression = arguments.get("expression") or ""
        if not expression:
            raise ToolError(texts["unclear"])
        try:
            value = arithmetic_evaluator.evaluate(expression)
        except arithmetic_evaluator.EvaluationError as error:
            raise ToolError(texts["failed"].format(expression=expression)) from error
        return texts["result"].format(value=arithmetic_evaluator.display(value, language))

    return Tool(
        "calculate",
        texts["description"],
        run=run,
        parameters={
            "type": "object",
            "properties": {"expression": {"type": "string", "description": texts["expression"]}},
            "required": ["expression"],
        },
        refine=refine,
    )
