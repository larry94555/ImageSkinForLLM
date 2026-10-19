"""Answers through the ChatGPT plan (roadmap R43a)."""

import io
import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from email.message import Message as HttpHeaders
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from imageskin import chatgpt_signin as cs
from imageskin import llm_choice as lc
from imageskin.app import create_app
from imageskin.chat import DECLINED, EmptyReply, LlmError, LlmSettings, Message
from imageskin.chatgpt_plan import (
    SIGN_IN_AGAIN,
    URL,
    ChatGptPlanClient,
    plan_models,
    request_body,
)
from imageskin.chatgpt_signin import ChatGptSignIn, SignInError
from imageskin.review import Review
from imageskin.uploads import PhotoResult

SETTINGS = LlmSettings(
    url="https://api.openai.com/v1", model="gpt-plan", provider="chatgpt", context_tokens=8192
)
MESSAGES: list[Message] = [
    {"role": "system", "content": "Be brief."},
    {"role": "user", "content": "Hi"},
    {"role": "assistant", "content": "Hello."},
    {"role": "user", "content": "What is two plus two?"},
]


def events(*items: dict[str, Any]) -> list[bytes]:
    """A stream of server-sent events, as OpenAI sends them."""
    lines: list[bytes] = []
    for item in items:
        lines += [f"event: {item['type']}\n".encode(), f"data: {json.dumps(item)}\n".encode()]
        lines.append(b"\n")
    return lines


def text(*pieces: str) -> list[bytes]:
    deltas = [{"type": "response.output_text.delta", "delta": p} for p in pieces]
    return events({"type": "response.created"}, *deltas, {"type": "response.completed"})


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(URL, code, "refused", HttpHeaders(), io.BytesIO(b'{"error": 1}'))


class Response:
    def __init__(self, lines: list[bytes]) -> None:
        self.lines = lines

    def __enter__(self) -> list[bytes]:
        return self.lines

    def __exit__(self, *exc: object) -> None:
        pass


class FakeResponses:
    """OpenAI's Responses API: answers each request with the next of `answers`, a stream of
    events or an error to raise."""

    def __init__(self, *answers: list[bytes] | BaseException) -> None:
        self.answers = list(answers)
        self.asked: list[tuple[dict[str, Any], str]] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> Response:
        assert request.full_url == URL and isinstance(request.data, bytes)
        self.asked.append((json.loads(request.data), request.get_header("Authorization") or ""))
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return Response(answer)


class Tokens:
    """The sign-in's tokens: renewing gives the next."""

    def __init__(self) -> None:
        self.n = 1
        self.renewed = 0

    def __call__(self, renew: bool) -> str:
        if renew:
            self.n += 1
            self.renewed += 1
        return f"token-{self.n}"


def client(*answers: list[bytes] | BaseException) -> tuple[ChatGptPlanClient, FakeResponses]:
    api = FakeResponses(*answers)
    return ChatGptPlanClient(SETTINGS, Tokens(), opener=api), api


def test_the_plan_lists_the_models_meant_to_be_shown_in_its_order() -> None:
    listed = {
        "models": [
            {"slug": "gpt-b", "visibility": "list"},
            {"slug": "gpt-hidden", "visibility": "hide"},
            {"slug": "gpt-a"},
            {"id": "gpt-c", "visibility": "list"},
            {"slug": "gpt-b", "visibility": "list"},
            "not a model",
            {"visibility": "list"},
        ]
    }
    assert plan_models(listed) == ["gpt-b", "gpt-a", "gpt-c"]
    assert plan_models({"data": [{"id": "gpt-d"}]}) == ["gpt-d"]
    with pytest.raises(ValueError):
        plan_models({"error": "nothing"})


def test_a_request_is_streamed_unstored_with_the_system_prompt_as_instructions() -> None:
    body = request_body("gpt-plan", MESSAGES)
    assert body == {
        "model": "gpt-plan",
        "input": [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello."},
            {"role": "user", "content": "What is two plus two?"},
        ],
        "stream": True,
        "store": False,
        "instructions": "Be brief.",
    }
    assert "instructions" not in request_body("gpt-plan", MESSAGES[1:])
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    shaped = request_body("gpt-plan", MESSAGES, schema)["text"]["format"]
    assert shaped["type"] == "json_schema" and shaped["strict"] is True
    assert shaped["schema"]["additionalProperties"] is False


def test_the_reply_streams_in_pieces_with_the_accounts_token() -> None:
    plan, api = client(text("Two plus ", "two is four."))
    assert list(plan.stream(MESSAGES)) == ["Two plus ", "two is four."]
    assert api.asked[0][1] == "Bearer token-1"
    assert api.asked[0][0]["model"] == "gpt-plan"
    assert plan.count("four") >= 1 and plan.context_tokens() == 8192
    plan.warm_up()  # nothing to warm up


def test_ask_joins_the_streamed_reply(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    plan, api = client(text(" Four. "), text())
    assert plan.ask(MESSAGES, schema={"type": "object"}) == "Four."
    assert "text" in api.asked[0][0] and "max_output_tokens" not in api.asked[0][0]
    assert "ChatGPT answered" in caplog.messages
    with pytest.raises(EmptyReply):
        plan.ask(MESSAGES)


def test_a_refused_token_is_renewed_once() -> None:
    plan, api = client(http_error(401), text("Four."))
    assert list(plan.stream(MESSAGES)) == ["Four."]
    assert [auth for _, auth in api.asked] == ["Bearer token-1", "Bearer token-2"]
    twice, _ = client(http_error(401), http_error(401))
    with pytest.raises(LlmError, match="Sign in with ChatGPT again"):
        list(twice.stream(MESSAGES))
    assert SIGN_IN_AGAIN.startswith("ChatGPT refused the sign-in")


@pytest.mark.parametrize(
    ("answer", "said"),
    [
        (http_error(429), "reached its limit"),
        (http_error(403), "isn't allowed to use this model"),
        (http_error(404), "doesn't know the model"),
        (http_error(400), r"refused the prompt \(400\)"),
        (urllib.error.URLError("down"), "Could not reach ChatGPT"),
        (events({"type": "response.refusal.delta", "delta": "No."}), DECLINED),
        (events({"type": "response.failed", "response": {"error": {"m": 1}}}), "couldn't answer"),
        (events({"type": "error", "message": "bad"}), "couldn't answer"),
        (events({"type": "response.output_text.delta", "delta": "Fo"}), "before finishing"),
        ([b"data: {not json\n"], "could not be read"),
    ],
)
def test_a_reply_that_fails_says_why_in_plain_words(
    answer: list[bytes] | BaseException, said: str, caplog: pytest.LogCaptureFixture
) -> None:
    plan, _ = client(answer)
    with pytest.raises(LlmError, match=said):
        list(plan.stream(MESSAGES))
    assert "token-1" not in caplog.text


def test_an_incomplete_reply_or_done_marker_ends_the_stream() -> None:
    delta = {"type": "response.output_text.delta", "delta": "Four"}
    cut = events(delta, {"type": "response.incomplete"})
    plan, _ = client(cut, [b"data: [DONE]\n"])
    assert list(plan.stream(MESSAGES)) == ["Four"]
    with pytest.raises(LlmError, match="before finishing"):
        list(plan.stream(MESSAGES))


def test_a_stream_cut_off_says_so() -> None:
    class Broken:
        def __iter__(self) -> Iterator[bytes]:
            raise TimeoutError("timed out")

    def opener(request: urllib.request.Request, timeout: float) -> Any:
        return Response(Broken())  # type: ignore[arg-type]

    plan = ChatGptPlanClient(SETTINGS, Tokens(), opener=opener)
    with pytest.raises(LlmError, match="stopped answering"):
        list(plan.stream(MESSAGES))


def test_no_sign_in_says_so() -> None:
    def none(renew: bool) -> str:
        raise LlmError(cs.SIGN_IN_FIRST)

    plan = ChatGptPlanClient(SETTINGS, none, opener=FakeResponses())
    with pytest.raises(LlmError, match="Sign in with ChatGPT on the Settings page first"):
        list(plan.stream(MESSAGES))


# The sign-in's token, renewed when it is about to end


NOW = 1_800_000_000.0


class FakeAuth:
    """auth.openai.com's sign-in settings and its token endpoint, for renewing."""

    def __init__(self, status: int = 200, answer: dict[str, Any] | None = None) -> None:
        self.status = status
        self.answer = (
            answer
            if answer is not None
            else {
                "access_token": "access-2",
                "refresh_token": "refresh-2",
                "expires_in": 3600,
                "scope": cs.SCOPES,
            }
        )
        self.forms: list[dict[str, str]] = []

    def __call__(self, url: str, form: dict[str, str] | None) -> tuple[int, Any]:
        if form is None:
            return 200, {
                "issuer": cs.ISSUER,
                "authorization_endpoint": f"{cs.ISSUER}/oauth/authorize",
                "token_endpoint": f"{cs.ISSUER}/oauth/token",
                "jwks_uri": f"{cs.ISSUER}/jwks",
            }
        assert url == f"{cs.ISSUER}/oauth/token"
        self.forms.append(form)
        return self.status, self.answer


def signed_in(home: Path, expires_at: float, scopes: str = cs.SCOPES) -> None:
    credentials = {
        "scopes": scopes.split(),
        "access_token": "access-1",
        "refresh_token": "refresh-1",
        "expires_at": expires_at,
    }
    registration = {"client_id": "app_1", "email": "larry@example.com", "credentials": credentials}
    (home / cs.FILENAME).write_text(
        json.dumps({"registrations": [registration], "active": "app_1"})
    )


def signin(home: Path, auth: FakeAuth) -> ChatGptSignIn:
    return ChatGptSignIn(home, http=auth, clock=lambda: NOW)


def test_a_token_with_time_left_is_used_as_it_is(tmp_path: Path) -> None:
    auth = FakeAuth()
    signed_in(tmp_path, NOW + 3000)
    assert signin(tmp_path, auth).access_token() == "access-1"
    assert auth.forms == []


def test_a_token_about_to_end_is_renewed_and_kept(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    auth = FakeAuth()
    signed_in(tmp_path, NOW + 30)
    who = signin(tmp_path, auth)
    assert who.access_token() == "access-2"
    assert auth.forms == [
        {
            "grant_type": "refresh_token",
            "client_id": "app_1",
            "refresh_token": "refresh-1",
            "resource": "https://api.openai.com/v1",
        }
    ]
    saved = json.loads((tmp_path / cs.FILENAME).read_text())["registrations"][0]["credentials"]
    assert saved["refresh_token"] == "refresh-2" and saved["expires_at"] == NOW + 3600
    assert who.access_token() == "access-2" and len(auth.forms) == 1  # kept, not renewed again
    assert who.access_token(renew=True) == "access-2" and len(auth.forms) == 2  # refused: renewed
    assert "Renewed the ChatGPT sign-in" in caplog.messages
    assert "access-2" not in caplog.text and "refresh-2" not in caplog.text


def test_a_renewal_without_a_new_refresh_token_keeps_the_old_one(tmp_path: Path) -> None:
    signed_in(tmp_path, NOW - 1)
    signin(tmp_path, FakeAuth(answer={"access_token": "access-2", "expires_in": 60})).access_token()
    saved = json.loads((tmp_path / cs.FILENAME).read_text())["registrations"][0]["credentials"]
    assert saved["refresh_token"] == "refresh-1" and saved["scopes"] == cs.SCOPES.split()


@pytest.mark.parametrize(
    ("status", "said"),
    [(400, "sign-in has ended"), (401, "sign-in has ended"), (503, "can't be reached")],
)
def test_a_renewal_that_fails_says_why(tmp_path: Path, status: int, said: str) -> None:
    signed_in(tmp_path, NOW - 1)
    with pytest.raises(SignInError, match=said):
        signin(tmp_path, FakeAuth(status, {"error": "invalid_grant"})).access_token()


def test_no_sign_in_or_no_plan_use_has_no_token(tmp_path: Path) -> None:
    who = signin(tmp_path, FakeAuth())
    with pytest.raises(SignInError, match="Sign in with ChatGPT on the Settings page first"):
        who.access_token()
    with pytest.raises(LlmError, match="Sign in with ChatGPT on the Settings page first"):
        who.plan_token()
    signed_in(tmp_path, NOW + 3000, scopes="openid email")
    with pytest.raises(SignInError, match="Allow use of my plan"):
        who.access_token()


def test_no_refresh_token_means_signing_in_again(tmp_path: Path) -> None:
    signed_in(tmp_path, NOW - 1)
    data = json.loads((tmp_path / cs.FILENAME).read_text())
    data["registrations"][0]["credentials"]["refresh_token"] = ""
    (tmp_path / cs.FILENAME).write_text(json.dumps(data))
    with pytest.raises(SignInError, match="sign-in has ended"):
        signin(tmp_path, FakeAuth()).access_token()


def test_a_renewal_doesnt_bring_back_an_account_disconnected_meanwhile(tmp_path: Path) -> None:
    signed_in(tmp_path, NOW - 1)

    class Disconnecting(FakeAuth):
        def __call__(self, url: str, form: dict[str, str] | None) -> tuple[int, Any]:
            if form is not None:
                data = json.loads((tmp_path / cs.FILENAME).read_text())
                data["registrations"][0]["credentials"] = None
                (tmp_path / cs.FILENAME).write_text(json.dumps(data))
            return super().__call__(url, form)

    assert signin(tmp_path, Disconnecting()).access_token() == "access-2"
    saved = json.loads((tmp_path / cs.FILENAME).read_text())["registrations"][0]
    assert saved["credentials"] is None


# The ChatGPT plan in the LLM setting


def test_the_plan_needs_a_sign_in_not_a_key(tmp_path: Path) -> None:
    choice = lc.save_choice(tmp_path, "chatgpt", "ignored-key", "gpt-plan")
    assert choice.keys == {} and lc.load_choice(tmp_path) == choice
    shown = lc.described(choice)["providers"][-1]
    assert shown["id"] == "chatgpt" and shown["signs_in"] and not shown["has_key"]
    assert lc.described(choice, signed_in=True)["providers"][-1]["has_key"]
    settings = lc.settings_for(LlmSettings(), choice)
    assert (settings.url, settings.model, settings.api_key) == (
        "https://api.openai.com/v1",
        "gpt-plan",
        "",
    )


def test_the_plans_models_are_listed_with_its_token_in_its_order() -> None:
    asked: list[tuple[str, dict[str, str]]] = []

    def fetch(url: str, headers: dict[str, str]) -> Any:
        asked.append((url, headers))
        return {"models": [{"slug": "gpt-z"}, {"slug": "gpt-a"}]}

    lists = lc.ModelLists(fetch)
    assert lists.models("chatgpt", "access-1") == ["gpt-z", "gpt-a"]
    assert asked == [("https://api.openai.com/v1/models", {"Authorization": "Bearer access-1"})]
    with pytest.raises(lc.ModelListError, match="Sign in with ChatGPT on the Settings page"):
        lists.models("chatgpt", "")

    def refused(url: str, headers: dict[str, str]) -> Any:
        raise http_error(401)

    with pytest.raises(lc.ModelListError, match="Sign in with ChatGPT again") as e:
        lc.ModelLists(refused).models("chatgpt", "access-1")
    assert e.value.refused


def test_switching_to_the_plan_answers_through_it() -> None:
    api = FakeResponses(text("Through the plan."))
    with patch.object(lc, "ChatGptPlanClient", lambda s, t: ChatGptPlanClient(s, t, api)):
        llm = lc.SwitchableLlm(LlmSettings(), lc.LlmChoice(), plan_token=Tokens())
        llm.use(lc.LlmChoice("chatgpt", models={"chatgpt": "gpt-plan"}))
        assert list(llm.stream(MESSAGES)) == ["Through the plan."]
    unsigned = lc.SwitchableLlm(LlmSettings(), lc.LlmChoice("chatgpt"))
    with patch("imageskin.chatgpt_plan.urllib.request.urlopen") as never:
        with pytest.raises(LlmError, match="Sign in with ChatGPT"):
            list(unsigned.stream(MESSAGES))
    never.assert_not_called()


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeResponses]:
    api = FakeResponses(text("Answered through the plan."))
    monkeypatch.setattr(lc, "ChatGptPlanClient", lambda s, t: ChatGptPlanClient(s, t, api))

    def fetch(url: str, headers: dict[str, str]) -> Any:
        assert headers == {"Authorization": "Bearer access-1"}
        return {"models": [{"slug": "gpt-first"}, {"slug": "gpt-second"}]}

    lists = lc.ModelLists(fetch)
    monkeypatch.setattr("imageskin.app.ModelLists", lambda: lists)
    client = TestClient(
        create_app(
            tmp_path,
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=lambda photo, text, output: None,
            llm=LlmSettings(model="local"),
            chatgpt=ChatGptSignIn(tmp_path, http=FakeAuth()),
        )
    )
    client.post("/api/consent", json={"agreed": True})
    return client, api


def test_the_plan_needs_a_sign_in_first(app: tuple[TestClient, FakeResponses]) -> None:
    client, _ = app
    refused = client.put("/api/llm", json={"provider": "chatgpt"})
    assert refused.status_code == 400
    assert refused.json()["detail"] == cs.SIGN_IN_FIRST
    listed = client.post("/api/llm/models", json={"provider": "chatgpt"})
    assert listed.status_code == 400 and listed.json()["detail"] == cs.SIGN_IN_FIRST
    plan = client.get("/api/llm").json()["providers"][-1]
    assert plan["label"] == "ChatGPT plan" and not plan["has_key"]


def test_a_question_is_answered_through_the_plan(
    app: tuple[TestClient, FakeResponses], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    client, api = app
    signed_in(tmp_path, time.time() + 3600)
    assert client.get("/api/llm").json()["providers"][-1]["has_key"]
    listed = client.post("/api/llm/models", json={"provider": "chatgpt"})
    assert listed.json() == {"models": ["gpt-first", "gpt-second"]}
    chosen = client.put("/api/llm", json={"provider": "chatgpt"})
    assert chosen.status_code == 200, chosen.text
    plan = chosen.json()["providers"][-1]
    assert chosen.json()["provider"] == "chatgpt" and plan["model"] == "gpt-first"
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        answer = client.post("/api/chat", json={"prompt": "What is two plus two?"})
    assert answer.status_code == 200, answer.text
    assert answer.json()["content"] == "Answered through the plan."
    body, auth = api.asked[0]
    assert body["model"] == "gpt-first" and auth == "Bearer access-1"
    assert body["store"] is False and body["stream"] is True and body["instructions"]
    assert "access-1" not in caplog.text
    # A model entered is kept, and kept again when none is sent.
    other = client.put("/api/llm", json={"provider": "chatgpt", "model": "gpt-second"})
    assert other.json()["providers"][-1]["model"] == "gpt-second"
    kept = client.put("/api/llm", json={"provider": "chatgpt"})
    assert kept.json()["providers"][-1]["model"] == "gpt-second"


def test_a_plan_list_that_cant_be_had_asks_for_a_model_name(
    app: tuple[TestClient, FakeResponses], tmp_path: Path
) -> None:
    client, _ = app
    signed_in(tmp_path, time.time() + 3600)

    def down(provider: str, key: str) -> list[str]:
        raise lc.ModelListError("ChatGPT plan's models couldn't be listed. Try again.")

    with patch.object(lc.ModelLists, "models", side_effect=down):
        refused = client.put("/api/llm", json={"provider": "chatgpt", "model": ""})
    assert refused.status_code == 502
    assert "Type a model's name" in refused.json()["detail"]
    typed = client.put("/api/llm", json={"provider": "chatgpt", "model": "gpt-typed"})
    assert typed.status_code == 200 and typed.json()["providers"][-1]["model"] == "gpt-typed"
