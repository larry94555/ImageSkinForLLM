"""Host accounts (roadmap R188, item 148): sign up, sign in and sign out as a host.

Accounts and sign-ins are kept in `hosts.json` in the app's home folder, so a host stays signed
in through restarts until they sign out. Only a hash of each password is kept, made as the admin
password's is (R149), and only a hash of each sign-in's token, so the file alone can't sign in.
The file is read again whenever it changes, so `imageskin host-password-reset` works on a
running server. No email is sent yet: confirming the address and Forgot password come with R62
and R62a.
"""

import hashlib
import json
import logging
import os
import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from imageskin.admin import Secret, check_password, hash_password

logger = logging.getLogger(__name__)

FILENAME = "hosts.json"
MIN_PASSWORD = 10
# Enough to catch a typo, not a full check: confirming the address comes with R62.
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

BAD_EMAIL = "Enter an email address, such as name@example.com."
SHORT_PASSWORD = f"The password must be at least {MIN_PASSWORD} characters."
EMAIL_TAKEN = "That email address is already signed up. Sign in instead."
# The same words whether the email or the password is wrong, so a guess can't learn which
# emails are signed up; only the log says which.
WRONG = "The email address or password is wrong."


UNREADABLE = "Host accounts can't be read right now. Please try again later."


class HostsUnreadable(Exception):
    """hosts.json is there but can't be read or parsed. Nothing is written over it, so the
    accounts in it are never lost to an empty file (Codex's review); only the log says why."""

    def __init__(self) -> None:
        super().__init__(UNREADABLE)


class HostRefused(Exception):
    """A refused sign-up or sign-in: the words for the page, and the reason for the log."""

    def __init__(self, message: str, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


def normal_email(email: str) -> str:
    return email.strip().lower()


def token_key(token: str) -> str:
    """What the file keeps for a sign-in's token."""
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Host:
    email: str
    created_at: float


class HostAccounts:
    """The hosts signed up on this site, and who is signed in, by the token in their cookie."""

    def __init__(self, home: Path, clock: Callable[[], float] = time.time) -> None:
        self.path = home / FILENAME
        self.clock = clock
        self._lock = threading.Lock()
        self._file_seen: tuple[int, int] | None = None
        self._data: dict[str, Any] = {"hosts": {}, "sessions": {}}

    def _load(self) -> dict[str, Any]:
        """The file's accounts and sign-ins, read again only when the file has changed;
        HostsUnreadable when it is there but can't be used, so nothing reads or writes it."""
        try:
            stat = self.path.stat()
            seen: tuple[int, int] | None = (stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            seen = None
        except OSError as e:
            # Only a missing file is no hosts yet; any other failure fails closed (Codex's review).
            logger.error(
                "Could not read the host accounts file",
                extra={"path": str(self.path), "error": str(e)},
            )
            raise HostsUnreadable() from e
        if seen != self._file_seen:
            data: dict[str, Any] = {"hosts": {}, "sessions": {}}
            if seen:
                try:
                    data.update(json.loads(self.path.read_text(encoding="utf-8")))
                    if not all(isinstance(data[k], dict) for k in ("hosts", "sessions")):
                        raise ValueError("hosts and sessions must be objects")
                except (OSError, ValueError, TypeError) as e:
                    # Not remembered as seen, so the file is tried again once it is fixed.
                    logger.error(
                        "Could not read the host accounts file",
                        extra={"path": str(self.path), "error": str(e)},
                    )
                    raise HostsUnreadable() from e
            self._data, self._file_seen = data, seen
        return self._data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Written beside it, then put in its place, so a read never sees half a file.
        part = self.path.with_suffix(".part")
        part.write_text(json.dumps(data, indent=1), encoding="utf-8")
        # Readable only by its owner, as it holds the password hashes (where the system allows).
        os.chmod(part, 0o600)
        os.replace(part, self.path)
        stat = self.path.stat()
        self._data, self._file_seen = data, (stat.st_mtime_ns, stat.st_size)

    def _refuse(self, message: str, reason: str, action: str, email: str, address: str) -> NoReturn:
        logger.warning(
            f"Host {action} failed",
            extra={"reason": reason, "email": email, "address": address},
        )
        raise HostRefused(message, reason)

    def _new_sign_in(self, data: dict[str, Any], email: str) -> str:
        token = secrets.token_urlsafe(32)
        data["sessions"][token_key(token)] = {"email": email, "created_at": self.clock()}
        return token

    def sign_up(self, email: str, password: str, address: str) -> str:
        """Make a host account and sign it in, returning the sign-in's token; HostRefused when
        the email isn't one, the password is too short or the email is already signed up."""
        start = time.perf_counter()
        email = normal_email(email)
        if not EMAIL.fullmatch(email):
            self._refuse(BAD_EMAIL, "not an email address", "sign-up", email, address)
        if len(password) < MIN_PASSWORD:
            self._refuse(SHORT_PASSWORD, "password too short", "sign-up", email, address)
        # Hashed before the lock, as it takes about 50 ms.
        password_hash = hash_password(password)
        with self._lock:
            data = self._load()
            if email in data["hosts"]:
                self._refuse(EMAIL_TAKEN, "email already signed up", "sign-up", email, address)
            data = {**data, "hosts": {**data["hosts"]}, "sessions": {**data["sessions"]}}
            data["hosts"][email] = {"password_hash": password_hash, "created_at": self.clock()}
            token = self._new_sign_in(data, email)
            self._save(data)
        logger.info(
            "Host signed up",
            extra={
                "email": email,
                "address": address,
                "hosts": len(data["hosts"]),
                "took_ms": round((time.perf_counter() - start) * 1000),
            },
        )
        return token

    def sign_in(self, email: str, password: str, address: str) -> str:
        """A new sign-in's token; HostRefused, with the same words for an unknown email and a
        wrong password, when either is wrong."""
        start = time.perf_counter()
        email = normal_email(email)
        with self._lock:
            account = self._load()["hosts"].get(email)
        secret = Secret("hash", account["password_hash"]) if account else None
        # One scrypt run either way, so the time taken doesn't say whether the email is known.
        if not check_password(password, secret):
            reason = "wrong password" if account else "no such host"
            self._refuse(WRONG, reason, "sign-in", email, address)
        with self._lock:
            data = self._load()
            now = data["hosts"].get(email)
            # The password reset while it was checked (Codex's review): no sign-in with the old
            # one, as the reset ended the host's sign-ins.
            if now is None or now["password_hash"] != secret.value:  # type: ignore[union-attr]
                self._refuse(WRONG, "password changed while signing in", "sign-in", email, address)
            data = {**data, "sessions": {**data["sessions"]}}
            token = self._new_sign_in(data, email)
            self._save(data)
        logger.info(
            "Host signed in",
            extra={
                "email": email,
                "address": address,
                "took_ms": round((time.perf_counter() - start) * 1000),
            },
        )
        return token

    def host(self, token: str | None) -> Host | None:
        """The host the token is signed in as, or None."""
        if not token:
            return None
        with self._lock:
            try:
                data = self._load()
            except HostsUnreadable:
                return None  # signed in as no one until the file can be read
            session = data["sessions"].get(token_key(token))
            account = session and data["hosts"].get(session["email"])
        if not account:
            return None
        return Host(session["email"], account["created_at"])

    def sign_out(self, token: str | None, address: str) -> None:
        """End the token's sign-in on the server, so the same cookie is refused from now on."""
        if not token:
            return
        with self._lock:
            data = self._load()
            key = token_key(token)
            session = data["sessions"].get(key)
            if session is None:
                return
            sessions = {k: v for k, v in data["sessions"].items() if k != key}
            self._save({**data, "sessions": sessions})
        logger.info("Host signed out", extra={"email": session["email"], "address": address})

    def reset_password(self, email: str, password: str) -> bool:
        """Set a host's password from the server (until R62a's Forgot password), ending every
        sign-in the host has; False when there is no such host."""
        email = normal_email(email)
        if len(password) < MIN_PASSWORD:
            raise HostRefused(SHORT_PASSWORD, "password too short")
        password_hash = hash_password(password)
        with self._lock:
            data = self._load()
            if email not in data["hosts"]:
                logger.warning("Host password not reset", extra={"email": email, "why": "no host"})
                return False
            hosts = {**data["hosts"], email: {**data["hosts"][email]}}
            hosts[email]["password_hash"] = password_hash
            sessions = {k: v for k, v in data["sessions"].items() if v["email"] != email}
            ended = len(data["sessions"]) - len(sessions)
            self._save({**data, "hosts": hosts, "sessions": sessions})
        logger.info("Host password reset", extra={"email": email, "sign_ins_ended": ended})
        return True
