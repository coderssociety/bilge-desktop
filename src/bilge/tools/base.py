"""What every assistant tool declares: its schema for the model, how risky it is, and how to run it."""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from bilge.llm.messages import ToolSpec


class Risk(Enum):
    SAFE = "safe"
    # Runs only after a clear spoken yes.
    CONFIRM = "confirm"
    DISABLED = "disabled"


class ToolError(Exception):
    """The tool could not do the job; the message is spoken to the user."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    run: Callable[[dict[str, Any]], str]
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    risk: Risk = Risk.SAFE
    # The question asked before a CONFIRM tool runs, built from the arguments. Returning None means this
    # particular call changes nothing worth asking about (nothing to delete, a fact the user just dictated).
    confirmation: Callable[[dict[str, Any]], str | None] | None = None
    # The result holds text someone else may have written (a web page, an e-mail, the clipboard). A function decides
    # per call, for tools where only some actions read such text ("what's playing" does, "pause" doesn't).
    untrusted_output: bool | Callable[[dict[str, Any]], bool] = False
    # Corrects the model's arguments against what the user actually said, before anything runs.
    refine: Callable[[dict[str, Any], str], dict[str, Any]] | None = None
    # What the call will do, as a spoken question ("example.com sayfasını açıp okuyayım mı?"); used when a
    # normally safe step needs a yes because it follows text someone else wrote.
    spoken_action: Callable[[dict[str, Any]], str] | None = None

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, self.parameters)

    def reads_untrusted(self, arguments: dict[str, Any]) -> bool:
        if callable(self.untrusted_output):
            return bool(self.untrusted_output(arguments))
        return self.untrusted_output

    def question(self, arguments: dict[str, Any]) -> str | None:
        if self.confirmation:
            return self.confirmation(arguments)
        return self.generic_question(arguments)

    def generic_question(self, arguments: dict[str, Any]) -> str:
        if self.spoken_action:
            return self.spoken_action(arguments)
        return f"{self.name} {describe_arguments(arguments)}".strip()


def describe_arguments(arguments: dict[str, Any]) -> str:
    """ "text: x, when: tomorrow": short enough to read aloud in a confirmation question."""
    return ", ".join(f"{key}: {value}" for key, value in arguments.items() if value not in (None, ""))


class Registry:
    def __init__(self, tools: list[Tool] | None = None):
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.add(tool)

    def add(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def specs(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values() if t.risk is not Risk.DISABLED]

    def __len__(self) -> int:
        return len(self._tools)
