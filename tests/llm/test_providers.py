import json

import httpx
import pytest

from bilge.llm.messages import Message, ToolCall, ToolSpec
from bilge.llm.providers import AnthropicProvider, OpenAICompatibleProvider, ProviderError, make_provider

CLOCK = ToolSpec("currentDateTime", "time", {"type": "object", "properties": {}})


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_openai_sends_tools_and_reads_tool_calls():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "type": "function",
                                    "function": {"name": "currentDateTime", "arguments": '{"x": 1}'},
                                }
                            ],
                        }
                    }
                ]
            },
        )

    provider = OpenAICompatibleProvider("https://api.example/v1", "m", "secret", client(handler))
    reply = provider.complete([Message.system("s"), Message.user("saat kaç")], [CLOCK])
    assert reply.tool_calls == (ToolCall("c1", "currentDateTime", {"x": 1}),)
    assert reply.text == ""
    assert seen["auth"] == "Bearer secret"
    assert seen["body"]["tools"][0]["function"]["name"] == "currentDateTime"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "s"}


def test_openai_sends_tool_results_back():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Saat 14:05."}}]})

    call = ToolCall("c1", "currentDateTime", {})
    messages = [
        Message.user("saat kaç"),
        Message("assistant", "", tool_calls=(call,)),
        Message.tool_result(call, "14:05"),
    ]
    reply = OpenAICompatibleProvider("http://localhost:1234/v1", "m", None, client(handler)).complete(messages)
    assert reply.text == "Saat 14:05."
    sent = seen["body"]["messages"]
    assert sent[1]["tool_calls"][0]["function"]["arguments"] == "{}"
    assert sent[2] == {"role": "tool", "tool_call_id": "c1", "content": "14:05"}


def test_malformed_tool_arguments_become_empty():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {"id": "c1", "function": {"name": "currentDateTime", "arguments": "{broken"}}
                            ]
                        }
                    }
                ]
            },
        )

    reply = OpenAICompatibleProvider("http://x/v1", "m", None, client(handler)).complete([Message.user("x")])
    assert reply.tool_calls[0].arguments == {}


def test_api_errors_carry_the_message():
    def handler(request):
        return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

    with pytest.raises(ProviderError, match="Invalid API key"):
        OpenAICompatibleProvider("http://x/v1", "m", "k", client(handler)).complete([Message.user("x")])


def test_unreachable_server_is_a_provider_error():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(ProviderError, match="Could not reach"):
        OpenAICompatibleProvider("http://x/v1", "m", None, client(handler)).complete([Message.user("x")])


def test_anthropic_moves_system_and_merges_tool_results():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["headers"] = request.headers
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "text", "text": "Bakıyorum."},
                    {"type": "tool_use", "id": "t2", "name": "currentDateTime", "input": {}},
                ]
            },
        )

    a, b = ToolCall("t0", "currentDateTime", {}), ToolCall("t1", "currentDateTime", {})
    messages = [
        Message.system("kurallar"),
        Message.user("saat"),
        Message("assistant", "", tool_calls=(a, b)),
        Message.tool_result(a, "14:05"),
        Message.tool_result(b, "14:05"),
    ]
    reply = AnthropicProvider("https://api.anthropic.com/v1", "m", "key", client(handler)).complete(messages, [CLOCK])
    assert reply.text == "Bakıyorum."
    assert reply.tool_calls == (ToolCall("t2", "currentDateTime", {}),)
    body = seen["body"]
    assert body["system"] == "kurallar"
    assert body["tools"][0]["input_schema"] == CLOCK.parameters
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
    assert [block["tool_use_id"] for block in body["messages"][2]["content"]] == ["t0", "t1"]
    assert seen["headers"]["x-api-key"] == "key"


def test_hosted_providers_need_a_key():
    with pytest.raises(ProviderError, match="API key"):
        make_provider("openai", "m")
    assert isinstance(make_provider("ollama", "m"), OpenAICompatibleProvider)
    with pytest.raises(ProviderError, match="Unknown provider"):
        make_provider("nope", "m")


def test_openai_itself_gets_the_current_parameters():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = OpenAICompatibleProvider(
        "https://api.openai.com/v1", "m", "k", client(handler), current_openai_parameters=True
    )
    provider.complete([Message.user("x")], max_tokens=50)
    assert seen["body"]["max_completion_tokens"] == 50
    assert "max_tokens" not in seen["body"] and "temperature" not in seen["body"]


def test_a_tool_call_without_a_function_is_ignored():
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"tool_calls": [{"function": None}]}}]})

    reply = OpenAICompatibleProvider("http://x/v1", "m", None, client(handler)).complete([Message.user("x")])
    assert reply.tool_calls == ()


@pytest.mark.parametrize("body", [[], {"choices": "x"}, {"choices": []}])
def test_answers_in_an_odd_shape_are_provider_errors(body):
    def handler(request):
        return httpx.Response(200, json=body)

    with pytest.raises(ProviderError):
        OpenAICompatibleProvider("http://x/v1", "m", None, client(handler)).complete([Message.user("x")])


def test_anthropic_never_sends_an_empty_turn():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})

    messages = [Message.user("a"), Message("assistant", ""), Message.user("b")]
    AnthropicProvider("https://api.anthropic.com/v1", "m", "k", client(handler)).complete(messages)
    assert [m["content"] for m in seen["body"]["messages"]] == ["a", "b"]
