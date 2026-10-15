"""Shared by the desktop tools: what to say when the desktop can't do something, and small schema helpers."""

import logging
from enum import StrEnum
from typing import Any

from bilge.core.language import AssistantLanguage
from bilge.desktop.process import DesktopError, MissingProgram
from bilge.tools.base import ToolError

log = logging.getLogger(__name__)


def failure(error: DesktopError, language: AssistantLanguage, what: str | None = None) -> ToolError:
    """A missing program is named, so the user knows what to install; other details only go to the log."""
    log.info("Desktop action failed: %s", error)
    english = language is AssistantLanguage.ENGLISH
    if isinstance(error, MissingProgram):
        programs = ", ".join(error.programs)
        if english:
            return ToolError(f"This needs one of these programs, which aren't installed: {programs}.")
        return ToolError(f"Bunun için şu programlardan biri gerekiyor ama yüklü değil: {programs}.")
    if what:
        return ToolError(what)
    return ToolError("That didn't work on this computer." if english else "Bunu bu bilgisayarda yapamadım.")


def choice(values: type[StrEnum] | list[str], description: str) -> dict[str, Any]:
    options = [v.value for v in values] if isinstance(values, type) else list(values)
    return {"type": "string", "enum": options, "description": description}


def obj(required: list[str] | None = None, **properties: dict[str, Any]) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def text(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


def integer(description: str, minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "minimum": minimum, "maximum": maximum, "description": description}


def string_argument(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    return str(value).strip() if value is not None else ""


def int_argument(arguments: dict[str, Any], key: str) -> int | None:
    """Models send numbers as 7, 7.0 or "7"; anything else counts as not given."""
    value = arguments.get(key)
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
