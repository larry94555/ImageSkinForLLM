"""Sign in with ChatGPT on the Settings page (roadmap R43, feature item 29).

OpenAI lets an open-source app that runs on the user's own machine use the user's ChatGPT plan
in place of an API key, through "Sign in with ChatGPT" (an OAuth sign-in with PKCE). This app
qualifies while it runs locally. The browser is sent to auth.openai.com, which sends it back to
this app's own address on 127.0.0.1 with a one-time code; the server swaps the code for tokens
and keeps them in chatgpt.json in the app's home folder, readable by the owner only where the
system allows. A token is never logged or sent to the browser: the page is told only which
account is connected and whether it allowed plan usage. R43a makes that plan answer the chat.

The first sign-in registers this app with OpenAI and gets back a client ID, bound to the ChatGPT
account that signed in. Each registration is kept, even after Disconnect, so signing in again reuses
it, sending its retained ID token as `id_token_hint` unless it was disconnected; a returning sign-in
that comes back with another client ID, or as another account, is refused. Each registration keeps
its own tokens, so "Use another ChatGPT account" adds one beside the others without touching theirs,
switching back to an account still connected needs no sign-in, and after a sign-in that didn't allow
plan use, "Allow use of my plan" asks for consent again. Every sign-in also sends one host ID, made
once and kept, so OpenAI sees the same computer each time. The ID token is checked against OpenAI's
published keys before any of its claims are used. Claude's and Grok's subscriptions offer no
supported way for another app to use them (decided before R43).
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

from imageskin.chat import LlmError
from imageskin.chatgpt_plan import RESOURCE
from imageskin.llm_choice import write_owner_only

logger = logging.getLogger(__name__)

FILENAME = "chatgpt.json"
ISSUER = "https://auth.openai.com"
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
REVOKE_TRIES = 3  # a network failure or 5xx is tried again, after 1 s then 2 s
REVOKE_BACKOFF_S = 1.0
# The access token is renewed when it has less than this left, so a reply never starts on a token
# about to end (R43a).
RENEW_BEFORE_S = 60
SIGN_IN_FIRST = "Sign in with ChatGPT on the Settings page first."
SIGN_IN_AGAIN = "Your ChatGPT sign-in has ended. Sign in with ChatGPT again on the Settings page."
NO_PLAN_USE = (
    'ChatGPT wasn\'t allowed to use your plan. Click "Allow use of my plan" on the Settings page.'
)

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
    # The client ID it was started with, when this app was already registered, or when a new
    # registration's code was refused and it is tried again (`provisional`).
    client_id: str = ""
    provisional: bool = False


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
    """Signs in with ChatGPT, keeps the connection, and disconnects it.

    chatgpt.json holds the host ID, one registration per ChatGPT account this app was registered
    (its issued client ID, verified account and retained ID token, cleared on Disconnect) with that
    account's own credentials (tokens, scopes and expiry, or null after Disconnect), and which
    registration is in use (`active`). A new registration whose code was refused keeps its issued
    client ID as `provisional`, never as an account, so the next new sign-in uses it rather than
    registering the app again; it becomes a registration once a sign-in through it checks out.
    Signing in or out changes only its own registration, so switching accounts leaves the others'
    credentials as they were. A registration is only written once its code is swapped and its
    identity checked, so a sign-in that fails leaves the accounts as they were."""

    def __init__(
        self,
        home: Path,
        http: Http = _http,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._path = home / FILENAME
        self._http = http
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()  # the pending sign-ins
        self._writing = threading.Lock()  # chatgpt.json: one read-change-write at a time
        # One renewal at a time: OpenAI replaces the refresh token with each, so two at once
        # would leave one holding a token already used.
        self._renewing = threading.Lock()
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

    def _update(self, change: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        """Reads chatgpt.json, changes it and writes it back, with no other change between."""
        with self._writing:
            data = change(self._load())
            write_owner_only(self._path, data)
            return data

    @staticmethod
    def _registrations(saved: dict[str, Any]) -> dict[str, dict[str, Any]]:
        found = saved.get("registrations")
        if not isinstance(found, list):
            return {}
        return {str(r["client_id"]): r for r in found if isinstance(r, dict) and r.get("client_id")}

    @staticmethod
    def _label(base: str, taken: list[str]) -> str:
        """A new registration's label: its email, numbered when another registration already
        shows it, since one ChatGPT email can be registered more than once (another workspace).
        It is saved with the registration, so it stays the same on every reload."""
        if base not in taken:
            return base
        n = 2
        while f"{base} ({n})" in taken:
            n += 1
        return f"{base} ({n})"

    @classmethod
    def _labels(cls, registrations: dict[str, dict[str, Any]]) -> dict[str, str]:
        """Each registration's label; one saved without a label gets one in file order."""
        labels: dict[str, str] = {}
        for cid, r in registrations.items():
            saved = r.get("label")
            if isinstance(saved, str) and saved and saved not in labels.values():
                labels[cid] = saved
        for cid, r in registrations.items():
            if cid not in labels:
                base = r.get("email") or r.get("name") or "ChatGPT account"
                labels[cid] = cls._label(base, list(labels.values()))
        return labels

    def status(self) -> dict[str, Any]:
        """For the Settings page: the account in use and whether it is connected, never its
        tokens, and the other accounts this app is registered for."""
        saved = self._load()
        registrations = self._registrations(saved)
        active = registrations.get(str(saved.get("active", ""))) or {}
        credentials = active.get("credentials") or {}
        labels = self._labels(registrations)
        return {
            "connected": bool(credentials),
            "email": active.get("email", "") if credentials else "",
            "name": active.get("name", "") if credentials else "",
            "plan_usage": PLAN_SCOPE in credentials.get("scopes", []),
            "registered_email": active.get("email", ""),
            # The account in use, as the page shows it: distinct even when emails are the same.
            "label": labels.get(str(active.get("client_id", "")), ""),
            "accounts": [
                {
                    "id": cid,
                    "email": r.get("email", ""),
                    "label": labels[cid],
                    "connected": bool(r.get("credentials")),
                }
                for cid, r in registrations.items()
                if r is not active
            ],
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

    def _host_id(self) -> str:
        """This computer's host ID for OpenAI: made on the first sign-in, then always the same."""

        def ensure(saved: dict[str, Any]) -> dict[str, Any]:
            host_id = saved.get("host_id")
            if isinstance(host_id, str) and host_id:
                return saved
            return {**saved, "host_id": f"urn:uuid:{uuid.uuid4()}"}

        return str(self._update(ensure)["host_id"])

    def start(
        self, redirect_uri: str, consent: bool = False, another: bool = False, account: str = ""
    ) -> str:
        """The address on auth.openai.com that the browser is sent to, to sign in: again with
        the active registration, or `account`'s; asking for consent again when `consent`; or as
        `another` ChatGPT account, which registers the app anew."""
        endpoints = self._discover()
        host_id = self._host_id()
        saved = self._load()
        registrations = self._registrations(saved)
        chosen = account if account in registrations else str(saved.get("active", ""))
        registration = None if another else registrations.get(chosen)
        registered = str(registration["client_id"]) if registration else ""
        provisional = str(saved.get("provisional", ""))
        retrying = not registration and bool(CLIENT_ID.match(provisional))
        if retrying:
            registered = provisional
        verifier, state, nonce = (_b64(secrets.token_bytes(32)) for _ in range(3))
        now = self._clock()
        with self._lock:
            self._pending = {s: p for s, p in self._pending.items() if now - p.started < PENDING_S}
            while len(self._pending) >= MOST_PENDING:
                self._pending.pop(next(iter(self._pending)))
            self._pending[state] = _Pending(
                verifier, nonce, redirect_uri, now, registered, provisional=retrying
            )
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
            # Only a dynamic registration names the app; an issued client ID already has it.
            params["agent_name_hint"] = APP_NAME
        elif registration:
            if registration.get("email"):
                params["login_hint"] = registration["email"]
            if registration.get("id_token"):
                params["id_token_hint"] = registration["id_token"]
        if consent:
            params["prompt"] = "consent"
        logger.info(
            "Signing in with ChatGPT",
            extra={
                "registered": bool(registration),
                "retrying_registration": retrying,
                "consent": consent,
                "another": another,
            },
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
        returned = query.get("client_id", "")
        if pending.client_id and returned and returned != pending.client_id:
            # A returning sign-in keeps its registration: another client ID isn't taken.
            logger.error("ChatGPT sign-in came back for another app")
            raise SignInError("ChatGPT's answer didn't match this sign-in. Sign in again.")
        client_id = pending.client_id or returned
        code = query.get("code", "")
        if not code or not CLIENT_ID.match(client_id) or client_id == REGISTER_CLIENT:
            raise SignInError("ChatGPT didn't finish registering this app. Sign in again.")
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
            if error == "invalid_grant" and (not pending.client_id or pending.provisional):
                # OpenAI's recovery: drop the code but keep the issued client ID, and start the
                # next new sign-in with it rather than registering the app again.
                self._update(lambda saved: {**saved, "provisional": client_id})
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
        credentials = {
            "scopes": str(data.get("scope", "")).split(),
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", ""),
            "expires_at": self._clock() + float(data.get("expires_in", 0)),
        }

        def commit(saved: dict[str, Any]) -> dict[str, Any]:
            registrations = self._registrations(saved)
            bound = registrations.get(client_id)
            returning = pending.client_id and not pending.provisional
            if returning and (bound is None or bound.get("subject") != identity["sub"]):
                logger.error("ChatGPT sign-in came back as another account")
                email = (bound or {}).get("email") or "the one"
                raise SignInError(
                    f"That's a different ChatGPT account from {email} this app is registered "
                    'to. Use "Use another ChatGPT account" to switch.'
                )
            labels = self._labels(registrations)
            base = identity.get("email") or identity.get("name") or "ChatGPT account"
            label = labels.get(client_id) or self._label(base, list(labels.values()))
            registrations[client_id] = {
                "client_id": client_id,
                "label": label,
                "subject": identity["sub"],
                "email": identity.get("email", ""),
                "name": identity.get("name", ""),
                "id_token": data["id_token"],
                "credentials": credentials,
            }
            kept = {k: v for k, v in saved.items() if k != "provisional"}
            if saved.get("provisional") not in (None, client_id):
                kept["provisional"] = saved["provisional"]
            return {**kept, "registrations": list(registrations.values()), "active": client_id}

        self._update(commit)
        logger.info(
            "Signed in with ChatGPT",
            extra={
                "plan_usage": PLAN_SCOPE in credentials["scopes"],
                "new_registration": not pending.client_id or pending.provisional,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return self.status()

    def use(self, account: str) -> dict[str, Any]:
        """Makes `account`, a registration of this app, the one in use; one still connected is
        used again with no sign-in."""

        def choose(saved: dict[str, Any]) -> dict[str, Any]:
            if account not in self._registrations(saved):
                raise SignInError("That ChatGPT account isn't registered here. Sign in again.")
            return {**saved, "active": account}

        status = self.status() if account == self._load().get("active") else None
        if status is None:
            self._update(choose)
            status = self.status()
        logger.info("Switched ChatGPT account", extra={"connected": status["connected"]})
        return status

    def _revoke(self, connection: dict[str, Any], token: str) -> bool:
        """Asks OpenAI to end the connection, retrying with backoff after a network failure or a
        5xx, while the token is still saved. True when OpenAI confirmed it."""
        form = {
            "token": token,
            "token_type_hint": "refresh_token"
            if connection.get("refresh_token")
            else "access_token",
            "client_id": connection.get("client_id", ""),
        }
        for attempt in range(REVOKE_TRIES):
            if attempt:
                self._sleep(REVOKE_BACKOFF_S * 2 ** (attempt - 1))
            try:
                url = self._discover().get("revocation_endpoint")
                if not url:
                    return False
                code = self._http(url, form)[0]
            except SignInError as e:
                logger.error(
                    "Could not end the ChatGPT sign-in",
                    extra={"error": str(e), "attempt": attempt + 1},
                )
                continue
            if code < 500:
                return code == 200
            logger.error(
                "Could not end the ChatGPT sign-in", extra={"status": code, "attempt": attempt + 1}
            )
        return False

    def sign_out(self) -> dict[str, Any]:
        """Asks OpenAI to end the active account's connection, then forgets its tokens whatever
        the outcome; its registration, and the other accounts, are kept. The status says
        `revoked` false when OpenAI couldn't confirm it ended the connection. Its tokens and ID
        token are forgotten either way."""
        saved = self._load()
        client_id = str(saved.get("active", ""))
        active = self._registrations(saved).get(client_id) or {}
        connection = {**(active.get("credentials") or {}), "client_id": client_id}
        token = connection.get("refresh_token") or connection.get("access_token")
        revoked = self._revoke(connection, token) if token else False

        def forget(saved: dict[str, Any]) -> dict[str, Any]:
            registrations = self._registrations(saved)
            current = registrations.get(client_id)
            # Only the credentials just revoked: a sign-in that finished meanwhile is kept.
            if not current or current.get("credentials") != active.get("credentials"):
                return saved
            # Its ID token goes too, so the next sign-in sends no `id_token_hint`; the client ID
            # and verified account stay, to sign in as it again.
            registrations[client_id] = {**current, "credentials": None, "id_token": ""}
            return {**saved, "registrations": list(registrations.values())}

        self._update(forget)
        logger.info(
            "Disconnected ChatGPT", extra={"was_connected": bool(token), "revoked": revoked}
        )
        return {**self.status(), "revoked": revoked or not token}

    def access_token(self, renew: bool = False) -> str:
        """The account in use's access token for its plan (R43a), renewed first when it ends
        within a minute, or when `renew` because OpenAI refused it; SignInError, in plain words,
        when there is none to use."""
        with self._renewing:
            saved = self._load()
            client_id = str(saved.get("active", ""))
            active = self._registrations(saved).get(client_id) or {}
            credentials = active.get("credentials") or {}
            if not credentials.get("access_token"):
                raise SignInError(SIGN_IN_FIRST)
            if PLAN_SCOPE not in credentials.get("scopes", []):
                raise SignInError(NO_PLAN_USE)
            left = float(credentials.get("expires_at", 0)) - self._clock()
            if not renew and left > RENEW_BEFORE_S:
                return str(credentials["access_token"])
            return self._renew(client_id, credentials)

    def plan_token(self, renew: bool = False) -> str:
        """`access_token` for the ChatGPT plan's client (R43a): LlmError when there is none, so
        the chat says why in plain words."""
        try:
            return self.access_token(renew)
        except SignInError as e:
            logger.error("No ChatGPT sign-in to answer with", extra={"error": str(e)})
            raise LlmError(str(e)) from e

    def _renew(self, client_id: str, credentials: dict[str, Any]) -> str:
        start = time.perf_counter()
        refresh = credentials.get("refresh_token")
        if not refresh:
            raise SignInError(SIGN_IN_AGAIN)
        status, data = self._http(
            self._discover()["token_endpoint"],
            {
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": refresh,
                "resource": RESOURCE,
            },
        )
        if status != 200 or not isinstance(data, dict) or not data.get("access_token"):
            error = data.get("error", "") if isinstance(data, dict) else ""
            logger.error(
                "Could not renew the ChatGPT sign-in", extra={"status": status, "error": error}
            )
            if status in (400, 401):  # the refresh token was refused: only a sign-in helps
                raise SignInError(SIGN_IN_AGAIN)
            raise SignInError("ChatGPT's sign-in can't be reached right now. Try again.")
        renewed = {
            "scopes": str(data.get("scope", "")).split() or credentials.get("scopes", []),
            "access_token": data["access_token"],
            # OpenAI may send a new refresh token; the old one is then used up.
            "refresh_token": data.get("refresh_token") or refresh,
            "expires_at": self._clock() + float(data.get("expires_in", 0)),
        }

        def keep(saved: dict[str, Any]) -> dict[str, Any]:
            registrations = self._registrations(saved)
            current = registrations.get(client_id)
            # Not if the account was disconnected or signed in again meanwhile.
            if not current or current.get("credentials") != credentials:
                return saved
            registrations[client_id] = {**current, "credentials": renewed}
            return {**saved, "registrations": list(registrations.values())}

        self._update(keep)
        logger.info(
            "Renewed the ChatGPT sign-in",
            extra={"duration_ms": round((time.perf_counter() - start) * 1000, 1)},
        )
        return str(renewed["access_token"])
