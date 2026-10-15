"""One reply of the multi-step planner: call a tool, or finish with what to tell the user.
A call may carry the closing message too, when it is the last step: if it succeeds, the plan ends
without another round trip to the model."""

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Call:
    tool: str
    arguments_json: str
    final_message: str | None = None


@dataclass(frozen=True)
class Done:
    message: str


AgentStep = Call | Done


def parse(reply: str) -> AgentStep | None:
    """Accepts the first JSON object in the reply, so stray text around it does no harm."""
    text = first_json_object(reply)
    if text is None:
        return None
    try:
        obj = json.loads(text)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    done = obj.get("done")
    done = done if isinstance(done, str) and done else None
    tool = obj.get("tool")
    if not isinstance(tool, str) or not tool:
        return Done(done) if done is not None else None
    arguments = obj.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}
    arguments_json = json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return Call(tool=tool, arguments_json=arguments_json, final_message=done)


def first_json_object(text: str) -> str | None:
    """The first balanced {...}, ignoring braces inside strings."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        character = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def compact_tool_signature(name: str, schema_json: bytes | str) -> str:
    """A one-line signature for a tool's argument schema, e.g.
    `addCalendarEvent(title: string, dayOffset?: integer 0…60)`: the full JSON schemas of 45 tools
    would take ~7K tokens of the planner's context."""
    try:
        schema = json.loads(schema_json)
    except ValueError:
        return f"{name}()"
    properties = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(properties, dict):
        return f"{name}()"
    required = set(_string_list(schema.get("required")) or [])
    order = _string_list(schema.get("x-order"))
    if order is None:
        order = sorted(properties)
    arguments = []
    for key in order:
        prop = properties.get(key)
        if not isinstance(prop, dict):
            continue
        description = prop.get("description")
        note = f' "{description}"' if isinstance(description, str) else ""
        optional = "" if key in required else "?"
        arguments.append(f"{key}{optional}: {_type_of(prop)}{note}")
    return f"{name}({', '.join(arguments)})"


def _type_of(prop: dict[str, Any]) -> str:
    values = _string_list(prop.get("enum"))
    if values is not None:
        return "|".join(values)
    options = prop.get("anyOf")
    if isinstance(options, list) and all(isinstance(option, dict) for option in options):
        choices = [choice for option in options if (choice := _option_values(option)) is not None]
        if choices:
            return "|".join(choices)
    base = prop.get("type")
    base = base if isinstance(base, str) else "any"
    minimum, maximum = _as_int(prop.get("minimum")), _as_int(prop.get("maximum"))
    if minimum is not None and maximum is not None:
        return f"{base} {minimum}…{maximum}"
    return base


def _option_values(option: dict[str, Any]) -> str | None:
    values = _string_list(option.get("enum"))
    if values is not None:
        return "|".join(values)
    const = option.get("const")
    return const if isinstance(const, str) else None


def _string_list(value: Any) -> list[str] | None:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    return None


def _as_int(value: Any) -> int | None:
    # JSON numbers like 60.0 bridge to Int on the Swift side; booleans never count here.
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None
