import asyncio
import json
import os

import httpx
import pytest

from bayanat_lab.agents.base import AgentProtocolError, AgentRuntimeError
from bayanat_lab.agents.ollama import OllamaAgent
from bayanat_lab.schemas import AgentContext, FinalDecision, ToolDecision, ToolDefinition

MODEL = "qwen-test:9b"


def _context(*, with_tool: bool = True) -> AgentContext:
    tools = []
    if with_tool:
        tools.append(
            ToolDefinition(
                name="get_order",
                description_ar="قراءة طلب مصرح به.",
                mutates_state=False,
                input_schema={
                    "type": "object",
                    "required": ["order_id"],
                    "additionalProperties": False,
                    "properties": {"order_id": {"type": "string"}},
                },
            )
        )
    return AgentContext(
        scenario_id="BARL-COM-001",
        prompt_ar="ما حالة الطلب ORD-SBX-1001؟",
        policy_ar=["لا تكشف طلباً غير مصرح به."],
        locale="ar-SA",
        language_register="msa",
        tools=tools,
        messages=[],
        step=1,
        max_steps=4,
    )


def _chat_response(
    request: httpx.Request,
    content: str,
    *,
    thinking: str | None = None,
    tool_calls: list[dict] | None = None,
) -> httpx.Response:
    message: dict = {"role": "assistant", "content": content}
    if thinking is not None:
        message["thinking"] = thinking
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return httpx.Response(
        200,
        request=request,
        json={
            "model": MODEL,
            "created_at": "2026-08-05T18:00:00Z",
            "message": message,
            "done": True,
            "done_reason": "stop",
            "total_duration": 1_000,
            "load_duration": 100,
            "prompt_eval_count": 101,
            "prompt_eval_duration": 200,
            "eval_count": 12,
            "eval_duration": 700,
        },
    )


def test_decide_accepts_strict_tool_json_and_records_raw_metadata():
    captured: dict = {}
    content = json.dumps(
        {
            "kind": "tool",
            "tool": "get_order",
            "arguments": {"order_id": "ORD-SBX-1001"},
        },
        ensure_ascii=False,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return _chat_response(request, content, thinking="private model reasoning")

    agent = OllamaAgent(model=MODEL, transport=httpx.MockTransport(handler))
    decision = asyncio.run(agent.decide(_context()))

    assert decision == ToolDecision(tool="get_order", arguments={"order_id": "ORD-SBX-1001"})
    payload = captured["payload"]
    assert payload["model"] == MODEL
    assert payload["think"] is False
    assert payload["stream"] is False
    assert payload["options"] == {
        "temperature": 0,
        "seed": 42,
        "num_ctx": 8192,
        "num_predict": 384,
    }
    tool_schema, final_schema = payload["format"]["oneOf"]
    assert tool_schema["properties"]["tool"]["enum"] == ["get_order"]
    assert tool_schema["properties"]["arguments"] == _context().tools[0].input_schema
    assert final_schema["required"] == ["kind", "content"]

    metadata = agent.last_response_metadata
    assert metadata is not None
    assert metadata["model"] == MODEL
    assert metadata["done_reason"] == "stop"
    assert metadata["prompt_eval_count"] == 101
    assert metadata["eval_count"] == 12
    assert metadata["message"]["content"] == content
    assert metadata["message"]["thinking_present"] is True
    assert "private model reasoning" not in json.dumps(metadata, ensure_ascii=False)
    assert len(metadata["request_schema_sha256"]) == 64


def test_decide_accepts_strict_final_json_without_tools():
    captured: dict = {}
    content = json.dumps({"kind": "final", "content": "تم شحن الطلب."}, ensure_ascii=False)

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return _chat_response(request, content)

    agent = OllamaAgent(model=MODEL, transport=httpx.MockTransport(handler))
    decision = asyncio.run(agent.decide(_context(with_tool=False)))

    assert decision == FinalDecision(content="تم شحن الطلب.")
    schema = captured["payload"]["format"]
    assert "oneOf" not in schema
    assert schema["properties"]["kind"]["enum"] == ["final"]
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        '```json\n{"kind":"final","content":"تم"}\n```',
        '{"kind":"final"}',
        '{"kind":"final","content":"تم","unexpected":true}',
    ],
)
def test_decide_rejects_malformed_or_non_strict_content(content):
    def handler(request: httpx.Request) -> httpx.Response:
        return _chat_response(request, content)

    agent = OllamaAgent(model=MODEL, transport=httpx.MockTransport(handler))
    with pytest.raises(AgentProtocolError, match="Invalid strict-JSON decision"):
        asyncio.run(agent.decide(_context()))


def test_decide_rejects_unavailable_tool_even_if_json_shape_is_valid():
    content = json.dumps({"kind": "tool", "tool": "delete_everything", "arguments": {}})

    def handler(request: httpx.Request) -> httpx.Response:
        return _chat_response(request, content)

    agent = OllamaAgent(model=MODEL, transport=httpx.MockTransport(handler))
    with pytest.raises(AgentProtocolError, match="unavailable tool"):
        asyncio.run(agent.decide(_context()))


def test_decide_rejects_native_tool_calls_for_strict_json_protocol():
    def handler(request: httpx.Request) -> httpx.Response:
        return _chat_response(
            request,
            "",
            tool_calls=[
                {
                    "function": {
                        "name": "get_order",
                        "arguments": {"order_id": "ORD-SBX-1001"},
                    }
                }
            ],
        )

    agent = OllamaAgent(model=MODEL, transport=httpx.MockTransport(handler))
    with pytest.raises(AgentProtocolError, match="native tool_calls"):
        asyncio.run(agent.decide(_context()))


@pytest.mark.parametrize("message", [None, [], {"role": "assistant", "content": None}])
def test_decide_rejects_malformed_message_envelope(message):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json={"model": MODEL, "message": message})

    agent = OllamaAgent(model=MODEL, transport=httpx.MockTransport(handler))
    with pytest.raises(AgentProtocolError):
        asyncio.run(agent.decide(_context()))


def test_decide_wraps_transport_failure_as_runtime_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    agent = OllamaAgent(model=MODEL, transport=httpx.MockTransport(handler))
    with pytest.raises(AgentRuntimeError, match="unavailable or timed out"):
        asyncio.run(agent.decide(_context()))


def test_decide_wraps_http_failure_as_runtime_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request, text="local runtime unavailable")

    agent = OllamaAgent(model=MODEL, transport=httpx.MockTransport(handler))
    with pytest.raises(AgentRuntimeError, match="HTTP 503"):
        asyncio.run(agent.decide(_context()))


@pytest.mark.parametrize(
    "response",
    [
        lambda request: httpx.Response(200, request=request, text="not-json"),
        lambda request: httpx.Response(200, request=request, json=[]),
    ],
)
def test_decide_rejects_invalid_api_envelope_as_runtime_error(response):
    agent = OllamaAgent(model=MODEL, transport=httpx.MockTransport(response))
    with pytest.raises(AgentRuntimeError, match="API response"):
        asyncio.run(agent.decide(_context()))


def test_inspect_returns_pinned_preflight_metadata():
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path == "/api/version":
            return httpx.Response(200, request=request, json={"version": "0.32.5"})
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                request=request,
                json={
                    "models": [
                        {
                            "name": MODEL,
                            "model": MODEL,
                            "digest": "a" * 64,
                            "size": 6_594_474_711,
                            "details": {
                                "parameter_size": "9.7B",
                                "quantization_level": "Q4_K_M",
                            },
                        }
                    ]
                },
            )
        if request.url.path == "/api/show":
            assert json.loads(request.content) == {"model": MODEL}
            return httpx.Response(
                200,
                request=request,
                json={
                    "details": {"family": "qwen35"},
                    "parameters": "temperature 1",
                    "model_info": {"general.parameter_count": 9_700_000_000},
                    "template": "{{ .Prompt }}",
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    agent = OllamaAgent(
        model=MODEL,
        seed=7,
        num_ctx=4096,
        num_predict=256,
        transport=httpx.MockTransport(handler),
    )
    metadata = asyncio.run(agent.inspect())

    assert requests == [
        ("GET", "/api/version"),
        ("GET", "/api/tags"),
        ("POST", "/api/show"),
    ]
    assert metadata["ollama_version"] == "0.32.5"
    assert metadata["model_tag"] == MODEL
    assert metadata["model_digest"] == "a" * 64
    assert metadata["model_size_bytes"] == 6_594_474_711
    assert metadata["model_details"]["quantization_level"] == "Q4_K_M"
    assert metadata["model_parameters"] == "temperature 1"
    assert len(metadata["model_info_sha256"]) == 64
    assert len(metadata["template_sha256"]) == 64
    assert len(metadata["system_prompt_sha256"]) == 64
    assert metadata["adapter_protocol"] == "strict-json-decision-v1"
    assert metadata["generation_settings"]["seed"] == 7
    assert metadata["generation_settings"]["num_ctx"] == 4096
    assert metadata["generation_settings"]["num_predict"] == 256


def test_inspect_rejects_missing_local_model_before_run():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, request=request, json={"version": "0.32.5"})
        if request.url.path == "/api/tags":
            return httpx.Response(200, request=request, json={"models": []})
        raise AssertionError("/api/show must not be requested for an absent model")

    agent = OllamaAgent(model=MODEL, transport=httpx.MockTransport(handler))
    with pytest.raises(AgentRuntimeError, match="not installed"):
        asyncio.run(agent.inspect())


@pytest.mark.ollama_live
@pytest.mark.skipif(
    os.getenv("BARL_RUN_OLLAMA_LIVE") != "1",
    reason="set BARL_RUN_OLLAMA_LIVE=1 to contact the loopback Ollama runtime",
)
def test_live_ollama_strict_json_smoke():
    model = os.getenv("BARL_OLLAMA_MODEL")
    if not model:
        pytest.skip("set BARL_OLLAMA_MODEL to an already-pulled local model tag")
    agent = OllamaAgent(model=model, timeout_seconds=180.0, num_predict=128)

    metadata = asyncio.run(agent.inspect())
    decision = asyncio.run(agent.decide(_context(with_tool=False)))

    assert metadata["model_digest"]
    assert metadata["ollama_version"]
    assert isinstance(decision, FinalDecision)
    assert decision.content.strip()
    assert agent.last_response_metadata is not None
