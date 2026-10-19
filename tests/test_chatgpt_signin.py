"""Sign in with ChatGPT on the Settings page (roadmap R43)."""

import base64
import hashlib
import json
import logging
import urllib.parse
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from imageskin import chatgpt_signin as cs
from imageskin.app import create_app
from imageskin.chatgpt_signin import ChatGptSignIn, SignInError
from imageskin.uploads import PhotoResult

DISCOVERY = {
    "issuer": cs.ISSUER,
    "authorization_endpoint": f"{cs.ISSUER}/oauth/authorize",
    "token_endpoint": f"{cs.ISSUER}/oauth/token",
    "revocation_endpoint": f"{cs.ISSUER}/oauth/revoke",
}
NOW = 1_800_000_000.0
REDIRECT = "http://127.0.0.1:8000/auth/callback"


def id_token(**claims: Any) -> str:
    def part(data: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'RS256'})}.{part(claims)}.signature"


class FakeOpenAi:
    """auth.openai.com: its sign-in settings, the code swap and revoking a token."""

    def __init__(self) -> None:
        self.forms: list[tuple[str, dict[str, str]]] = []
        self.nonce = ""
        self.token_status = 200
        self.scope = cs.SCOPES
        self.discovery: dict[str, str] = dict(DISCOVERY)
        self.claims: dict[str, Any] = {}

    def __call__(self, url: str, form: dict[str, str] | None) -> tuple[int, Any]:
        if form is None:
            return 200, self.discovery
        self.forms.append((url, form))
        if url.endswith("/revoke"):
            return 200, {}
        if self.token_status != 200:
            return self.token_status, {"error": "invalid_grant"}
        token = id_token(
            **{
                "iss": cs.ISSUER,
                "aud": [form["client_id"]],
                "sub": "user-1",
                "email": "larry@example.com",
                "name": "Larry",
                "nonce": self.nonce,
                "exp": NOW + 3600,
                **self.claims,
            }
        )
        return 200, {
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": self.scope,
            "id_token": token,
        }


@pytest.fixture
def openai() -> FakeOpenAi:
    return FakeOpenAi()


@pytest.fixture
def signin(tmp_path: Path, openai: FakeOpenAi) -> ChatGptSignIn:
    return ChatGptSignIn(tmp_path, http=openai, clock=lambda: NOW)


def authorize(signin: ChatGptSignIn, openai: FakeOpenAi) -> dict[str, str]:
    url = signin.start(REDIRECT)
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    openai.nonce = query["nonce"]
    return query


def test_signing_in_keeps_the_account_and_its_tokens_on_the_server(
    signin: ChatGptSignIn, openai: FakeOpenAi, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    assert signin.status() == {"connected": False, "email": "", "name": "", "plan_usage": False}
    query = authorize(signin, openai)
    assert query["client_id"] == cs.REGISTER_CLIENT
    assert query["agent_name_hint"] == "ImageSkinForLLM"
    assert query["redirect_uri"] == REDIRECT
    assert cs.PLAN_SCOPE in query["scope"].split()

    status = signin.finish({"state": query["state"], "code": "c1", "client_id": "app-123"})

    assert status == {
        "connected": True,
        "email": "larry@example.com",
        "name": "Larry",
        "plan_usage": True,
    }
    url, form = openai.forms[-1]
    assert url == DISCOVERY["token_endpoint"]
    assert form["client_id"] == "app-123"
    assert form["redirect_uri"] == REDIRECT
    # PKCE: the verifier sent now matches the challenge sent to start.
    challenge = hashlib.sha256(form["code_verifier"].encode()).digest()
    assert base64.urlsafe_b64encode(challenge).rstrip(b"=").decode() == query["code_challenge"]
    saved = json.loads((tmp_path / cs.FILENAME).read_text())
    assert saved["client_id"] == "app-123"
    assert saved["connection"]["refresh_token"] == "refresh-secret"
    assert "Signed in with ChatGPT" in caplog.text
    assert "secret" not in caplog.text


def test_signing_in_again_uses_the_registered_app(
    signin: ChatGptSignIn, openai: FakeOpenAi
) -> None:
    first = authorize(signin, openai)
    signin.finish({"state": first["state"], "code": "c1", "client_id": "app-123"})
    again = authorize(signin, openai)
    assert again["client_id"] == "app-123"
    assert "agent_name_hint" not in again
    signin.finish({"state": again["state"], "code": "c2"})
    assert openai.forms[-1][1]["client_id"] == "app-123"


def test_a_sign_in_without_plan_usage_says_so(signin: ChatGptSignIn, openai: FakeOpenAi) -> None:
    openai.scope = "openid profile email offline_access"
    query = authorize(signin, openai)
    status = signin.finish({"state": query["state"], "code": "c1", "client_id": "app-1"})
    assert status["connected"] and not status["plan_usage"]


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ({"state": "unknown", "code": "c"}, "expired or was already used"),
        ({"error": "access_denied"}, "cancelled"),
        ({"error": "server_error"}, r"refused the sign-in \(server_error\)"),
        ({"code": "c"}, "didn't finish registering"),
        ({"code": "c", "client_id": cs.REGISTER_CLIENT}, "didn't finish registering"),
        ({"client_id": "app-1"}, "didn't finish registering"),
    ],
)
def test_a_failed_sign_in_says_why(
    signin: ChatGptSignIn, openai: FakeOpenAi, query: dict[str, str], message: str
) -> None:
    state = authorize(signin, openai)["state"]
    with pytest.raises(SignInError, match=message):
        signin.finish({"state": state, **query})
    assert not signin.status()["connected"]


@pytest.mark.parametrize(
    "claims",
    [
        {"nonce": "other"},
        {"iss": "https://evil.example"},
        {"aud": "another-app"},
        {"exp": 0},
        {"sub": ""},
    ],
)
def test_an_identity_that_does_not_match_is_refused(
    signin: ChatGptSignIn, openai: FakeOpenAi, claims: dict[str, Any]
) -> None:
    query = authorize(signin, openai)
    openai.claims = claims
    with pytest.raises(SignInError, match="didn't match"):
        signin.finish({"state": query["state"], "code": "c", "client_id": "app-1"})
    assert not signin.status()["connected"]


def test_a_refused_code_keeps_the_registration(
    signin: ChatGptSignIn, openai: FakeOpenAi, caplog: pytest.LogCaptureFixture
) -> None:
    openai.token_status = 400
    query = authorize(signin, openai)
    with pytest.raises(SignInError, match="didn't accept"):
        signin.finish({"state": query["state"], "code": "c", "client_id": "app-9"})
    assert "ChatGPT sign-in code refused" in caplog.text
    assert authorize(signin, openai)["client_id"] == "app-9"


def test_a_sign_in_is_used_once_and_expires(tmp_path: Path, openai: FakeOpenAi) -> None:
    now = [NOW]
    signin = ChatGptSignIn(tmp_path, http=openai, clock=lambda: now[0])
    query = authorize(signin, openai)
    now[0] += cs.PENDING_S
    with pytest.raises(SignInError, match="expired"):
        signin.finish({"state": query["state"], "code": "c", "client_id": "a"})
    # Only the latest few are kept.
    states = [authorize(signin, openai)["state"] for _ in range(cs.MOST_PENDING + 1)]
    with pytest.raises(SignInError, match="expired"):
        signin.finish({"state": states[0], "code": "c", "client_id": "a"})


def test_sign_in_settings_that_cannot_be_trusted_are_refused(
    signin: ChatGptSignIn, openai: FakeOpenAi
) -> None:
    openai.discovery["token_endpoint"] = "https://evil.example/token"
    with pytest.raises(SignInError, match="can't be reached"):
        signin.start(REDIRECT)


def test_disconnecting_revokes_and_keeps_the_registration(
    signin: ChatGptSignIn, openai: FakeOpenAi, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    query = authorize(signin, openai)
    signin.finish({"state": query["state"], "code": "c", "client_id": "app-1"})
    assert signin.sign_out()["connected"] is False
    url, form = openai.forms[-1]
    assert url == DISCOVERY["revocation_endpoint"]
    assert form == {
        "token": "refresh-secret",
        "token_type_hint": "refresh_token",
        "client_id": "app-1",
    }
    assert "Disconnected ChatGPT" in caplog.text
    assert authorize(signin, openai)["client_id"] == "app-1"


def test_a_broken_file_reads_as_not_connected(tmp_path: Path, openai: FakeOpenAi) -> None:
    (tmp_path / cs.FILENAME).write_text("[not json")
    assert ChatGptSignIn(tmp_path, http=openai).status()["connected"] is False


def test_an_unreadable_identity_is_refused() -> None:
    with pytest.raises(SignInError, match="can't be read"):
        cs.claims("no-dots")
    with pytest.raises(SignInError, match="can't be read"):
        cs.claims("a.W10.b")  # a list, not an object


@pytest.fixture
def app(tmp_path: Path, signin: ChatGptSignIn) -> TestClient:
    return TestClient(
        create_app(
            tmp_path,
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=lambda photo, text, output: None,
            chatgpt=signin,
        ),
        base_url="http://127.0.0.1:8000",
        follow_redirects=False,
    )


def test_the_browser_signs_in_and_comes_back_to_settings(
    app: TestClient, openai: FakeOpenAi
) -> None:
    assert app.get("/api/chatgpt").json()["connected"] is False
    sent = app.get("/api/chatgpt/sign-in")
    assert sent.status_code == 303
    to = urllib.parse.urlsplit(sent.headers["location"])
    assert f"{to.scheme}://{to.netloc}{to.path}" == DISCOVERY["authorization_endpoint"]
    query = dict(urllib.parse.parse_qsl(to.query))
    assert query["redirect_uri"] == REDIRECT
    openai.nonce = query["nonce"]

    back = app.get(
        "/auth/callback", params={"state": query["state"], "code": "c", "client_id": "app-1"}
    )

    assert back.status_code == 303
    assert back.headers["location"] == "/#/settings"
    assert app.get("/api/chatgpt").json()["email"] == "larry@example.com"
    assert app.post("/api/chatgpt/sign-out").json()["connected"] is False


def test_a_failed_sign_in_shows_why_with_the_way_back(app: TestClient, openai: FakeOpenAi) -> None:
    back = app.get("/auth/callback", params={"error": "x", "state": "<b>"})
    assert back.status_code == 400
    assert "expired or was already used" in back.text
    assert 'href="/#/settings"' in back.text
    openai.discovery["issuer"] = "https://evil.example"
    assert app.get("/api/chatgpt/sign-in").status_code == 502


def test_openai_is_asked_over_http() -> None:
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._send(200, b'{"issuer": "x"}')

        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            self._send(400 if b"bad" in body else 200, b"" if b"empty" in body else b'{"ok": 1}')

        def _send(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/"
    try:
        assert cs._http(url, None) == (200, {"issuer": "x"})
        assert cs._http(url, {"a": "b"}) == (200, {"ok": 1})
        assert cs._http(url, {"a": "bad"}) == (400, {"ok": 1})
        assert cs._http(url, {"a": "bad empty"}) == (400, {})
        with pytest.raises(SignInError, match="can't be reached"):
            cs._http("http://127.0.0.1:1/", None)  # nothing listens there
    finally:
        server.shutdown()


def test_disconnecting_when_openai_cannot_be_reached_still_forgets_it(
    signin: ChatGptSignIn, openai: FakeOpenAi, caplog: pytest.LogCaptureFixture
) -> None:
    query = authorize(signin, openai)
    signin.finish({"state": query["state"], "code": "c", "client_id": "app-1"})
    signin._endpoints = None
    openai.discovery["issuer"] = "https://evil.example"
    assert signin.sign_out()["connected"] is False
    assert "Could not end the ChatGPT sign-in" in caplog.text
