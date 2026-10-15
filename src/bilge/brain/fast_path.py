"""Common Turkish commands recognized without the language model ("saat kaç", "125'in yüzde 18'i"), so they are
answered at once and cost nothing. The call still goes through the agent's checks and the action log."""

from bilge.core.conversation import quick_intent_parser
from bilge.core.conversation.quick_intent_parser import Calculate, DateTime
from bilge.core.language import AssistantLanguage
from bilge.llm.messages import ToolCall


def call_for(command: str, language: AssistantLanguage) -> ToolCall | None:
    """`command` is already resolved (digits, times of day). English commands always go to the model."""
    if language is not AssistantLanguage.TURKISH:
        return None
    intent = quick_intent_parser.parse(command)
    if isinstance(intent, DateTime):
        return ToolCall("fast-path", "currentDateTime", {})
    if isinstance(intent, Calculate):
        return ToolCall("fast-path", "calculate", {"expression": intent.expression})
    return None
