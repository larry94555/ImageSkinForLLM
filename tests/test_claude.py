"""Claude as the LLM (roadmap R33), against a fake Messages API behind the real SDK."""

import json
from collections.abc import Callable
from typing import Any

import anthropic
import httpx2
import pytest

from imageskin.app import llm_client
from imageskin.chat import (
    REPLY_TOKENS,
    Conversation,
    EmptyReply,
    LlmClient,
    LlmError,
    LlmSettings,
)
from imageskin.claude import (
    DECLINED,
    DEFAULT_MODEL,
    EFFORT,
    FALLBACK_BETA,
    THINKING_ROOM,
    ClaudeClient,
    split_system,
    strict,
)

KEY = "sk-ant-test"
Handler = Callable[[httpx2.Request], httpx2.Response]


def message(
    text: str, stop_reason: str | None = "end_turn", model: str = DEFAULT_MODEL
) -> dict[str, Any]:
    content = [{"type": "text", "text": text}] if text else []
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 12, "output_tokens": 5},
    }


def sse(*pieces: str, stop_reason: str = "end_turn") -> bytes:
    """A streamed reply, as the Messages API sends it."""
    start = message("", stop_reason=None)
    events: list[tuple[str, dict[str, Any]]] = [("message_start", {"message": start})]
    events.append(
        ("content_block_start", {"index": 0, "content_block": {"type": "text", "text": ""}})
    )
    for piece in pieces:
        delta = {"type": "text_delta", "text": piece}
        events.append(("content_block_delta", {"index": 0, "delta": delta}))
    events.append(("content_block_stop", {"index": 0}))
    events.append(
        (
            "message_delta",
            {
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": 5},
            },
        )
    )
    events.append(("message_stop", {}))
    return "".join(
        f"event: {name}\ndata: {json.dumps({'type': name, **data})}\n\n" for name, data in events
    ).encode()


class FakeClaude:
    """Answers each request with the next response, and keeps what was sent."""

    def __init__(self, *responses: httpx2.Response) -> None:
        self.responses = list(responses)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self.responses.pop(0)

    def body(self, i: int = 0) -> dict[str, Any]:
        body: dict[str, Any] = json.loads(self.requests[i].content)
        return body


def client(fake: Handler, model: str = "local") -> ClaudeClient:
    sdk = anthropic.Anthropic(
        api_key=KEY,
        base_url="http://claude.test",
        max_retries=0,
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(fake)),
    )
    settings = LlmSettings(model=model, provider="claude", api_key=KEY, context_tokens=32000)
    return ClaudeClient(settings, sdk)


def test_claude_is_asked_with_the_users_key(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO")
    fake = FakeClaude(httpx2.Response(200, json=message(" Hello there! ")))
    messages = [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello."},
        {"role": "user", "content": "How are you?"},
    ]
    assert client(fake).ask(messages) == "Hello there!"
    request = fake.requests[0]
    assert request.headers["x-api-key"] == KEY
    assert FALLBACK_BETA in request.headers["anthropic-beta"]
    assert fake.body() == {
        "model": DEFAULT_MODEL,
        "max_tokens": REPLY_TOKENS + THINKING_ROOM,
        "system": "Be brief.",
        "messages": messages[1:],
        "output_config": {"effort": EFFORT},
        "fallbacks": "default",
    }
    answered = next(r for r in caplog.records if r.message == "Claude answered")
    assert (answered.__dict__["model"], answered.__dict__["output_tokens"]) == (DEFAULT_MODEL, 5)
    assert KEY not in caplog.text


def test_claude_can_be_asked_for_json_of_a_given_form() -> None:
    fake = FakeClaude(httpx2.Response(200, json=message('{"topics": []}')))
    schema = {
        "type": "object",
        "properties": {"topics": {"type": "array", "items": {"type": "object"}}},
    }
    answer = client(fake, "claude-haiku-5-5").ask([{"role": "user", "content": "Hi"}], 900, schema)
    assert answer == '{"topics": []}'
    body = fake.body()
    assert body["model"] == "claude-haiku-5-5"
    assert "fallbacks" not in body  # only some models take it
    assert body["output_config"]["format"] == {"type": "json_schema", "schema": strict(schema)}
    assert body["max_tokens"] == 900 + THINKING_ROOM


def test_every_object_in_the_schema_is_closed() -> None:
    schema = {
        "type": "object",
        "properties": {"a": {"type": "array", "items": {"type": "object", "properties": {}}}},
    }
    closed = strict(schema)
    assert closed["additionalProperties"] is False
    assert closed["properties"]["a"]["items"]["additionalProperties"] is False
    assert "additionalProperties" not in closed["properties"]["a"]
    assert "additionalProperties" not in schema  # the original is left as it was


def test_the_system_messages_are_lifted_out() -> None:
    system, rest = split_system(
        [
            {"role": "system", "content": "One."},
            {"role": "user", "content": "Hi"},
            {"role": "system", "content": "Two."},
        ]
    )
    assert system == "One.\n\nTwo."
    assert rest == [{"role": "user", "content": "Hi"}]


def test_without_a_system_message_none_is_sent() -> None:
    fake = FakeClaude(httpx2.Response(200, json=message("Hi.")))
    client(fake).ask([{"role": "user", "content": "Hi"}])
    assert "system" not in fake.body()


@pytest.mark.parametrize(
    ("response", "error", "words"),
    [
        (message("", stop_reason="refusal"), LlmError, DECLINED),
        (message(""), EmptyReply, "empty reply"),
        (message("   "), EmptyReply, "empty reply"),
    ],
)
def test_a_declined_or_empty_reply_is_an_error(
    response: dict[str, Any], error: type[LlmError], words: str
) -> None:
    fake = FakeClaude(httpx2.Response(200, json=response))
    with pytest.raises(error, match=words):
        client(fake).ask([{"role": "user", "content": "Hi"}])


def api_error(status: int) -> httpx2.Response:
    body = {"type": "error", "error": {"type": "some_error", "message": "it went wrong"}}
    return httpx2.Response(status, json=body)


@pytest.mark.parametrize(
    ("status", "words"),
    [
        (401, "refused the API key"),
        (403, "isn't allowed"),
        (404, "doesn't know the model"),
        (429, "too many requests"),
        (400, r"refused the prompt \(400\)"),
        (529, r"refused the prompt \(529\)"),
    ],
)
def test_failures_are_said_in_plain_words(
    status: int, words: str, caplog: pytest.LogCaptureFixture
) -> None:
    fake = FakeClaude(api_error(status))
    with pytest.raises(LlmError, match=words):
        client(fake).ask([{"role": "user", "content": "Hi"}])
    assert any(r.message == "Claude failed" and r.levelname == "ERROR" for r in caplog.records)


def test_claude_out_of_reach_is_named() -> None:
    def down(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no route", request=request)

    with pytest.raises(LlmError, match="Could not reach Claude"):
        client(down).ask([{"role": "user", "content": "Hi"}])


def streamed(body: bytes) -> httpx2.Response:
    return httpx2.Response(200, content=body, headers={"content-type": "text/event-stream"})


def test_claude_streams_the_reply(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO")
    fake = FakeClaude(streamed(sse("Hel", "lo there.")))
    pieces = list(client(fake).stream([{"role": "user", "content": "Hi"}]))
    assert pieces == ["Hello there."]  # whole, once Claude has finished (review on PR #111)
    assert fake.body()["stream"] is True
    streamed_log = next(r for r in caplog.records if r.message == "Claude streamed a reply")
    assert streamed_log.__dict__["first_words_ms"] is not None


@pytest.mark.parametrize(
    ("body", "error", "words"),
    [
        (sse("Sorry", stop_reason="refusal"), LlmError, DECLINED),
        (sse(), EmptyReply, "empty reply"),
    ],
)
def test_a_declined_or_empty_stream_is_an_error(
    body: bytes, error: type[LlmError], words: str
) -> None:
    fake = FakeClaude(streamed(body))
    with pytest.raises(error, match=words):
        list(client(fake).stream([{"role": "user", "content": "Hi"}]))


def test_a_failed_stream_is_said_in_plain_words() -> None:
    fake = FakeClaude(api_error(401))
    with pytest.raises(LlmError, match="refused the API key"):
        list(client(fake).stream([{"role": "user", "content": "Hi"}]))


def test_tokens_are_estimated_and_the_window_is_the_configs() -> None:
    fake = FakeClaude()
    claude = client(fake)
    assert claude.count("four") == 4
    assert claude.context_tokens() == 32000
    claude.warm_up()
    assert fake.requests == []


def test_the_config_picks_the_client() -> None:
    claude = llm_client(LlmSettings(provider="claude", api_key=KEY))
    assert isinstance(claude, ClaudeClient)
    assert isinstance(llm_client(LlmSettings()), LlmClient)
    assert isinstance(llm_client(LlmSettings(provider="openai", api_key="k")), LlmClient)


def test_a_reply_declined_partway_is_never_spoken_or_kept() -> None:
    """Claude may decline after writing a whole sentence; that sentence must not reach the
    clips or the conversation (review on PR #111)."""
    fake = FakeClaude(streamed(sse("I can help with that. ", "First, you", stop_reason="refusal")))
    claude = client(fake)
    conversation = Conversation(claude.ask, claude.context_tokens, stream=claude.stream)
    spoken: list[str | None] = []
    with pytest.raises(LlmError, match=DECLINED):
        conversation.send("Hi", spoken.append)
    assert [s for s in spoken if s is not None] == []
    assert conversation.turns() == []


def test_a_reply_finished_by_the_fallback_model_is_spoken_whole() -> None:
    """When one model declines partway and the fallback model carries on, the reply is the
    text of both, without the fallback marker."""
    start = message("", stop_reason=None)
    events: list[tuple[str, dict[str, Any]]] = [
        ("message_start", {"message": start}),
        ("content_block_start", {"index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "Sure. "}}),
        ("content_block_stop", {"index": 0}),
        (
            "content_block_start",
            {
                "index": 1,
                "content_block": {
                    "type": "fallback",
                    "from": {"model": DEFAULT_MODEL},
                    "to": {"model": "claude-opus-4-8"},
                },
            },
        ),
        ("content_block_stop", {"index": 1}),
        ("content_block_start", {"index": 2, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"index": 2, "delta": {"type": "text_delta", "text": "Here."}}),
        ("content_block_stop", {"index": 2}),
        (
            "message_delta",
            {
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 4},
            },
        ),
        ("message_stop", {}),
    ]
    body = "".join(
        f"event: {name}\ndata: {json.dumps({'type': name, **data})}\n\n" for name, data in events
    ).encode()
    fake = FakeClaude(streamed(body))
    assert list(client(fake).stream([{"role": "user", "content": "Hi"}])) == ["Sure. Here."]
