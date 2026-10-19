"""The LLM setting (roadmap R42): which LLM answers, with the user's API key."""

import json
import logging
import os
import threading
from collections.abc import Iterator
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from imageskin import llm_choice as lc
from imageskin.app import create_app
from imageskin.chat import LlmClient, LlmSettings, Message
from imageskin.claude import DEFAULT_MODEL as CLAUDE_MODEL
from imageskin.claude import ClaudeClient
from imageskin.review import Review
from imageskin.uploads import PhotoResult

KEY = "sk-test-secret"


def test_local_llama_cpp_is_the_default(tmp_path: Path) -> None:
    choice = lc.load_choice(tmp_path)
    assert choice == lc.LlmChoice("local")
    assert lc.described(choice)["provider"] == "local"
    assert [p["id"] for p in lc.described(choice)["providers"]] == [
        "local",
        "claude",
        "openai",
        "grok",
        "openrouter",
    ]


def test_a_provider_is_saved_with_its_key_which_is_never_shown_or_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        choice = lc.save_choice(tmp_path, "grok", f"  {KEY} ")
    assert choice.provider == "grok" and choice.keys == {"grok": KEY}
    assert lc.load_choice(tmp_path) == choice
    shown = lc.described(choice)
    grok = next(p for p in shown["providers"] if p["id"] == "grok")
    assert grok["has_key"] is True and grok["default_model"] == "grok-4"
    assert KEY not in json.dumps(shown)
    assert KEY not in caplog.text and KEY not in repr(choice)
    assert "LLM chosen" in caplog.messages
    if os.name == "posix":  # Windows has no such modes
        assert (tmp_path / lc.FILENAME).stat().st_mode & 0o077 == 0


def test_each_provider_keeps_its_key_and_model(tmp_path: Path) -> None:
    lc.save_choice(tmp_path, "claude", KEY, "claude-sonnet-5-5")
    lc.save_choice(tmp_path, "openai", "sk-openai")
    back = lc.save_choice(tmp_path, "local")
    assert back.provider == "local" and set(back.keys) == {"claude", "openai"}
    again = lc.save_choice(tmp_path, "claude")  # no key needed a second time
    assert again.keys["claude"] == KEY and again.model("claude") == "claude-sonnet-5-5"
    assert lc.save_choice(tmp_path, "claude", model=" ").model("claude") == CLAUDE_MODEL
    assert lc.save_choice(tmp_path, "openai", "sk-new").keys["openai"] == "sk-new"


@pytest.mark.parametrize(
    ("provider", "key", "model", "said"),
    [
        ("gemini", None, None, "no LLM called gemini"),
        ("openrouter", None, None, "Enter your OpenRouter API key"),
        ("openrouter", "   ", None, "Enter your OpenRouter API key"),
        ("openai", "sk 1", None, "doesn't look like a OpenAI API key"),
        ("openai", "k" * 501, None, "doesn't look like"),
        ("openai", "sk-1", "m" * 201, "too long"),
    ],
)
def test_a_choice_that_cant_be_used_is_refused(
    tmp_path: Path, provider: str, key: str | None, model: str | None, said: str
) -> None:
    with pytest.raises(ValueError, match=said):
        lc.save_choice(tmp_path, provider, key, model)
    assert not (tmp_path / lc.FILENAME).exists()


@pytest.mark.parametrize(
    "text",
    ["{", '{"provider": "gemini", "keys": {}, "models": {}}', '{"provider": "grok", "keys": {}}'],
)
def test_a_saved_choice_that_cant_be_used_is_local(
    tmp_path: Path, text: str, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / lc.FILENAME).write_text(text)
    assert lc.load_choice(tmp_path) == lc.LlmChoice()
    assert "Could not read the LLM choice" in caplog.messages


BASE = LlmSettings(url="http://127.0.0.1:8080/v1", model="qwen", context_tokens=8192)


@pytest.mark.parametrize(
    ("provider", "url", "model"),
    [
        ("claude", BASE.url, CLAUDE_MODEL),  # Claude's SDK knows its own address
        ("openai", "https://api.openai.com/v1", "gpt-4.1-mini"),
        ("grok", "https://api.x.ai/v1", "grok-4"),
        ("openrouter", "https://openrouter.ai/api/v1", "openrouter/auto"),
    ],
)
def test_each_provider_is_asked_at_its_own_address(provider: str, url: str, model: str) -> None:
    settings = lc.settings_for(BASE, lc.LlmChoice(provider, {provider: KEY}))
    assert (settings.provider, settings.url, settings.model) == (provider, url, model)
    assert settings.api_key == KEY and settings.context_tokens == 8192
    local = lc.settings_for(BASE, lc.LlmChoice("local", {provider: KEY}))
    assert local == BASE and local.api_key == ""  # never sent to llama-server


def test_the_client_suits_the_provider() -> None:
    assert isinstance(lc.llm_client(LlmSettings(provider="claude", api_key=KEY)), ClaudeClient)
    for provider in ("local", "openai", "grok", "openrouter"):
        assert isinstance(lc.llm_client(LlmSettings(provider=provider, api_key=KEY)), LlmClient)


class Recorder:
    """Stands in for a client, saying which LLM it is."""

    def __init__(self, settings: LlmSettings) -> None:
        self.name = settings.provider
        self.calls: list[str] = []

    def count(self, text: str) -> int:
        return len(text)

    def context_tokens(self) -> int:
        return 1234

    def warm_up(self) -> None:
        self.calls.append("warm_up")

    def ask(self, messages: list[Message], max_tokens: int = 300, schema: Any = None) -> str:
        return f"{self.name} {max_tokens} {schema}"

    def stream(self, messages: list[Message]) -> Iterator[str]:
        yield self.name


def test_switching_changes_who_answers_from_the_next_request(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with patch.object(lc, "llm_client", Recorder):
        switch = lc.SwitchableLlm(BASE, lc.LlmChoice())
        assert switch.local and switch.ask([]) == "local 300 None"
        with caplog.at_level(logging.INFO):
            switch.use(lc.LlmChoice("openrouter", {"openrouter": KEY}))
    assert not switch.local
    assert switch.ask([], 50, {"type": "object"}) == "openrouter 50 {'type': 'object'}"
    assert list(switch.stream([])) == ["openrouter"]
    assert switch.count("abc") == 3 and switch.context_tokens() == 1234
    switch.warm_up()
    assert "Chat LLM changed" in caplog.messages and KEY not in caplog.text


# The app, with stand-ins for llama-server and the providers


class FakeApi(BaseHTTPRequestHandler):
    """An OpenAI-compatible API: says which model was asked for and with which key."""

    asked: list[tuple[str, str | None]] = []  # model and Authorization header of each prompt

    def do_GET(self) -> None:  # noqa: N802 (the name http.server calls)
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.endswith("/tokenize"):
            self.send_response(404)
            self.end_headers()
            return
        key = self.headers.get("Authorization")
        text = f"Answered by {body['model']}."
        self.send_response(200)
        if body.get("stream"):
            FakeApi.asked.append((body["model"], key))
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            piece = {"choices": [{"delta": {"content": text}, "finish_reason": "stop"}]}
            self.wfile.write(f"data: {json.dumps(piece)}\n\ndata: [DONE]\n\n".encode())
            return
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"choices": [{"message": {"content": text}}]}).encode())

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def api() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), FakeApi)
    FakeApi.asked = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()
    server.server_close()


class FakeClaude(Recorder):
    def context_tokens(self) -> int:
        return 4096

    def stream(self, messages: list[Message]) -> Iterator[str]:
        yield "Answered by Claude."


@pytest.fixture
def app(tmp_path: Path, api: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for provider in ("openai", "grok", "openrouter"):
        monkeypatch.setitem(lc.PROVIDERS, provider, replace(lc.PROVIDERS[provider], url=api))
    monkeypatch.setattr(lc, "ClaudeClient", FakeClaude)
    client = TestClient(
        create_app(
            tmp_path,
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=lambda photo, text, output: None,
            llm=LlmSettings(url=api, model="local"),
        )
    )
    client.post("/api/consent", json={"agreed": True})
    return client


def ask(app: TestClient) -> str:
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        answer = app.post("/api/chat", json={"prompt": "What is two plus two?"})
    assert answer.status_code == 200, answer.text
    content: str = answer.json()["content"]
    return content


def test_the_same_question_is_answered_by_each_llm(
    app: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    assert app.get("/api/llm").json()["provider"] == "local"
    assert ask(app) == "Answered by local."
    said = []
    for provider, key in (
        ("claude", "sk-ant"),
        ("openai", "sk-oa"),
        ("grok", "xai-k3y"),
        ("openrouter", "sk-or-k3y"),
    ):
        chosen = app.put("/api/llm", json={"provider": provider, "api_key": key})
        assert chosen.status_code == 200 and key not in chosen.text
        assert chosen.json()["provider"] == provider
        said.append(ask(app))
    assert said == [
        "Answered by Claude.",
        "Answered by gpt-4.1-mini.",
        "Answered by grok-4.",
        "Answered by openrouter/auto.",
    ]
    assert FakeApi.asked == [
        ("local", None),  # llama-server is never sent a key
        ("gpt-4.1-mini", "Bearer sk-oa"),
        ("grok-4", "Bearer xai-k3y"),
        ("openrouter/auto", "Bearer sk-or-k3y"),
    ]
    assert "LLM setting changed" in caplog.messages
    for key in ("sk-ant", "sk-oa", "xai-k3y", "sk-or-k3y"):
        assert key not in caplog.text
    # Back to the local model, then to Grok with another model: the key is kept.
    assert app.put("/api/llm", json={"provider": "local"}).status_code == 200
    assert ask(app) == "Answered by local."
    app.put("/api/llm", json={"provider": "grok", "model": "grok-4-fast"})
    assert ask(app) == "Answered by grok-4-fast."
    shown = app.get("/api/llm").json()
    grok = next(p for p in shown["providers"] if p["id"] == "grok")
    assert grok == {
        "id": "grok",
        "label": "Grok",
        "keys_at": "console.x.ai",
        "model": "grok-4-fast",
        "default_model": "grok-4",
        "has_key": True,
    }


def test_a_provider_without_a_key_is_refused(app: TestClient) -> None:
    refused = app.put("/api/llm", json={"provider": "claude"})
    assert refused.status_code == 400 and refused.json()["detail"] == "Enter your Claude API key."
    assert app.get("/api/llm").json()["provider"] == "local"
