"""Answers through the ChatGPT plan (roadmap R43a)."""

import io
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
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


def http_error(
    code: int, error_code: str = "", param: str = "", message: str = ""
) -> urllib.error.HTTPError:
    error = {
        "message": message,
        "code": error_code,
        **({"param": param} if param else {}),
    }
    body = json.dumps({"error": error} if error_code else {"error": 1}).encode()
    headers = HttpHeaders()
    headers["x-request-id"] = "req-1"
    return urllib.error.HTTPError(URL, code, "refused", headers, io.BytesIO(body))


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

    @contextmanager
    def __call__(self, renew: bool) -> Iterator[str]:
        if renew:
            self.n += 1
            self.renewed += 1
        yield f"token-{self.n}"


def client(*answers: list[bytes] | BaseException) -> tuple[ChatGptPlanClient, FakeResponses]:
    api = FakeResponses(*answers)
    return ChatGptPlanClient(SETTINGS, Tokens(), opener=api), api


def test_the_plan_lists_the_models_meant_to_be_shown_in_its_order() -> None:
    # Only those marked "list" (a review on PR #118), shown by their display names.
    listed = {
        "models": [
            {"slug": "gpt-b", "display_name": "GPT B", "visibility": "list"},
            {"slug": "gpt-hidden", "display_name": "Hidden", "visibility": "hide"},
            {"slug": "gpt-unmarked", "display_name": "Unmarked"},
            {"slug": "gpt-a", "visibility": "list"},
            {"id": "gpt-c", "visibility": "list"},
            {"slug": "gpt-b", "visibility": "list"},
            "not a model",
            {"visibility": "list"},
        ]
    }
    assert plan_models(listed) == [("gpt-b", "GPT B"), ("gpt-a", "gpt-a")]
    with pytest.raises(ValueError):
        plan_models({"data": [{"slug": "gpt-d", "visibility": "list"}]})


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
    # An account OpenAI won't take even with a renewed token keeps its sign-in, and the
    # request ID is given (a review on PR #118).
    invalid = http_error(401, "subscription_sharing_invalid_user")
    refused, api = client(invalid, http_error(401, "subscription_sharing_invalid_user"))
    with pytest.raises(LlmError, match=r"\(request ID req-1\)\. Your sign-in is kept") as said:
        list(refused.stream(MESSAGES))
    assert "Sign in" not in str(said.value) and len(api.asked) == 2


def test_a_plan_service_down_for_now_is_tried_again_after_a_wait() -> None:
    # A review on PR #118: OpenAI's temporary 503s are tried again with a growing wait, and the
    # sign-in is kept.
    for code in ("subscription_sharing_usage_unavailable", "subscription_sharing_user_unavailable"):
        waits: list[float] = []
        api = FakeResponses(http_error(503, code), http_error(503, code), text("Four."))
        plan = ChatGptPlanClient(SETTINGS, Tokens(), opener=api, sleep=waits.append)
        assert list(plan.stream(MESSAGES)) == ["Four."] and waits == [1.0, 2.0]
        api = FakeResponses(*[http_error(503, code) for _ in range(3)])
        plan = ChatGptPlanClient(SETTINGS, Tokens(), opener=api, sleep=waits.append)
        with pytest.raises(LlmError, match="can't use your plan right now. Your sign-in is kept"):
            list(plan.stream(MESSAGES))
        assert len(api.asked) == 3
    assert SIGN_IN_AGAIN.startswith("ChatGPT refused the sign-in")


@pytest.mark.parametrize(
    ("answer", "said"),
    [
        (http_error(429), "reached its limit"),
        # A 403 is not always the model's fault (a review on PR #118).
        (http_error(403), r"refused the prompt \(403\)"),
        (http_error(403, "subscription_sharing_user_not_eligible"), "plan can't be used here"),
        # Each code's own recovery: the app's route isn't the plan's fault, a part the plan
        # can't take is named, and an authorization context is the sign-in's scope (a review
        # on PR #118). None of them says to try again.
        (
            http_error(400, "subscription_sharing_route_not_supported"),
            r"unsupported route\). This is a problem with the app, not your plan",
        ),
        (
            http_error(400, "subscription_sharing_unsupported_capability", "tools"),
            r"part of the app's request through a plan \(tools\)\. Pick another LLM",
        ),
        (
            http_error(400, "subscription_sharing_unsupported_capability"),
            r"through a plan\. Pick another LLM",
        ),
        (
            events(
                {
                    "type": "response.failed",
                    "response": {
                        "error": {
                            "code": "subscription_sharing_unsupported_capability",
                            "param": "text.format",
                        }
                    },
                }
            ),
            r"through a plan \(text\.format\)",
        ),
        # A body longer than the logged part still gives its code and param (a review on
        # PR #118).
        (
            http_error(400, "subscription_sharing_unsupported_capability", "tools", "x" * 2000),
            r"through a plan \(tools\)",
        ),
        # The app's grant, which signing in or allowing plan use again won't fix.
        (
            http_error(403, "chatpass_v2_invalid_authorization_context"),
            r"access to plans \(chatpass_v2_invalid_authorization_context\)\. This is a problem",
        ),
        (
            http_error(403, "chatpass_v2_scope_not_authorized"),
            r"refused this app's access to plans \(chatpass_v2_scope_not_authorized\)",
        ),
        (
            events(
                {
                    "type": "response.failed",
                    "response": {"error": {"code": "subscription_sharing_user_unavailable"}},
                }
            ),
            "can't use your plan right now",
        ),
        (http_error(403, "other_thing"), r"refused the prompt \(403: other_thing\)"),
        (http_error(404, "model_not_found"), "doesn't know the model"),
        (http_error(400, "subscription_sharing_usage_limit_exceeded"), "reached its limit"),
        # A plan's limit can also end a stream that had begun.
        (
            events(
                {"type": "response.output_text.delta", "delta": "Fo"},
                {
                    "type": "response.failed",
                    "response": {
                        "id": "resp_1",
                        "error": {"code": "subscription_sharing_usage_limit_exceeded"},
                    },
                },
            ),
            "reached its limit",
        ),
        (
            events({"type": "response.failed", "response": {"error": {"code": "odd"}}}),
            r"couldn't answer that \(odd\)",
        ),
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


def test_an_incomplete_reply_is_not_an_answer(caplog: pytest.LogCaptureFixture) -> None:
    # Only response.completed is a whole answer (a review on PR #118).
    delta = {"type": "response.output_text.delta", "delta": "Four"}
    reason = {"response": {"incomplete_details": {"reason": "max_output_tokens"}}}
    cut = events(delta, {"type": "response.incomplete", **reason})
    plan, _ = client(cut, events(delta, {"type": "response.incomplete"}), [b"data: [DONE]\n"])
    with pytest.raises(LlmError, match=r"didn't finish its reply \(max_output_tokens\)"):
        list(plan.stream(MESSAGES))
    assert "ChatGPT left its reply unfinished" in caplog.messages
    with pytest.raises(LlmError, match=r"\(unknown\)"):
        plan.ask(MESSAGES)  # the part sent is not returned as the answer
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
    @contextmanager
    def none(renew: bool) -> Iterator[str]:
        raise LlmError(cs.SIGN_IN_FIRST)
        yield ""

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
        self.revoked: list[str] = []

    def __call__(self, url: str, form: dict[str, str] | None) -> tuple[int, Any]:
        if form is None:
            return 200, {
                "issuer": cs.ISSUER,
                "authorization_endpoint": f"{cs.ISSUER}/oauth/authorize",
                "token_endpoint": f"{cs.ISSUER}/oauth/token",
                "jwks_uri": f"{cs.ISSUER}/jwks",
                "revocation_endpoint": f"{cs.ISSUER}/oauth/revoke",
            }
        if url.endswith("/revoke"):
            self.revoked.append(form["token"])
            return 200, {}
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
    ("status", "error", "said", "connected"),
    [
        (400, "invalid_grant", "sign-in has ended", False),
        (400, "invalid_refresh_token", "sign-in has ended", False),
        (401, "token_expired", "sign-in has ended", False),
        (400, "refresh_token_expired", "sign-in has ended", False),
        (400, "refresh_token_invalidated", "sign-in has ended", False),
        (400, "refresh_token_reused", "sign-in has ended", False),
        # The app's registration, not the account: signing in again won't help, so the tokens
        # stay (a review on PR #118).
        (401, "invalid_client", r"registration \(invalid_client\).*not your account", True),
        (400, "unauthorized_client", "registration", True),
        (400, "temporarily_unavailable", "can't be renewed right now", True),
        (503, "", "can't be renewed right now", True),
    ],
)
def test_a_renewal_that_fails_says_why(
    tmp_path: Path, status: int, error: str, said: str, connected: bool
) -> None:
    # Tokens OpenAI won't renew are forgotten, so the page asks for a sign-in; a failure that
    # may pass keeps them (a review on PR #118).
    signed_in(tmp_path, NOW - 1)
    who = signin(tmp_path, FakeAuth(status, {"error": error}))
    with pytest.raises(SignInError, match=said):
        who.access_token()
    assert who.status()["connected"] is connected
    registration = json.loads((tmp_path / cs.FILENAME).read_text())["registrations"][0]
    assert registration["client_id"] == "app_1"  # kept, to sign in as it again


def test_no_sign_in_or_no_plan_use_has_no_token(tmp_path: Path) -> None:
    who = signin(tmp_path, FakeAuth())
    with pytest.raises(SignInError, match="Sign in with ChatGPT on the Settings page first"):
        who.access_token()
    with pytest.raises(LlmError, match="Sign in with ChatGPT on the Settings page first"):
        with who.plan_session():
            pass
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

    auth = Disconnecting()
    # The renewed session is ended at OpenAI and its token isn't handed out.
    with pytest.raises(SignInError, match="Sign in with ChatGPT on the Settings page first"):
        signin(tmp_path, auth).access_token()
    assert auth.revoked == ["refresh-2"]
    saved = json.loads((tmp_path / cs.FILENAME).read_text())["registrations"][0]
    assert saved["credentials"] is None


def test_disconnect_waits_for_a_renewal_and_revokes_the_token_it_brought(tmp_path: Path) -> None:
    # A review on PR #118: Disconnect during a renewal must end the renewed session, and no
    # token is handed out after it.
    signed_in(tmp_path, NOW - 1)
    renewing, release = threading.Event(), threading.Event()

    class Slow(FakeAuth):
        def __call__(self, url: str, form: dict[str, str] | None) -> tuple[int, Any]:
            if form is not None and form.get("grant_type") == "refresh_token":
                renewing.set()
                assert release.wait(5)
            return super().__call__(url, form)

    auth = Slow()
    who = signin(tmp_path, auth)
    got: list[str] = []
    renewal = threading.Thread(target=lambda: got.append(who.access_token()))
    renewal.start()
    assert renewing.wait(5)
    disconnected: list[dict[str, Any]] = []
    disconnect = threading.Thread(target=lambda: disconnected.append(who.sign_out()))
    disconnect.start()
    disconnect.join(0.2)
    assert disconnect.is_alive() and auth.revoked == []  # it waits for the renewal
    release.set()
    renewal.join(5)
    disconnect.join(5)
    assert got == ["access-2"]  # handed out before Disconnect began
    assert auth.revoked == ["refresh-2"]  # the replacement, not the used-up refresh-1
    assert disconnected[0]["revoked"] is True and not disconnected[0]["connected"]
    with pytest.raises(SignInError, match="Sign in with ChatGPT on the Settings page first"):
        who.access_token()


def test_no_request_is_sent_after_disconnect(tmp_path: Path) -> None:
    # A review on PR #118: a request is held with its token until it is sent, so Disconnect
    # waits for one being sent, and one that waited for Disconnect sends nothing.
    signed_in(tmp_path, NOW + 3000)
    auth = FakeAuth()
    who = signin(tmp_path, auth)
    sending, release = threading.Event(), threading.Event()
    sent: list[str] = []

    def opener(request: urllib.request.Request, timeout: float) -> Response:
        sent.append(request.get_header("Authorization") or "")
        sending.set()
        assert release.wait(5)
        return Response(text("Four."))

    plan = ChatGptPlanClient(SETTINGS, who.plan_session, opener=opener)
    answered: list[list[str]] = []
    asking = threading.Thread(target=lambda: answered.append(list(plan.stream(MESSAGES))))
    asking.start()
    assert sending.wait(5)
    disconnect = threading.Thread(target=who.sign_out)
    disconnect.start()
    disconnect.join(0.2)
    assert disconnect.is_alive()  # waits for the request being sent
    release.set()
    asking.join(5)
    disconnect.join(5)
    assert answered == [["Four."]] and sent == ["Bearer access-1"]

    # Now Disconnect holds things up while a request waits: once it is done, nothing is sent.
    signed_in(tmp_path, NOW + 3000)
    revoking, finish = threading.Event(), threading.Event()

    class SlowRevoke(FakeAuth):
        def __call__(self, url: str, form: dict[str, str] | None) -> tuple[int, Any]:
            if url.endswith("/revoke"):
                revoking.set()
                assert finish.wait(5)
            return super().__call__(url, form)

    slow = signin(tmp_path, SlowRevoke())
    plan = ChatGptPlanClient(SETTINGS, slow.plan_session, opener=opener)
    sent.clear()
    disconnect = threading.Thread(target=slow.sign_out)
    disconnect.start()
    assert revoking.wait(5)
    errors: list[BaseException] = []

    def ask() -> None:
        try:
            list(plan.stream(MESSAGES))
        except LlmError as e:
            errors.append(e)

    asking = threading.Thread(target=ask)
    asking.start()
    asking.join(0.2)
    assert asking.is_alive() and sent == []  # waits for Disconnect
    finish.set()
    disconnect.join(5)
    asking.join(5)
    assert sent == [] and "Sign in with ChatGPT on the Settings page first" in str(errors[0])


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
        return {
            "models": [
                {"slug": "gpt-z", "visibility": "list"},
                {"slug": "gpt-a", "display_name": "GPT A", "visibility": "list"},
            ]
        }

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
        llm = lc.SwitchableLlm(LlmSettings(), lc.LlmChoice(), plan_session=Tokens())
        llm.use(lc.LlmChoice("chatgpt", models={"chatgpt": "gpt-plan"}))
        assert list(llm.stream(MESSAGES)) == ["Through the plan."]
    unsigned = lc.SwitchableLlm(LlmSettings(), lc.LlmChoice("chatgpt"))
    with patch("imageskin.chatgpt_plan.urllib.request.urlopen") as never:
        with pytest.raises(LlmError, match="Sign in with ChatGPT"):
            list(unsigned.stream(MESSAGES))
    never.assert_not_called()


# Each account's own models, by its token.
CATALOGS = {
    "Bearer access-1": {
        "models": [
            {"slug": "gpt-first", "display_name": "GPT First", "visibility": "list"},
            {"slug": "gpt-second", "visibility": "list"},
        ]
    },
    "Bearer access-b": {"models": [{"slug": "gpt-other", "visibility": "list"}]},
}


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeResponses]:
    api = FakeResponses(text("Answered through the plan."))
    monkeypatch.setattr(lc, "ChatGptPlanClient", lambda s, t: ChatGptPlanClient(s, t, api))

    def fetch(url: str, headers: dict[str, str]) -> Any:
        return CATALOGS[headers["Authorization"]]

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
    assert listed.json() == {
        "models": ["gpt-first", "gpt-second"],
        "names": {"gpt-first": "GPT First"},
    }
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


def test_switching_account_follows_its_own_models(
    app: tuple[TestClient, FakeResponses], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # A review on PR #118: after a switch, the next request uses the new account's token with a
    # model from its own list, not the one saved for the account before.
    caplog.set_level(logging.INFO)
    client, api = app
    signed_in(tmp_path, time.time() + 3600)
    data = json.loads((tmp_path / cs.FILENAME).read_text())
    other = {
        "client_id": "app_b",
        "email": "other@example.com",
        "credentials": {
            "scopes": cs.SCOPES.split(),
            "access_token": "access-b",
            "refresh_token": "refresh-b",
            "expires_at": time.time() + 3600,
        },
    }
    data["registrations"].append(other)
    (tmp_path / cs.FILENAME).write_text(json.dumps(data))
    assert client.put("/api/llm", json={"provider": "chatgpt", "model": "gpt-second"}).is_success
    switched = client.post("/api/chatgpt/use", json={"account": "app_b"})
    assert switched.json()["email"] == "other@example.com"
    plan = client.get("/api/llm").json()["providers"][-1]
    assert plan["model"] == "gpt-other"
    assert "ChatGPT plan model changed for the account in use" in caplog.messages
    listed = client.post("/api/llm/models", json={"provider": "chatgpt"})
    assert listed.json()["models"] == ["gpt-other"]
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "What is two plus two?"})
    body, auth = api.asked[-1]
    assert (body["model"], auth) == ("gpt-other", "Bearer access-b")
    # Back to the first account: its list has neither, so its first is saved again.
    client.post("/api/chatgpt/use", json={"account": "app_1"})
    assert client.get("/api/llm").json()["providers"][-1]["model"] == "gpt-first"


def test_an_account_whose_list_cant_be_had_keeps_the_model(
    app: tuple[TestClient, FakeResponses], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client, _ = app
    signed_in(tmp_path, time.time() + 3600)
    assert client.put("/api/llm", json={"provider": "chatgpt", "model": "gpt-second"}).is_success
    with patch.object(lc.ModelLists, "models", side_effect=lc.ModelListError("down")):
        client.post("/api/chatgpt/use", json={"account": "app_1"})
    assert client.get("/api/llm").json()["providers"][-1]["model"] == "gpt-second"
    assert "Could not check the ChatGPT plan's model" in caplog.messages
    # Not answering through the plan: nothing to check.
    client.put("/api/llm", json={"provider": "local"})
    with patch.object(lc.ModelLists, "models") as never:
        client.post("/api/chatgpt/use", json={"account": "app_1"})
    never.assert_not_called()


def test_no_model_list_is_fetched_after_disconnect(tmp_path: Path) -> None:
    # A review on PR #118: the plan's model list is fetched with the sign-in held, as a reply's
    # request is, so Disconnect waits for a fetch under way, and a fetch that waited for
    # Disconnect is never sent.
    fetching, release = threading.Event(), threading.Event()
    sent: list[str] = []

    def fetch(url: str, headers: dict[str, str]) -> Any:
        sent.append(headers["Authorization"])
        fetching.set()
        assert release.wait(5)
        return CATALOGS["Bearer access-1"]

    revoking, finish = threading.Event(), threading.Event()

    class SlowRevoke(FakeAuth):
        slow = False

        def __call__(self, url: str, form: dict[str, str] | None) -> tuple[int, Any]:
            if url.endswith("/revoke") and self.slow:
                revoking.set()
                assert finish.wait(5)
            return super().__call__(url, form)

    auth = SlowRevoke()
    lists = lc.ModelLists(fetch)
    with patch("imageskin.app.ModelLists", lambda: lists):
        client = TestClient(
            create_app(
                tmp_path,
                check_photo=lambda p: PhotoResult([], 80),
                prepare_voice=lambda: None,
                prepare_face=lambda photo, progress: None,
                render_clip=lambda photo, text, output: None,
                llm=LlmSettings(model="local"),
                chatgpt=ChatGptSignIn(tmp_path, http=auth),
            )
        )
    client.post("/api/consent", json={"agreed": True})

    def in_background(path: str, out: list[Any]) -> threading.Thread:
        body = {"provider": "chatgpt"}
        thread = threading.Thread(target=lambda: out.append(client.post(path, json=body)))
        thread.start()
        return thread

    signed_in(tmp_path, time.time() + 3600)
    listed: list[Any] = []
    listing = in_background("/api/llm/models", listed)
    assert fetching.wait(5)
    disconnected: list[Any] = []
    disconnect = in_background("/api/chatgpt/sign-out", disconnected)
    disconnect.join(0.2)
    assert disconnect.is_alive()  # waits for the list being fetched
    release.set()
    listing.join(5)
    disconnect.join(5)
    assert listed[0].json()["models"] == ["gpt-first", "gpt-second"]
    assert sent == ["Bearer access-1"] and not disconnected[0].json()["connected"]

    # Now Disconnect holds things up while a list is asked for: once it is done, none is fetched
    # (another token, so the list isn't one fetched before).
    signed_in(tmp_path, time.time() + 3600)
    data = json.loads((tmp_path / cs.FILENAME).read_text())
    data["registrations"][0]["credentials"]["access_token"] = "access-c"
    (tmp_path / cs.FILENAME).write_text(json.dumps(data))
    auth.slow = True
    sent.clear()
    disconnect = in_background("/api/chatgpt/sign-out", disconnected)
    assert revoking.wait(5)
    listed.clear()
    listing = in_background("/api/llm/models", listed)
    listing.join(0.2)
    assert listing.is_alive() and sent == []  # waits for Disconnect
    finish.set()
    disconnect.join(5)
    listing.join(5)
    assert sent == [] and listed[0].status_code == 400
    assert listed[0].json()["detail"] == cs.SIGN_IN_FIRST
