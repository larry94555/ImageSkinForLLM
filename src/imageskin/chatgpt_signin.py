"""Sign in with ChatGPT on the Settings page (roadmap R43, feature item 29).

OpenAI lets an open-source app that runs on the user's own machine use the user's ChatGPT plan
in place of an API key, through "Sign in with ChatGPT" (an OAuth sign-in with PKCE). This app
qualifies while it runs locally. The browser is sent to auth.openai.com, which sends it back to
this app's own address on 127.0.0.1 with a one-time code; the server swaps the code for tokens
and keeps them in chatgpt.json in the app's home folder, readable by the owner only where the
system allows. A token is never logged or sent to the browser: the page is told only which
account is connected and whether it allowed plan usage. R43a makes that plan answer the chat.

The first sign-in registers this app with OpenAI and gets back a client ID, bound to the ChatGPT
account that signed in. Both are kept, even after Disconnect, so signing in again reuses that
registration; a returning sign-in that comes back with another client ID, or as another account,
is refused. "Use another ChatGPT account" starts a new registration instead, and after a sign-in
that didn't allow plan use, "Allow use of my plan" asks for consent again. Every sign-in also
sends one host ID, made once and kept, so OpenAI sees the same computer each time. The ID token
is checked against OpenAI's published keys before any of its claims are used. Claude's and
Grok's subscriptions offer no supported way for another app to use them (decided before R43).
"""

import base64
import hashlib
import json
import logging
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from cryptography.hazmat.primitives.hashes import SHA256

from imageskin.llm_choice import write_owner_only

logger = logging.getLogger(__name__)

FILENAME = "chatgpt.json"
ISSUER = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
# Who the person is, a token that renews, and use of their plan for this app's requests.
PLAN_SCOPE = "chatgpt.tokens.use.direct"
SCOPES = f"openid profile email offline_access resource.invoke {PLAN_SCOPE}"
CALLBACK_PATH = "/auth/callback"
# The client ID asked with before this app is registered; OpenAI returns the real one.
REGISTER_CLIENT = "dynamic_agent_client"
APP_NAME = "ImageSkinForLLM"
CLIENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,200}$")
# A sign-in not finished in this long is dropped, and only this many are kept at once.
PENDING_S = 600
MOST_PENDING = 5

# POST a form, or GET when the form is None: the status and the decoded JSON.
Http = Callable[[str, dict[str, str] | None], tuple[int, Any]]


class SignInError(Exception):
    """Why signing in with ChatGPT failed, in plain words."""


@dataclass(frozen=True)
class _Pending:
    verifier: str
    nonce: str
    redirect_uri: str
    started: float
    # The client ID it was started with, when this app was already registered.
    client_id: str = ""


def _http(url: str, form: dict[str, str] | None) -> tuple[int, Any]:
    data = None if form is None else urllib.parse.urlencode(form).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except (OSError, ValueError) as e:
        logger.error("Could not reach ChatGPT's sign-in", extra={"url": url, "error": str(e)})
        raise SignInError("ChatGPT's sign-in can't be reached right now. Try again.") from e


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


UNREADABLE = "ChatGPT sent an identity that can't be read. Sign in again."
NOT_SIGNED = "ChatGPT's identity isn't signed by OpenAI. Sign in again."


def _json_part(part: str) -> dict[str, Any]:
    try:
        data = json.loads(_unb64(part))
    except ValueError as e:
        raise SignInError(UNREADABLE) from e
    if not isinstance(data, dict):
        raise SignInError(UNREADABLE)
    return data


def verified_claims(id_token: str, keys: Callable[[str], dict[str, Any] | None]) -> dict[str, Any]:
    """The claims in an ID token, once its RS256 signature is checked against the OpenAI key
    `keys` gives for its key ID (OpenAI's published JWKS); SignInError when it can't be."""
    parts = id_token.split(".")
    if len(parts) != 3:
        raise SignInError(UNREADABLE)
    header, payload = _json_part(parts[0]), _json_part(parts[1])
    if header.get("alg") != "RS256":
        raise SignInError(NOT_SIGNED)
    key = keys(str(header.get("kid", "")))
    try:
        if not key or key.get("kty") != "RSA":
            raise ValueError("no RSA key for this key ID")
        public = RSAPublicNumbers(
            int.from_bytes(_unb64(key["e"]), "big"), int.from_bytes(_unb64(key["n"]), "big")
        ).public_key()
        public.verify(_unb64(parts[2]), f"{parts[0]}.{parts[1]}".encode(), PKCS1v15(), SHA256())
    except (InvalidSignature, ValueError, KeyError, TypeError) as e:
        logger.error("ChatGPT identity's signature didn't check", extra={"error": type(e).__name__})
        raise SignInError(NOT_SIGNED) from e
    return payload


class ChatGptSignIn:
    """Signs in with ChatGPT, keeps the connection, and disconnects it."""

    def __init__(self, home: Path, http: Http = _http, clock: Callable[[], float] = time.time):
        self._path = home / FILENAME
        self._http = http
        self._clock = clock
        self._lock = threading.Lock()
        self._pending: dict[str, _Pending] = {}
        self._endpoints: dict[str, str] | None = None
        self._keys: dict[str, dict[str, Any]] = {}

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not an object")
            return data
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            logger.error("Could not read the ChatGPT sign-in", extra={"error": str(e)})
            return {}

    def status(self) -> dict[str, Any]:
        """For the Settings page: the connected account, never its tokens, and the account this
        app is registered to, which signing in again uses."""
        saved = self._load()
        connection = saved.get("connection") or {}
        return {
            "connected": bool(connection),
            "email": connection.get("email", ""),
            "name": connection.get("name", ""),
            "plan_usage": PLAN_SCOPE in connection.get("scopes", []),
            "registered_email": saved.get("email", "") if saved.get("client_id") else "",
        }

    def _discover(self) -> dict[str, str]:
        if self._endpoints is None:
            status, data = self._http(f"{ISSUER}/.well-known/openid-configuration", None)
            names = ("authorization_endpoint", "token_endpoint", "jwks_uri")
            if (
                status != 200
                or not isinstance(data, dict)
                or data.get("issuer") != ISSUER
                or any(not str(data.get(n, "")).startswith(ISSUER + "/") for n in names)
            ):
                logger.error("Could not read ChatGPT's sign-in settings", extra={"status": status})
                raise SignInError("ChatGPT's sign-in can't be reached right now. Try again.")
            revoke = str(data.get("revocation_endpoint", ""))
            self._endpoints = {n: data[n] for n in names}
            if revoke.startswith(ISSUER + "/"):
                self._endpoints["revocation_endpoint"] = revoke
        return self._endpoints

    def _key(self, kid: str) -> dict[str, Any] | None:
        """OpenAI's signing key with this ID, read again once when it isn't known (keys rotate)."""
        if kid not in self._keys:
            status, data = self._http(self._discover()["jwks_uri"], None)
            found = data.get("keys") if status == 200 and isinstance(data, dict) else None
            if not isinstance(found, list):
                logger.error("Could not read ChatGPT's signing keys", extra={"status": status})
                raise SignInError("ChatGPT's sign-in can't be reached right now. Try again.")
            self._keys = {str(k.get("kid", "")): k for k in found if isinstance(k, dict)}
        return self._keys.get(kid)

    def _host_id(self, saved: dict[str, Any]) -> str:
        """This computer's host ID for OpenAI: made on the first sign-in, then always the same."""
        host_id = saved.get("host_id")
        if not isinstance(host_id, str) or not host_id:
            host_id = f"urn:uuid:{uuid.uuid4()}"
            self._save({**saved, "host_id": host_id})
        return host_id

    def start(self, redirect_uri: str, consent: bool = False, another: bool = False) -> str:
        """The address on auth.openai.com that the browser is sent to, to sign in: again with
        this app's registration, asking for consent again when `consent`, or as `another`
        ChatGPT account, which registers the app anew."""
        endpoints = self._discover()
        saved = self._load()
        host_id = self._host_id(saved)
        registered = "" if another else str(saved.get("client_id") or "")
        verifier, state, nonce = (_b64(secrets.token_bytes(32)) for _ in range(3))
        now = self._clock()
        with self._lock:
            self._pending = {s: p for s, p in self._pending.items() if now - p.started < PENDING_S}
            while len(self._pending) >= MOST_PENDING:
                self._pending.pop(next(iter(self._pending)))
            self._pending[state] = _Pending(verifier, nonce, redirect_uri, now, registered)
        params = {
            "client_id": registered or REGISTER_CLIENT,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": SCOPES,
            "resource": RESOURCE,
            "state": state,
            "nonce": nonce,
            "code_challenge_method": "S256",
            "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
            "ext_agent_host_id": host_id,
        }
        if not registered:
            params["agent_name_hint"] = APP_NAME
        elif saved.get("email"):
            params["login_hint"] = saved["email"]
        if consent:
            params["prompt"] = "consent"
        logger.info(
            "Signing in with ChatGPT",
            extra={"registered": bool(registered), "consent": consent, "another": another},
        )
        return f"{endpoints['authorization_endpoint']}?{urllib.parse.urlencode(params)}"

    def finish(self, query: dict[str, str]) -> dict[str, Any]:
        """Completes the sign-in from the query OpenAI sent the browser back with."""
        start = time.perf_counter()
        with self._lock:
            pending = self._pending.pop(query.get("state", ""), None)
        if pending is None or self._clock() - pending.started >= PENDING_S:
            raise SignInError("This sign-in has expired or was already used. Sign in again.")
        if query.get("error"):
            logger.warning("ChatGPT sign-in refused", extra={"error": query["error"]})
            if query["error"] == "access_denied":
                raise SignInError("The sign-in was cancelled.")
            raise SignInError(f"ChatGPT refused the sign-in ({query['error']}).")
        saved = self._load()
        returned = query.get("client_id", "")
        if pending.client_id and returned and returned != pending.client_id:
            # A returning sign-in keeps its registration: another client ID isn't taken.
            logger.error("ChatGPT sign-in came back for another app")
            raise SignInError("ChatGPT's answer didn't match this sign-in. Sign in again.")
        client_id = pending.client_id or returned
        code = query.get("code", "")
        if not code or not CLIENT_ID.match(client_id) or client_id == REGISTER_CLIENT:
            raise SignInError("ChatGPT didn't finish registering this app. Sign in again.")
        if client_id != saved.get("client_id"):
            # Kept before the code is used, so a failed swap doesn't register another app; its
            # account is known once the identity is checked.
            self._save({**saved, "client_id": client_id, "subject": "", "email": ""})
        status, data = self._http(
            self._discover()["token_endpoint"],
            {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "code_verifier": pending.verifier,
                "redirect_uri": pending.redirect_uri,
                "resource": RESOURCE,
            },
        )
        if status != 200 or not isinstance(data, dict) or not data.get("access_token"):
            error = data.get("error", "") if isinstance(data, dict) else ""
            logger.error("ChatGPT sign-in code refused", extra={"status": status, "error": error})
            raise SignInError("ChatGPT didn't accept the sign-in. Sign in again.")
        identity = verified_claims(str(data.get("id_token", "")), self._key)
        audience = identity.get("aud")
        if (
            identity.get("iss") != ISSUER
            or client_id not in (audience if isinstance(audience, list) else [audience])
            or identity.get("nonce") != pending.nonce
            or not identity.get("sub")
            or float(identity.get("exp", 0)) < self._clock()
        ):
            logger.error("ChatGPT identity didn't match the sign-in")
            raise SignInError("ChatGPT's answer didn't match this sign-in. Sign in again.")
        bound_to = saved.get("subject")
        if pending.client_id and bound_to and identity["sub"] != bound_to:
            logger.error("ChatGPT sign-in came back as another account")
            raise SignInError(
                f"That's a different ChatGPT account from {saved.get('email') or 'the one'} "
                'this app is registered to. Use "Use another ChatGPT account" to switch.'
            )
        connection = {
            "subject": identity["sub"],
            "email": identity.get("email", ""),
            "name": identity.get("name", ""),
            "scopes": str(data.get("scope", "")).split(),
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", ""),
            "expires_at": self._clock() + float(data.get("expires_in", 0)),
        }
        self._save(
            {
                **self._load(),
                "client_id": client_id,
                "subject": identity["sub"],
                "email": connection["email"],
                "connection": connection,
            }
        )
        logger.info(
            "Signed in with ChatGPT",
            extra={
                "plan_usage": PLAN_SCOPE in connection["scopes"],
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return self.status()

    def sign_out(self) -> dict[str, Any]:
        """Forgets the connection, and asks OpenAI to end it; the registration is kept. The
        status says `revoked` false when OpenAI couldn't confirm it ended the connection."""
        saved = self._load()
        connection = saved.get("connection") or {}
        self._save({**saved, "connection": None})
        token = connection.get("refresh_token") or connection.get("access_token")
        revoked = False
        if token:
            try:
                url = self._discover().get("revocation_endpoint")
                if url:
                    form = {
                        "token": token,
                        "token_type_hint": "refresh_token"
                        if connection.get("refresh_token")
                        else "access_token",
                        "client_id": saved.get("client_id", ""),
                    }
                    revoked = self._http(url, form)[0] == 200
            except SignInError as e:
                logger.error("Could not end the ChatGPT sign-in", extra={"error": str(e)})
        logger.info(
            "Disconnected ChatGPT", extra={"was_connected": bool(connection), "revoked": revoked}
        )
        return {**self.status(), "revoked": revoked or not token}

    def _save(self, data: dict[str, Any]) -> None:
        with self._lock:
            write_owner_only(self._path, data)
