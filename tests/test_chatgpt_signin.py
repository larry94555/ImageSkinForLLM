"""Sign in with ChatGPT on the Settings page (roadmap R43)."""

import base64
import hashlib
import json
import logging
import urllib.parse
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.hashes import SHA256
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
    "jwks_uri": f"{cs.ISSUER}/.well-known/jwks.json",
}
NOW = 1_800_000_000.0
REDIRECT = "http://127.0.0.1:8000/auth/callback"


# OpenAI's signing key, and another that isn't OpenAI's.
OPENAI_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def jwk(key: rsa.RSAPrivateKey, kid: str) -> dict[str, str]:
    numbers = key.public_key().public_numbers()

    def as_bytes(n: int) -> bytes:
        return n.to_bytes((n.bit_length() + 7) // 8, "big")

    return {"kty": "RSA", "kid": kid, "n": b64(as_bytes(numbers.n)), "e": b64(as_bytes(numbers.e))}


def id_token(
    claims: dict[str, Any],
    key: rsa.RSAPrivateKey = OPENAI_KEY,
    header: dict[str, Any] | None = None,
) -> str:
    def part(data: dict[str, Any]) -> str:
        return b64(json.dumps(data).encode())

    signed = f"{part(header or {'alg': 'RS256', 'kid': 'k1'})}.{part(claims)}"
    return f"{signed}.{b64(key.sign(signed.encode(), PKCS1v15(), SHA256()))}"


class FakeOpenAi:
    """auth.openai.com: its sign-in settings, the code swap and revoking a token."""

    def __init__(self) -> None:
        self.forms: list[tuple[str, dict[str, str]]] = []
        self.nonce = ""
        self.token_status = 200
        self.scope = cs.SCOPES
        self.discovery: dict[str, str] = dict(DISCOVERY)
        self.claims: dict[str, Any] = {}
        self.key = OPENAI_KEY
        self.header: dict[str, Any] | None = None
        self.jwks_reads = 0
        self.revoke_results: list[int] = []  # statuses to answer revocations with; 0: unreachable
        self.sleeps: list[float] = []

    def __call__(self, url: str, form: dict[str, str] | None) -> tuple[int, Any]:
        if form is None and url == DISCOVERY["jwks_uri"]:
            self.jwks_reads += 1
            return 200, {"keys": [jwk(OPENAI_KEY, "k1")]}
        if form is None:
            return 200, self.discovery
        self.forms.append((url, form))
        if url.endswith("/revoke"):
            status = self.revoke_results.pop(0) if self.revoke_results else 200
            if not status:
                raise SignInError("ChatGPT's sign-in can't be reached right now. Try again.")
            return status, {}
        if self.token_status != 200:
            return self.token_status, {"error": "invalid_grant"}
        claims = {
            "iss": cs.ISSUER,
            "aud": [form["client_id"]],
            "sub": "user-1",
            "email": "larry@example.com",
            "name": "Larry",
            "nonce": self.nonce,
            "exp": NOW + 3600,
            **self.claims,
        }
        token = id_token(claims, self.key, self.header)
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
    return ChatGptSignIn(tmp_path, http=openai, clock=lambda: NOW, sleep=openai.sleeps.append)


def authorize(signin: ChatGptSignIn, openai: FakeOpenAi) -> dict[str, str]:
    url = signin.start(REDIRECT)
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    openai.nonce = query["nonce"]
    return query


def test_signing_in_keeps_the_account_and_its_tokens_on_the_server(
    signin: ChatGptSignIn, openai: FakeOpenAi, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    assert signin.status() == {
        "connected": False,
        "email": "",
        "name": "",
        "plan_usage": False,
        "registered_email": "",
        "label": "",
        "accounts": [],
    }
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
        "registered_email": "larry@example.com",
        "label": "larry@example.com",
        "accounts": [],
    }
    url, form = openai.forms[-1]
    assert url == DISCOVERY["token_endpoint"]
    assert form["client_id"] == "app-123"
    assert form["redirect_uri"] == REDIRECT
    # PKCE: the verifier sent now matches the challenge sent to start.
    challenge = hashlib.sha256(form["code_verifier"].encode()).digest()
    assert base64.urlsafe_b64encode(challenge).rstrip(b"=").decode() == query["code_challenge"]
    saved = json.loads((tmp_path / cs.FILENAME).read_text())
    [registration] = saved["registrations"]
    assert {k: registration[k] for k in ("client_id", "subject", "email", "name")} == {
        "client_id": "app-123",
        "subject": "user-1",
        "email": "larry@example.com",
        "name": "Larry",
    }
    assert registration["id_token"].count(".") == 2
    assert registration["credentials"]["refresh_token"] == "refresh-secret"
    assert registration["credentials"]["expires_at"] == NOW + 3600
    assert saved["active"] == "app-123"
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
    # OpenAI's signing keys are read once and kept.
    assert openai.jwks_reads == 1


def test_every_sign_in_sends_the_same_host_id(
    signin: ChatGptSignIn, openai: FakeOpenAi, tmp_path: Path
) -> None:
    first = authorize(signin, openai)
    assert first["ext_agent_host_id"].startswith("urn:uuid:")
    signin.finish({"state": first["state"], "code": "c1", "client_id": "app-123"})
    signin.sign_out()
    returning = authorize(signin, openai)
    assert returning["ext_agent_host_id"] == first["ext_agent_host_id"]
    # A new ChatGptSignIn (the app restarted) reads it back from chatgpt.json.
    restarted = ChatGptSignIn(tmp_path, http=openai, clock=lambda: NOW)
    assert authorize(restarted, openai)["ext_agent_host_id"] == first["ext_agent_host_id"]


def test_a_returning_sign_in_must_be_the_registered_account(
    signin: ChatGptSignIn, openai: FakeOpenAi, tmp_path: Path
) -> None:
    first = authorize(signin, openai)
    signin.finish({"state": first["state"], "code": "c1", "client_id": "app-123"})
    signin.sign_out()
    assert signin.status()["registered_email"] == "larry@example.com"
    again = authorize(signin, openai)
    assert again["login_hint"] == "larry@example.com"
    # Disconnect forgot the ID token, so it isn't sent as a hint.
    assert again["client_id"] == "app-123"
    assert "id_token_hint" not in again
    assert json.loads((tmp_path / cs.FILENAME).read_text())["registrations"][0]["id_token"] == ""
    before = (tmp_path / cs.FILENAME).read_bytes()
    openai.claims = {"sub": "someone-else", "email": "other@example.com"}
    with pytest.raises(SignInError, match="different ChatGPT account from larry@example.com"):
        signin.finish({"state": again["state"], "code": "c2"})
    assert (tmp_path / cs.FILENAME).read_bytes() == before


def test_another_account_registers_the_app_anew(
    signin: ChatGptSignIn, openai: FakeOpenAi, tmp_path: Path
) -> None:
    first = authorize(signin, openai)
    signin.finish({"state": first["state"], "code": "c1", "client_id": "app-123"})
    signin.sign_out()
    url = signin.start(REDIRECT, another=True)
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    assert query["client_id"] == cs.REGISTER_CLIENT
    assert "login_hint" not in query
    assert query["ext_agent_host_id"] == first["ext_agent_host_id"]
    openai.nonce = query["nonce"]
    openai.claims = {"sub": "user-2", "email": "second@example.com"}
    status = signin.finish({"state": query["state"], "code": "c2", "client_id": "app-456"})
    assert status["email"] == status["registered_email"] == "second@example.com"
    # The first account's registration is kept, and can be signed in as again.
    assert status["accounts"] == [
        {
            "id": "app-123",
            "email": "larry@example.com",
            "label": "larry@example.com",
            "connected": False,
        }
    ]
    saved = json.loads((tmp_path / cs.FILENAME).read_text())
    assert [r["subject"] for r in saved["registrations"]] == ["user-1", "user-2"]
    assert saved["active"] == "app-456"
    signin.sign_out()
    url = signin.start(REDIRECT, account="app-123")
    back = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    assert (back["client_id"], back["login_hint"]) == ("app-123", "larry@example.com")
    openai.nonce, openai.claims = back["nonce"], {}
    status = signin.finish({"state": back["state"], "code": "c3"})
    assert status["email"] == "larry@example.com"
    assert status["accounts"] == [
        {
            "id": "app-456",
            "email": "second@example.com",
            "label": "second@example.com",
            "connected": False,
        }
    ]


def test_switching_accounts_keeps_each_accounts_own_credentials(
    signin: ChatGptSignIn, openai: FakeOpenAi, tmp_path: Path
) -> None:
    def saved() -> dict[str, dict[str, Any]]:
        data = json.loads((tmp_path / cs.FILENAME).read_text())
        return {r["client_id"]: r for r in data["registrations"]}

    first = authorize(signin, openai)
    signin.finish({"state": first["state"], "code": "c1", "client_id": "app-1"})
    kept = saved()["app-1"]
    # Switch to a second account while the first is still connected.
    url = signin.start(REDIRECT, another=True)
    second = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    openai.nonce, openai.claims = second["nonce"], {"sub": "user-2", "email": "b@example.com"}
    status = signin.finish({"state": second["state"], "code": "c2", "client_id": "app-2"})
    assert (status["email"], status["connected"]) == ("b@example.com", True)
    assert status["accounts"] == [
        {
            "id": "app-1",
            "email": "larry@example.com",
            "label": "larry@example.com",
            "connected": True,
        }
    ]
    assert saved()["app-1"] == kept  # its refresh, access and ID tokens are untouched
    assert "revoke" not in " ".join(url for url, _ in openai.forms)
    # Back to the first with no sign-in: it is still connected.
    forms = len(openai.forms)
    status = signin.use("app-1")
    assert (status["email"], status["connected"]) == ("larry@example.com", True)
    assert len(openai.forms) == forms
    # Signing in to it again continues its own registration, with its retained ID token.
    url = signin.start(REDIRECT)
    again = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    assert (again["client_id"], again["id_token_hint"]) == ("app-1", kept["id_token"])
    openai.nonce, openai.claims = again["nonce"], {}
    signin.finish({"state": again["state"], "code": "c3"})
    assert saved()["app-1"]["subject"] == "user-1"
    assert saved()["app-2"]["credentials"]["refresh_token"] == "refresh-secret"
    # Disconnect ends only the account in use.
    signin.sign_out()
    assert saved()["app-1"]["credentials"] is None
    assert saved()["app-1"]["id_token"] == ""
    assert saved()["app-1"]["email"] == "larry@example.com"
    assert saved()["app-2"]["credentials"]
    assert signin.use("app-2")["connected"] is True


def test_accounts_with_the_same_email_keep_distinct_labels(
    signin: ChatGptSignIn, openai: FakeOpenAi, tmp_path: Path
) -> None:
    # One ChatGPT email registered twice, as for two workspaces.
    for client_id, subject in (("app-1", "user-1"), ("app-2", "user-2"), ("app-3", "user-3")):
        url = signin.start(REDIRECT, another=True)
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        openai.nonce, openai.claims = query["nonce"], {"sub": subject}
        signin.finish({"state": query["state"], "code": "c", "client_id": client_id})
    status = signin.status()
    shown = [status["label"]] + [a["label"] for a in status["accounts"]]
    assert shown == ["larry@example.com (3)", "larry@example.com", "larry@example.com (2)"]
    # The same after a reload, after signing in again, and after a switch.
    reloaded = ChatGptSignIn(tmp_path, http=openai, clock=lambda: NOW)
    assert reloaded.status() == status
    url = signin.start(REDIRECT, account="app-1")
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    openai.nonce, openai.claims = query["nonce"], {"sub": "user-1"}
    assert signin.finish({"state": query["state"], "code": "c"})["label"] == "larry@example.com"
    labels = {a["id"]: a["label"] for a in signin.use("app-2")["accounts"]}
    assert labels == {"app-1": "larry@example.com", "app-3": "larry@example.com (3)"}


def test_a_registration_saved_without_a_label_gets_a_distinct_one(
    tmp_path: Path, openai: FakeOpenAi
) -> None:
    same = {"email": "a@example.com", "credentials": None}
    registrations = [{"client_id": "app-1", **same}, {"client_id": "app-2", **same}]
    (tmp_path / cs.FILENAME).write_text(
        json.dumps({"registrations": registrations, "active": "app-2"})
    )
    status = ChatGptSignIn(tmp_path, http=openai).status()
    assert (status["label"], status["accounts"][0]["label"]) == (
        "a@example.com (2)",
        "a@example.com",
    )


def test_only_a_registered_account_can_be_used(signin: ChatGptSignIn) -> None:
    with pytest.raises(SignInError, match="isn't registered"):
        signin.use("app-unknown")


@pytest.mark.parametrize("failure", ["code", "signature", "nonce"])
def test_a_failed_switch_leaves_the_saved_sign_in_unchanged(
    signin: ChatGptSignIn, openai: FakeOpenAi, tmp_path: Path, failure: str
) -> None:
    first = authorize(signin, openai)
    signin.finish({"state": first["state"], "code": "c1", "client_id": "app-123"})
    before = (tmp_path / cs.FILENAME).read_bytes()
    url = signin.start(REDIRECT, another=True)
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    openai.nonce = "wrong" if failure == "nonce" else query["nonce"]
    openai.token_status = 400 if failure == "code" else 200
    openai.key = OTHER_KEY if failure == "signature" else OPENAI_KEY
    openai.claims = {"sub": "user-2"}
    with pytest.raises(SignInError):
        signin.finish({"state": query["state"], "code": "c2", "client_id": "app-456"})
    after = json.loads((tmp_path / cs.FILENAME).read_text())
    # A refused code keeps only the issued client ID, to try again with; no account changes.
    assert after.pop("provisional", None) == ("app-456" if failure == "code" else None)
    assert after == json.loads(before)


def test_two_sign_ins_finishing_out_of_order_keep_their_own_accounts(
    signin: ChatGptSignIn, openai: FakeOpenAi, tmp_path: Path
) -> None:
    def started(another: bool) -> dict[str, str]:
        url = signin.start(REDIRECT, another=another)
        return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))

    a, b = started(False), started(True)
    openai.nonce, openai.claims = b["nonce"], {"sub": "user-b", "email": "b@example.com"}
    signin.finish({"state": b["state"], "code": "cb", "client_id": "app-b"})
    openai.nonce, openai.claims = a["nonce"], {"sub": "user-a", "email": "a@example.com"}
    signin.finish({"state": a["state"], "code": "ca", "client_id": "app-a"})
    saved = json.loads((tmp_path / cs.FILENAME).read_text())
    pairs = {(r["client_id"], r["subject"]) for r in saved["registrations"]}
    assert pairs == {("app-a", "user-a"), ("app-b", "user-b")}
    assert saved["active"] == "app-a"
    assert all(r["credentials"] for r in saved["registrations"])


def test_allowing_the_plan_asks_for_consent_again(
    signin: ChatGptSignIn, openai: FakeOpenAi
) -> None:
    openai.scope = "openid profile email offline_access"
    first = authorize(signin, openai)
    assert "prompt" not in first
    assert not signin.finish({"state": first["state"], "code": "c1", "client_id": "app-1"})[
        "plan_usage"
    ]
    url = signin.start(REDIRECT, consent=True)
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    assert query["prompt"] == "consent"
    assert query["client_id"] == "app-1"
    assert cs.PLAN_SCOPE in query["scope"].split()
    assert "prompt" not in authorize(signin, openai)  # an ordinary returning sign-in


def test_a_returning_sign_in_for_another_app_is_refused(
    signin: ChatGptSignIn, openai: FakeOpenAi, tmp_path: Path
) -> None:
    first = authorize(signin, openai)
    signin.finish({"state": first["state"], "code": "c1", "client_id": "app-123"})
    forms = len(openai.forms)
    again = authorize(signin, openai)
    with pytest.raises(SignInError, match="didn't match"):
        signin.finish({"state": again["state"], "code": "c2", "client_id": "app-evil"})
    assert len(openai.forms) == forms  # the code was never swapped
    assert json.loads((tmp_path / cs.FILENAME).read_text())["active"] == "app-123"
    # The same client ID coming back is fine.
    again = authorize(signin, openai)
    signin.finish({"state": again["state"], "code": "c3", "client_id": "app-123"})
    assert signin.status()["connected"]


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


def test_a_refused_code_saves_no_registration(
    signin: ChatGptSignIn, openai: FakeOpenAi, caplog: pytest.LogCaptureFixture
) -> None:
    openai.token_status = 400
    query = authorize(signin, openai)
    with pytest.raises(SignInError, match="didn't accept"):
        signin.finish({"state": query["state"], "code": "c", "client_id": "app-9"})
    assert "ChatGPT sign-in code refused" in caplog.text
    assert signin.status()["registered_email"] == ""  # no account is saved


def test_a_refused_code_retries_with_the_issued_client_id(
    signin: ChatGptSignIn, openai: FakeOpenAi, tmp_path: Path
) -> None:
    def saved() -> dict[str, Any]:
        return dict(json.loads((tmp_path / cs.FILENAME).read_text()))

    first = authorize(signin, openai)
    signin.finish({"state": first["state"], "code": "c1", "client_id": "app-1"})
    kept = saved()["registrations"]
    # A new registration's callback comes with client ID app-123, but its code is refused.
    url = signin.start(REDIRECT, another=True)
    new = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    assert new["client_id"] == cs.REGISTER_CLIENT
    openai.token_status = 400
    with pytest.raises(SignInError, match="didn't accept"):
        signin.finish({"state": new["state"], "code": "c2", "client_id": "app-123"})
    assert (saved()["registrations"], saved()["active"]) == (kept, "app-1")
    assert signin.status()["email"] == "larry@example.com"
    # The retry authorizes with the issued app-123, with fresh state, nonce and PKCE.
    url = signin.start(REDIRECT, another=True)
    retry = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    assert retry["client_id"] == "app-123"
    assert "agent_name_hint" not in retry  # only for dynamic_agent_client
    assert "id_token_hint" not in retry
    for fresh in ("state", "nonce", "code_challenge"):
        assert retry[fresh] != new[fresh]
    # A second refusal keeps it too; then a sign-in that checks out makes it an account.
    with pytest.raises(SignInError):
        signin.finish({"state": retry["state"], "code": "c3", "client_id": "app-123"})
    assert saved()["provisional"] == "app-123"
    url = signin.start(REDIRECT, another=True)
    retry = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    openai.token_status = 200
    openai.nonce, openai.claims = retry["nonce"], {"sub": "user-2", "email": "b@example.com"}
    status = signin.finish({"state": retry["state"], "code": "c4"})
    assert (status["email"], openai.forms[-1][1]["client_id"]) == ("b@example.com", "app-123")
    assert "provisional" not in saved()
    assert saved()["registrations"][0] == kept[0]


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
    out = signin.sign_out()
    assert (out["connected"], out["revoked"]) == (False, True)
    url, form = openai.forms[-1]
    assert url == DISCOVERY["revocation_endpoint"]
    assert form == {
        "token": "refresh-secret",
        "token_type_hint": "refresh_token",
        "client_id": "app-1",
    }
    assert "Disconnected ChatGPT" in caplog.text
    assert authorize(signin, openai)["client_id"] == "app-1"


def test_disconnecting_tries_again_after_a_passing_failure(
    signin: ChatGptSignIn, openai: FakeOpenAi
) -> None:
    query = authorize(signin, openai)
    signin.finish({"state": query["state"], "code": "c", "client_id": "app-1"})
    openai.revoke_results = [0, 503]  # unreachable, then a 5xx, then confirmed
    out = signin.sign_out()
    assert (out["connected"], out["revoked"]) == (False, True)
    revokes = [form for url, form in openai.forms if url.endswith("/revoke")]
    assert [form["token"] for form in revokes] == ["refresh-secret"] * 3
    assert openai.sleeps == [1.0, 2.0]


def test_disconnecting_forgets_the_tokens_once_the_tries_run_out(
    tmp_path: Path, signin: ChatGptSignIn, openai: FakeOpenAi, caplog: pytest.LogCaptureFixture
) -> None:
    query = authorize(signin, openai)
    signin.finish({"state": query["state"], "code": "c", "client_id": "app-1"})
    openai.revoke_results = [500, 0, 502]
    out = signin.sign_out()
    assert (out["connected"], out["revoked"]) == (False, False)
    assert len([url for url, _ in openai.forms if url.endswith("/revoke")]) == cs.REVOKE_TRIES
    assert "secret" not in (tmp_path / cs.FILENAME).read_text()
    assert "Could not end the ChatGPT sign-in" in caplog.text


def test_a_refused_revocation_is_not_tried_again(signin: ChatGptSignIn, openai: FakeOpenAi) -> None:
    query = authorize(signin, openai)
    signin.finish({"state": query["state"], "code": "c", "client_id": "app-1"})
    openai.revoke_results = [400]
    out = signin.sign_out()
    assert (out["connected"], out["revoked"]) == (False, False)
    assert len([url for url, _ in openai.forms if url.endswith("/revoke")]) == 1
    assert openai.sleeps == []


def test_disconnecting_keeps_a_sign_in_that_finished_meanwhile(
    signin: ChatGptSignIn, openai: FakeOpenAi
) -> None:
    query = authorize(signin, openai)
    signin.finish({"state": query["state"], "code": "c", "client_id": "app-1"})

    def sign_in_again(_: float) -> None:
        saved = json.loads(signin._path.read_text())
        saved["registrations"][0]["credentials"]["access_token"] = "newer-access"
        signin._path.write_text(json.dumps(saved))

    signin._sleep = sign_in_again
    openai.revoke_results = [503]
    assert signin.sign_out()["connected"] is True


def test_a_broken_file_reads_as_not_connected(tmp_path: Path, openai: FakeOpenAi) -> None:
    (tmp_path / cs.FILENAME).write_text("[not json")
    assert ChatGptSignIn(tmp_path, http=openai).status()["connected"] is False


def test_an_unreadable_identity_is_refused() -> None:
    def key(kid: str) -> dict[str, Any]:
        return jwk(OPENAI_KEY, kid)

    with pytest.raises(SignInError, match="can't be read"):
        cs.verified_claims("no-dots", key)
    with pytest.raises(SignInError, match="can't be read"):
        cs.verified_claims("e30.W10.c2ln", key)  # claims that are a list, not an object
    with pytest.raises(SignInError, match="can't be read"):
        cs.verified_claims("e30.!!.c2ln", key)


@pytest.mark.parametrize(
    ("key", "header"),
    [
        (OTHER_KEY, None),  # signed, but not by OpenAI
        (OPENAI_KEY, {"alg": "HS256", "kid": "k1"}),
        (OPENAI_KEY, {"alg": "none", "kid": "k1"}),
        (OPENAI_KEY, {"alg": "RS256", "kid": "unknown"}),
    ],
)
def test_an_identity_not_signed_by_openai_is_refused(
    signin: ChatGptSignIn,
    openai: FakeOpenAi,
    caplog: pytest.LogCaptureFixture,
    key: rsa.RSAPrivateKey,
    header: dict[str, Any] | None,
) -> None:
    openai.key, openai.header = key, header
    query = authorize(signin, openai)
    with pytest.raises(SignInError, match="isn't signed by OpenAI"):
        signin.finish({"state": query["state"], "code": "c", "client_id": "app-1"})
    assert not signin.status()["connected"]


def test_a_changed_signature_is_refused() -> None:
    token = id_token({"sub": "user-1"})
    head, body, signature = token.split(".")
    forged = b64(json.dumps({"sub": "someone-else"}).encode())
    with pytest.raises(SignInError, match="isn't signed by OpenAI"):
        cs.verified_claims(f"{head}.{forged}.{signature}", lambda kid: jwk(OPENAI_KEY, kid))
    assert cs.verified_claims(token, lambda kid: jwk(OPENAI_KEY, kid)) == {"sub": "user-1"}


def test_signing_keys_that_cannot_be_read_stop_the_sign_in(
    signin: ChatGptSignIn, openai: FakeOpenAi
) -> None:
    query = authorize(signin, openai)
    real = openai.__call__

    def no_keys(url: str, form: dict[str, str] | None) -> tuple[int, Any]:
        return (503, {}) if url == DISCOVERY["jwks_uri"] else real(url, form)

    signin._http = no_keys
    with pytest.raises(SignInError, match="can't be reached"):
        signin.finish({"state": query["state"], "code": "c", "client_id": "app-1"})


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
    threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    ).start()
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
    status = signin.sign_out()
    assert status["connected"] is False
    assert status["revoked"] is False
    assert "Could not end the ChatGPT sign-in" in caplog.text


def test_the_sign_in_link_can_ask_for_consent_or_another_account(app: TestClient) -> None:
    def query(path: str) -> dict[str, str]:
        location = app.get(path).headers["location"]
        return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(location).query))

    assert query("/api/chatgpt/sign-in?consent=true")["prompt"] == "consent"
    assert "prompt" not in query("/api/chatgpt/sign-in")
    assert query("/api/chatgpt/sign-in?another=true")["client_id"] == cs.REGISTER_CLIENT


def test_the_page_can_switch_to_a_registered_account(
    app: TestClient, signin: ChatGptSignIn, openai: FakeOpenAi
) -> None:
    query = authorize(signin, openai)
    signin.finish({"state": query["state"], "code": "c", "client_id": "app-1"})
    response = app.post("/api/chatgpt/use", json={"account": "app-1"})
    assert (response.status_code, response.json()["connected"]) == (200, True)
    assert app.post("/api/chatgpt/use", json={"account": "nope"}).status_code == 404


def test_the_sign_in_link_can_name_an_account(app: TestClient, signin: ChatGptSignIn) -> None:
    location = app.get("/api/chatgpt/sign-in?account=unknown").headers["location"]
    # An account that isn't registered falls back to the active one (none yet: register).
    assert (
        dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(location).query))["client_id"]
        == cs.REGISTER_CLIENT
    )


# Moving the sign-in to a self-hosted server (OpenAI's "Self-hosted VMs" guide; review on PR #120).


def signed_in(signin: ChatGptSignIn, openai: FakeOpenAi) -> None:
    query = authorize(signin, openai)
    signin.finish({"state": query["state"], "code": "c1", "client_id": "app-123"})


def exported(signin: ChatGptSignIn) -> dict[str, Any]:
    kept: list[dict[str, Any]] = []
    signin.export_active(kept.append)
    [transfer] = kept
    return transfer


def test_a_laptop_sign_in_moves_to_the_server_which_keeps_its_own_host_id(
    signin: ChatGptSignIn, openai: FakeOpenAi, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    signed_in(signin, openai)
    laptop_host = json.loads((tmp_path / cs.FILENAME).read_text())["host_id"]
    transfer = exported(signin)
    assert "host_id" not in json.dumps(transfer)
    # The laptop forgets its tokens, unrevoked, and keeps the registration to sign in again.
    assert not [f for f in openai.forms if f[0].endswith("/revoke")]
    laptop = json.loads((tmp_path / cs.FILENAME).read_text())
    assert laptop["registrations"][0]["credentials"] is None
    assert laptop["registrations"][0]["client_id"] == "app-123"
    assert signin.status()["connected"] is False

    server_home = tmp_path / "server"
    server = ChatGptSignIn(server_home, http=openai, clock=lambda: NOW)
    server_host = server._host_id()  # made before the import, as the guide says
    status = server.import_registration(json.loads(json.dumps(transfer)))

    assert status["connected"] and status["plan_usage"]
    assert status["label"] == "larry@example.com"
    saved = json.loads((server_home / cs.FILENAME).read_text())
    assert saved["host_id"] == server_host != laptop_host
    assert saved["active"] == "app-123"
    # The server renews the tokens itself, with the laptop's client ID.
    assert server.access_token(renew=True) == "access-secret"
    url, form = openai.forms[-1]
    assert url == DISCOVERY["token_endpoint"]
    assert form == {**form, "grant_type": "refresh_token", "client_id": "app-123"}
    assert "Exported the ChatGPT sign-in" in caplog.text
    assert "Imported the ChatGPT sign-in" in caplog.text
    assert "secret" not in caplog.text


def test_a_server_with_no_host_id_gets_its_own(
    signin: ChatGptSignIn, openai: FakeOpenAi, tmp_path: Path
) -> None:
    signed_in(signin, openai)
    transfer = exported(signin)
    server = ChatGptSignIn(tmp_path / "server", http=openai, clock=lambda: NOW)
    server.import_registration(transfer)
    laptop_host = json.loads((tmp_path / cs.FILENAME).read_text())["host_id"]
    server_host = json.loads((tmp_path / "server" / cs.FILENAME).read_text())["host_id"]
    assert server_host.startswith("urn:uuid:")
    assert server_host != laptop_host


def test_nothing_is_exported_before_signing_in(signin: ChatGptSignIn) -> None:
    kept: list[dict[str, Any]] = []
    with pytest.raises(SignInError, match="Sign in with ChatGPT on the Settings page here first"):
        signin.export_active(kept.append)
    assert kept == []


def test_the_laptop_keeps_its_tokens_when_the_export_cant_be_written(
    signin: ChatGptSignIn, openai: FakeOpenAi
) -> None:
    signed_in(signin, openai)

    def fail(_: dict[str, Any]) -> None:
        raise OSError("disk full")

    with pytest.raises(OSError):
        signin.export_active(fail)
    assert signin.status()["connected"] is True


@pytest.mark.parametrize(
    "spoil",
    [
        lambda t: "not a dict",
        lambda t: {**t, "kind": "something else"},
        lambda t: {**t, "registration": "not a dict"},
        lambda t: {**t, "registration": {**t["registration"], "client_id": "bad id!"}},
        lambda t: {**t, "registration": {**t["registration"], "credentials": None}},
        lambda t: {**t, "registration": {**t["registration"], "subject": "user-2"}},
        lambda t: {**t, "registration": {**t["registration"], "client_id": "app-999"}},
    ],
)
def test_a_file_that_isnt_a_genuine_export_is_refused(
    signin: ChatGptSignIn, openai: FakeOpenAi, tmp_path: Path, spoil: Any
) -> None:
    signed_in(signin, openai)
    transfer = exported(signin)
    server = ChatGptSignIn(tmp_path / "server", http=openai, clock=lambda: NOW)
    with pytest.raises(SignInError, match="isn't a ChatGPT sign-in made by"):
        server.import_registration(spoil(transfer))
    assert server.status()["connected"] is False


def test_an_id_token_not_signed_by_openai_is_refused(
    signin: ChatGptSignIn, openai: FakeOpenAi, tmp_path: Path
) -> None:
    signed_in(signin, openai)
    transfer = exported(signin)
    claims = {"iss": cs.ISSUER, "aud": ["app-123"], "sub": "user-1", "exp": NOW + 3600}
    forged = {**transfer["registration"], "id_token": id_token(claims, OTHER_KEY)}
    server = ChatGptSignIn(tmp_path / "server", http=openai, clock=lambda: NOW)
    with pytest.raises(SignInError):
        server.import_registration({**transfer, "registration": forged})
    assert not (tmp_path / "server" / cs.FILENAME).exists() or not server.status()["connected"]


def test_an_import_sits_beside_the_servers_other_accounts(
    signin: ChatGptSignIn, openai: FakeOpenAi, tmp_path: Path
) -> None:
    signed_in(signin, openai)
    transfer = exported(signin)
    server_home = tmp_path / "server"
    server_home.mkdir()
    other = {"client_id": "app-555", "label": "larry@example.com", "email": "larry@example.com"}
    (server_home / cs.FILENAME).write_text(
        json.dumps({"host_id": "urn:uuid:server", "registrations": [other], "active": "app-555"})
    )
    server = ChatGptSignIn(server_home, http=openai, clock=lambda: NOW)
    status = server.import_registration(transfer)
    assert status["label"] == "larry@example.com (2)"
    saved = json.loads((server_home / cs.FILENAME).read_text())
    assert saved["host_id"] == "urn:uuid:server"
    assert [r["client_id"] for r in saved["registrations"]] == ["app-555", "app-123"]
    assert saved["registrations"][0] == other
    # Importing it again replaces it, with the same label.
    signed_in(signin, openai)
    assert server.import_registration(exported(signin))["label"] == "larry@example.com (2)"
