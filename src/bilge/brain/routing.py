"""Commands chosen by rules rather than by the model, for requests where a guess would be wrong (cell names, starting
dictation), and the hands-free modes that keep the conversation open (dictation, spreadsheet editing)."""

from collections.abc import Callable
from dataclasses import dataclass

from bilge.llm.messages import ToolCall

# Returns the call for a command the rule owns, or None.
Rule = Callable[[str], ToolCall | None]


def _never(_: str) -> bool:
    return False


@dataclass(frozen=True)
class Mode:
    is_active: Callable[[], bool]
    # How long the conversation stays open for the next input, in seconds.
    window: Callable[[], float]
    # Which input is taken without the wake word; talk in the room that isn't for the mode is ignored.
    accepts: Callable[[str], bool]
    end: Callable[[], None]
    # Takes the input itself (dictation types it) and returns what to say; None lets it go through the usual
    # handling (the spreadsheet rules, then the model).
    takes: Callable[[str], str] | None = None
    # Input it handles even when said with the wake word ("Bilge, dikteyi bitir").
    owns: Callable[[str], bool] = _never
    # The only tools the model may use for input heard without the wake word; None for all.
    tools: frozenset[str] | None = None


def rule(name: str, claims: Callable[[str], bool], arguments: Callable[[str], dict] | None = None) -> Rule:
    def route(command: str) -> ToolCall | None:
        if not claims(command):
            return None
        return ToolCall("rule", name, arguments(command) if arguments else {})

    return route
