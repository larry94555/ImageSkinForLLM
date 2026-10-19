"""The LLM setting (roadmap R42): which LLM answers, with the user's API key."""

import io
import json
import logging
import os
import threading
import urllib.error
from collections.abc import Iterator
from dataclasses import replace
from email.message import Message as HttpHeaders
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from imageskin import app as app_module
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
    # Each new key is checked by listing the provider's models.
    lists = lc.ModelLists(Lister({"data": [{"id": "m"}]}), claude=lambda key: ["claude-x"])
    monkeypatch.setattr("imageskin.app.ModelLists", lambda: lists)
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
        "lists_freely": False,
    }


def test_a_provider_without_a_key_is_refused(app: TestClient) -> None:
    refused = app.put("/api/llm", json={"provider": "claude"})
    assert refused.status_code == 400 and refused.json()["detail"] == "Enter your Claude API key."
    assert app.get("/api/llm").json()["provider"] == "local"


# The models each provider offers (Larry, 2026-10-19: a fixed list goes out of date)


class Lister:
    """Stands in for the providers' list-models APIs."""

    def __init__(self, answer: Any) -> None:
        self.answer = answer
        self.asked: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str]) -> Any:
        self.asked.append((url, headers))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_openai_lists_only_the_models_that_chat(caplog: pytest.LogCaptureFixture) -> None:
    ids = ["gpt-5", "text-embedding-3-small", "tts-1", "whisper-1", "dall-e-3", "gpt-4.1-mini"]
    fetch = Lister({"object": "list", "data": [{"id": i} for i in ids] + [{"no": "id"}]})
    with caplog.at_level(logging.INFO):
        assert lc.ModelLists(fetch).models("openai", KEY) == ["gpt-4.1-mini", "gpt-5"]
    assert fetch.asked == [("https://api.openai.com/v1/models", {"Authorization": f"Bearer {KEY}"})]
    listed = next(r for r in caplog.records if r.message == "Listed the provider's models")
    assert vars(listed)["models"] == 2 and KEY not in caplog.text


def test_grok_lists_its_language_models() -> None:
    fetch = Lister({"models": [{"id": "grok-4"}, {"id": "grok-3-mini"}]})
    assert lc.ModelLists(fetch).models("grok", KEY) == ["grok-3-mini", "grok-4"]
    assert fetch.asked[0][0] == "https://api.x.ai/v1/language-models"


def test_openrouter_lists_the_models_that_write_text() -> None:
    fetch = Lister(
        {
            "data": [
                {"id": "openai/gpt-5", "architecture": {"output_modalities": ["text"]}},
                {"id": "x/image-maker", "architecture": {"output_modalities": ["image"]}},
                {"id": "meta/llama"},
            ]
        }
    )
    assert lc.ModelLists(fetch).models("openrouter", KEY) == ["meta/llama", "openai/gpt-5"]
    # The list is anyone's, so the key is checked on its own first.
    assert [url for url, _ in fetch.asked] == [
        "https://openrouter.ai/api/v1/key",
        "https://openrouter.ai/api/v1/models",
    ]
    assert fetch.asked[0][1] == {"Authorization": f"Bearer {KEY}"}


def test_openrouter_lists_its_models_before_a_key() -> None:
    fetch = Lister({"data": [{"id": "openai/gpt-5"}]})
    assert lc.ModelLists(fetch).models("openrouter", "") == ["openai/gpt-5"]
    # No key to check, and none sent.
    assert fetch.asked == [("https://openrouter.ai/api/v1/models", {})]
    fetch.answer = {"data": []}
    with pytest.raises(lc.ModelListError, match=r"^OpenRouter listed no models\.$"):
        lc.ModelLists(fetch).models("openrouter", "")


def test_claude_lists_through_its_sdk() -> None:
    keys: list[str] = []
    lists = lc.ModelLists(Lister({}), claude=lambda key: keys.append(key) or ["claude-x"])  # type: ignore[func-returns-value]
    assert lists.models("claude", KEY) == ["claude-x"] and keys == [KEY]


def test_a_list_is_kept_a_while_for_each_key() -> None:
    now = [0.0]
    fetch = Lister({"data": [{"id": "gpt-5"}]})
    lists = lc.ModelLists(fetch, clock=lambda: now[0])
    lists.models("openai", KEY)
    lists.models("openai", KEY)
    assert len(fetch.asked) == 1
    lists.models("openai", "another-key")
    assert len(fetch.asked) == 2
    now[0] = lc.MODELS_KEPT_S + 1
    lists.models("openai", KEY)
    assert len(fetch.asked) == 3


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", code, "no", HttpHeaders(), io.BytesIO(b""))


@pytest.mark.parametrize(
    ("answer", "said"),
    [
        (http_error(401), "Grok refused the API key."),
        (http_error(500), r"Grok couldn't list its models \(500\)."),
        (urllib.error.URLError("down"), "Grok's models couldn't be listed. Try again."),
        ({"error": "what"}, "Grok's models couldn't be listed. Try again."),
        ({"models": []}, "Grok listed no models for this key."),
    ],
)
def test_a_list_that_cant_be_had_says_why(
    answer: Any, said: str, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(lc.ModelListError, match=said):
        lc.ModelLists(Lister(answer)).models("grok", KEY)
    assert KEY not in caplog.text


def test_only_a_provider_with_a_key_can_be_listed() -> None:
    lists = lc.ModelLists(Lister({}))
    with pytest.raises(lc.ModelListError, match="Only a provider"):
        lists.models("local", KEY)
    with pytest.raises(lc.ModelListError, match="Enter your Grok API key first"):
        lists.models("grok", "")


def test_the_app_lists_models_with_the_key_given_or_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetch = Lister({"models": [{"id": "grok-4"}]})
    monkeypatch.setattr("imageskin.app.ModelLists", lambda: lc.ModelLists(fetch))
    app = TestClient(
        create_app(
            tmp_path,
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=lambda photo, text, output: None,
            ask_llm=lambda messages: "Hi",
        )
    )
    missing = app.post("/api/llm/models", json={"provider": "grok"})
    assert missing.status_code == 400 and "Enter your Grok API key" in missing.json()["detail"]
    given = app.post("/api/llm/models", json={"provider": "grok", "api_key": " typed "})
    assert given.json() == {"models": ["grok-4"]}
    assert fetch.asked[-1][1] == {"Authorization": "Bearer typed"}
    lc.save_choice(tmp_path, "grok", "saved-key")
    app.post("/api/llm/models", json={"provider": "grok"})
    assert fetch.asked[-1][1] == {"Authorization": "Bearer saved-key"}
    assert app.post("/api/llm/models", json={"provider": "duke"}).status_code == 400
    fetch.answer = http_error(401)
    refused = app.post("/api/llm/models", json={"provider": "grok", "api_key": "bad"})
    assert refused.status_code == 400 and refused.json()["detail"] == "Grok refused the API key."
    # 502 only when the provider couldn't be asked, so the page offers a typed name then.
    fetch.answer = urllib.error.URLError("down")
    down = app.post("/api/llm/models", json={"provider": "grok", "api_key": "other"})
    assert down.status_code == 502
    fetch.answer = {"data": [{"id": "a/one"}]}
    anyone = app.post("/api/llm/models", json={"provider": "openrouter"})
    assert anyone.json() == {"models": ["a/one"]} and fetch.asked[-1][1] == {}
    assert not app.get("/api/llm").json()["providers"][0]["lists_freely"]
    assert app.get("/api/llm").json()["providers"][-1]["lists_freely"]


def test_a_key_the_provider_refuses_is_not_saved(app: TestClient) -> None:
    lists = lc.ModelLists(Lister(http_error(401)))
    with patch.object(lc.ModelLists, "models", lists.models):
        refused = app.put("/api/llm", json={"provider": "grok", "api_key": "bad-key"})
    assert refused.status_code == 400
    assert refused.json()["detail"] == "Grok refused the API key. Check it and paste it again."
    shown = app.get("/api/llm").json()
    assert shown["provider"] == "local"
    assert not next(p for p in shown["providers"] if p["id"] == "grok")["has_key"]


def test_a_key_that_cant_be_checked_is_saved_unchecked(
    app: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    lists = lc.ModelLists(Lister(urllib.error.URLError("down")))
    with patch.object(lc.ModelLists, "models", lists.models):
        saved = app.put("/api/llm", json={"provider": "grok", "api_key": "maybe-key"})
    assert saved.status_code == 200 and saved.json()["provider"] == "grok"
    assert "Could not check the API key; saving it unchecked" in caplog.messages
    assert "maybe-key" not in caplog.text


def test_openrouter_refusing_the_key_says_so() -> None:
    with pytest.raises(lc.ModelListError, match="OpenRouter refused the API key") as refused:
        lc.ModelLists(Lister(http_error(401))).models("openrouter", KEY)
    assert refused.value.refused


# A change made while the LLM is in use (reviews on PR #115)


def in_thread(run: Any) -> threading.Thread:
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def test_a_pinned_thread_keeps_its_llm_until_it_is_done() -> None:
    with patch.object(lc, "llm_client", Recorder):
        switch = lc.SwitchableLlm(BASE, lc.LlmChoice())
        pinned, changed = threading.Event(), threading.Event()
        answers: list[str] = []

        def prompt() -> None:
            with switch.pinned():
                pinned.set()
                changed.wait(5)
                with switch.pinned():  # inside another, the outer one's LLM holds
                    answers.append(switch.ask([]))
                answers.append(str(switch.local))
            answers.append(switch.ask([]))

        thread = in_thread(prompt)
        pinned.wait(5)
        switch.use(lc.LlmChoice("grok", {"grok": KEY}))
        assert switch.ask([]) == "grok 300 None"  # another thread has the new one at once
        changed.set()
        thread.join(5)
    assert answers == ["local 300 None", "True", "grok 300 None"]


def test_a_prompt_finishes_on_the_llm_it_began_with(
    app: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    measuring, changed = threading.Event(), threading.Event()

    class SlowClaude(FakeClaude):
        def context_tokens(self) -> int:
            # The prompt has been measured with Claude's window; it is sent after the change.
            if not measuring.is_set():
                measuring.set()
                changed.wait(5)
            return 4096

    monkeypatch.setattr(lc, "ClaudeClient", SlowClaude)
    app.put("/api/llm", json={"provider": "claude", "api_key": "sk-ant"})
    answers: list[str] = []
    thread = in_thread(lambda: answers.append(ask(app)))
    assert measuring.wait(5)
    assert app.put("/api/llm", json={"provider": "openai", "api_key": "sk-oa"}).status_code == 200
    changed.set()
    thread.join(10)
    assert answers == ["Answered by Claude."]
    assert ask(app) == "Answered by gpt-4.1-mini."  # the next prompt has the new one


def test_a_wiki_build_is_made_by_one_llm() -> None:
    parts: list[str] = []
    with patch.object(lc, "llm_client", Recorder):
        switch = lc.SwitchableLlm(BASE, lc.LlmChoice())

        def build_wiki(pdf_id: str, pieces: Any, ask: Any, *rest: Any) -> list[str]:
            # A part, then the LLM is changed on the Settings page, then the next part.
            parts.append(ask([]))
            in_thread(lambda: switch.use(lc.LlmChoice("grok", {"grok": KEY}))).join(5)
            parts.append(ask([]))
            return []

        with patch.object(app_module, "build_wiki", build_wiki):
            app_module.wiki_builder(BASE, switch, None)("p1", [], lambda *a: None, lambda *a: None)
        assert switch.ask([]).startswith("grok")  # the next build has the new one
    assert [p.split()[0] for p in parts] == ["local", "local"]


def test_an_outline_is_made_by_one_llm() -> None:
    parts: list[str] = []
    with patch.object(lc, "llm_client", Recorder):
        switch = lc.SwitchableLlm(BASE, lc.LlmChoice())

        class Outliner:
            def __init__(self, pdf_id: str, ask: Any, *rest: Any) -> None:
                self.ask = ask

            def outline(self, topics: Any, pieces: Any) -> list[str]:
                parts.append(self.ask([], {}))
                in_thread(lambda: switch.use(lc.LlmChoice("grok", {"grok": KEY}))).join(5)
                parts.append(self.ask([], {}))
                return []

        with patch.object(app_module, "Outliner", Outliner):
            build = app_module.outline_builder(BASE, switch, None)
            build("p1", [], [], lambda *a: None, lambda *a: None)
        assert switch.ask([]).startswith("grok")
    assert [p.split()[0] for p in parts] == ["local", "local"]


def test_two_changes_made_together_end_on_the_same_llm(
    app: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_save = lc.save_choice
    first_saved, second_saved = threading.Event(), threading.Event()

    def save(home: Path, provider: str, *args: Any, **kwargs: Any) -> lc.LlmChoice:
        choice = real_save(home, provider, *args, **kwargs)
        if provider == "openai":
            first_saved.set()
            # Without one step for saving and switching, Grok's change would be saved and made
            # live here, and then OpenAI's made live after it.
            second_saved.wait(0.5)
        else:
            second_saved.set()
        return choice

    monkeypatch.setattr("imageskin.app.save_choice", save)
    statuses: list[int] = []
    first = in_thread(
        lambda: statuses.append(
            app.put("/api/llm", json={"provider": "openai", "api_key": "sk-oa"}).status_code
        )
    )
    assert first_saved.wait(5)
    second = in_thread(
        lambda: statuses.append(
            app.put("/api/llm", json={"provider": "grok", "api_key": "xai-k3y"}).status_code
        )
    )
    first.join(10)
    second.join(10)
    assert statuses == [200, 200]
    assert lc.load_choice(tmp_path).provider == "grok"
    assert app.get("/api/llm").json()["provider"] == "grok"
    assert ask(app) == "Answered by grok-4."
