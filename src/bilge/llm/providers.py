"""Chat providers: any OpenAI-compatible endpoint (hosted APIs, Ollama, LM Studio, llama.cpp) and Anthropic."""

import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from bilge.llm.messages import Message, Reply, ToolCall, ToolSpec

DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class ProviderError(Exception):
    """A provider could not answer; the message is safe to show the user."""


class ChatProvider(Protocol):
    def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        *,
        temperature: float = 0.3,
        max_tokens: int = 800,
    ) -> Reply: ...

    def list_models(self) -> list[str]: ...


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    base_url: str
    needs_key: bool
    kind: str = "openai"


PRESETS: dict[str, Preset] = {
    p.id: p
    for p in [
        Preset("openai", "OpenAI", "https://api.openai.com/v1", True),
        Preset("anthropic", "Anthropic", "https://api.anthropic.com/v1", True, kind="anthropic"),
        Preset("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", True),
        Preset("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", True),
        Preset("groq", "Groq", "https://api.groq.com/openai/v1", True),
        Preset("deepseek", "DeepSeek", "https://api.deepseek.com/v1", True),
        Preset("ollama", "Ollama", "http://localhost:11434/v1", False),
        Preset("lmstudio", "LM Studio", "http://localhost:1234/v1", False),
        Preset("llamacpp", "llama.cpp", "http://localhost:8080/v1", False),
    ]
}


def make_provider(preset_id: str, model: str, api_key: str | None = None, base_url: str | None = None) -> ChatProvider:
    preset = PRESETS.get(preset_id)
    if preset is None:
        raise ProviderError(f"Unknown provider: {preset_id}")
    if preset.needs_key and not api_key:
        raise ProviderError(f"{preset.name} needs an API key.")
    url = (base_url or preset.base_url).rstrip("/")
    if preset.kind == "anthropic":
        return AnthropicProvider(url, model, api_key or "")
    return OpenAICompatibleProvider(url, model, api_key, current_openai_parameters=preset.id == "openai")


def _post(client: httpx.Client, url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    try:
        response = client.post(url, headers=headers, json=body)
    except httpx.HTTPError as error:
        raise ProviderError(f"Could not reach {url}: {error}") from error
    if response.status_code >= 400:
        raise ProviderError(f"{url} answered {response.status_code}: {_error_text(response)}")
    try:
        return response.json()
    except ValueError as error:
        raise ProviderError(f"{url} did not answer with JSON") from error


def _error_text(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:300]
    error = data.get("error", data) if isinstance(data, dict) else data
    if isinstance(error, dict):
        return str(error.get("message", error))[:300]
    return str(error)[:300]


def _arguments(raw: Any) -> dict[str, Any]:
    """Tool arguments arrive as a JSON string from OpenAI-style APIs and as an object from Anthropic."""
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


class OpenAICompatibleProvider:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None,
        client: httpx.Client | None = None,
        current_openai_parameters: bool = False,
    ):
        self.base_url = base_url
        self.model = model
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = client or httpx.Client(timeout=DEFAULT_TIMEOUT)
        # OpenAI's reasoning models refuse max_tokens and any temperature but the default; the servers
        # copying the older API (local ones, OpenRouter, Groq) still expect max_tokens.
        self._current_openai_parameters = current_openai_parameters

    def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        *,
        temperature: float = 0.3,
        max_tokens: int = 800,
    ) -> Reply:
        body: dict[str, Any] = {"model": self.model, "messages": [self._message(m) for m in messages]}
        if self._current_openai_parameters:
            body["max_completion_tokens"] = max_tokens
        else:
            body["temperature"] = temperature
            body["max_tokens"] = max_tokens
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
                }
                for t in tools
            ]
        data = _post(self._client, f"{self.base_url}/chat/completions", self._headers, body)
        try:
            message = data["choices"][0]["message"]
            calls = []
            for i, c in enumerate(message.get("tool_calls") or []):
                function = c.get("function") or {}
                if isinstance(function, dict) and isinstance(function.get("name"), str):
                    calls.append(
                        ToolCall(
                            str(c.get("id") or f"call_{i}"), function["name"], _arguments(function.get("arguments"))
                        )
                    )
            content = message.get("content")
            return Reply(text=content.strip() if isinstance(content, str) else "", tool_calls=tuple(calls))
        except (KeyError, IndexError, TypeError, AttributeError) as error:
            raise ProviderError("The model sent an answer in an unexpected shape") from error

    def list_models(self) -> list[str]:
        try:
            response = self._client.get(f"{self.base_url}/models", headers=self._headers)
            response.raise_for_status()
            return sorted(m["id"] for m in response.json().get("data", []) if "id" in m)
        except (httpx.HTTPError, ValueError, KeyError) as error:
            raise ProviderError(f"Could not list models at {self.base_url}: {error}") from error

    @staticmethod
    def _message(message: Message) -> dict[str, Any]:
        if message.role == "tool":
            return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
        out: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_calls:
            out["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                for c in message.tool_calls
            ]
        return out


class AnthropicProvider:
    API_VERSION = "2023-06-01"

    def __init__(self, base_url: str, model: str, api_key: str, client: httpx.Client | None = None):
        self.base_url = base_url
        self.model = model
        self._headers = {"x-api-key": api_key, "anthropic-version": self.API_VERSION}
        self._client = client or httpx.Client(timeout=DEFAULT_TIMEOUT)

    def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        *,
        temperature: float = 0.3,
        max_tokens: int = 800,
    ) -> Reply:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": self._messages([m for m in messages if m.role != "system"]),
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools
            ]
        data = _post(self._client, f"{self.base_url}/messages", self._headers, body)
        try:
            blocks = [b for b in data.get("content") or [] if isinstance(b, dict)]
            text = "".join(str(b.get("text", "")) for b in blocks if b.get("type") == "text").strip()
            calls = tuple(
                ToolCall(str(b["id"]), str(b["name"]), _arguments(b.get("input")))
                for b in blocks
                if b.get("type") == "tool_use"
            )
        except (KeyError, TypeError, AttributeError) as error:
            raise ProviderError("The model sent an answer in an unexpected shape") from error
        return Reply(text=text, tool_calls=calls)

    def list_models(self) -> list[str]:
        try:
            response = self._client.get(f"{self.base_url}/models", headers=self._headers)
            response.raise_for_status()
            return sorted(m["id"] for m in response.json().get("data", []) if "id" in m)
        except (httpx.HTTPError, ValueError, KeyError) as error:
            raise ProviderError(f"Could not list Anthropic models: {error}") from error

    @staticmethod
    def _messages(messages: list[Message]) -> list[dict[str, Any]]:
        """Anthropic wants tool results inside a user turn and consecutive results merged into one turn."""
        out: list[dict[str, Any]] = []
        for message in messages:
            if message.role == "tool":
                block = {"type": "tool_result", "tool_use_id": message.tool_call_id, "content": message.content}
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
            elif message.role == "assistant" and message.tool_calls:
                content: list[dict[str, Any]] = [{"type": "text", "text": message.content}] if message.content else []
                content += [
                    {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments} for c in message.tool_calls
                ]
                out.append({"role": "assistant", "content": content})
            elif message.content.strip():
                out.append({"role": message.role, "content": message.content})
        return out
