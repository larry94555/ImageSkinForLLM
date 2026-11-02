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
from imageskin.admin_settings import Choice

logger = logging.getLogger(__name__)

FILENAME = "hosts.json"
HOST_COOKIE = "imageskin_host"  # the cookie that keeps a host signed in (R188)
# The site at the main address (R61): every host's until they are given a site of their own.
DEFAULT_SITE = "default"
SITE = "site"  # the host's site, kept with the host; none for the main address's
MIN_PASSWORD = 10
# Enough to catch a typo, not a full check: the confirmation email checks the address (R62b).
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

BAD_EMAIL = "Enter an email address, such as name@example.com."
SHORT_PASSWORD = f"The password must be at least {MIN_PASSWORD} characters."
EMAIL_TAKEN = "That email address is already signed up. Sign in instead."
# The same words whether the email or the password is wrong, so a guess can't learn which
# emails are signed up; only the log says which.
WRONG = "The email address or password is wrong."


UNREADABLE = "Host accounts can't be read right now. Please try again later."
# A host's own Allow or Deny of a custom image and a custom voice (R242), kept with the host.
CUSTOM_IMAGE = "custom_image"
CUSTOM_VOICE = "custom_voice"


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


class HostElsewhere(HostRefused):
    """The right password, but the host's site is another one (R61e): told only once the
    password is checked, so a guess learns nothing, and the page says where to sign in."""

    def __init__(self, site: str) -> None:
        super().__init__(WRONG, "another site's host")
        self.site = site


def trial_cookie(code: str) -> str:
    """The name of a trial site's host cookie (R62). Every trial site is at the same address,
    so each has a cookie of its own, kept for its path only; the main address's never reaches
    it, and a trial site's app reads and sets its own as `imageskin_host`, as any site does."""
    return f"{HOST_COOKIE}_{code}"


def normal_email(email: str) -> str:
    return email.strip().lower()


def token_key(token: str) -> str:
    """What the file keeps for a sign-in's token."""
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Host:
    email: str
    created_at: float
    site: str = DEFAULT_SITE  # the site the host signs in to and manages (R61)


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

    def sign_in_now(self, email: str) -> str:
        """A new sign-in for the host, as after signing up (R62): its token."""
        email = normal_email(email)
        with self._lock:
            data = self._load()
            if email not in data["hosts"]:
                raise HostRefused(WRONG, "no such host")
            data = {**data, "sessions": {**data["sessions"]}}
            token = self._new_sign_in(data, email)
            self._save(data)
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

    def sign_in(self, email: str, password: str, address: str, site: str = DEFAULT_SITE) -> str:
        """A new sign-in's token; HostRefused, with the same words for an unknown email and a
        wrong password, when either is wrong, or the host is another site's (R61)."""
        start = time.perf_counter()
        email = normal_email(email)
        with self._lock:
            account = self._load()["hosts"].get(email)
        secret = Secret("hash", account["password_hash"]) if account else None
        # One scrypt run either way, so the time taken doesn't say whether the email is known.
        if not check_password(password, secret):
            reason = "wrong password" if account else "no such host"
            self._refuse(WRONG, reason, "sign-in", email, address)
        if account and account.get(SITE, DEFAULT_SITE) != site:
            elsewhere = str(account.get(SITE, DEFAULT_SITE))
            logger.warning(
                "Host sign-in failed",
                extra={
                    "reason": "another site's host",
                    "email": email,
                    "address": address,
                    "host_site": elsewhere,
                },
            )
            raise HostElsewhere(elsewhere)
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

    def exists(self, email: str) -> bool:
        """Whether a host has signed up with this email address."""
        with self._lock:
            try:
                return normal_email(email) in self._load()["hosts"]
            except HostsUnreadable:
                return False

    def emails(self, contains: str = "") -> list[str]:
        """Every host's email, sorted, or only those with `contains` anywhere in them, ignoring
        capitals, as `*text*` would match (R241); HostsUnreadable when the file can't be read."""
        wanted = contains.strip().lower()
        with self._lock:
            hosts = list(self._load()["hosts"])
        return sorted(e for e in hosts if wanted in e.lower())

    def host(self, token: str | None, site: str | None = None) -> Host | None:
        """The host the token is signed in as, or None; with `site`, only that site's host
        (R61), so another site's sign-in counts as none."""
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
        host = Host(
            session["email"],
            account["created_at"],
            account.get(SITE, DEFAULT_SITE),
        )
        if site is not None and host.site != site:
            logger.warning(
                "Host sign-in refused: another site",
                extra={"email": host.email, "site": site, "host_site": host.site},
            )
            return None
        return host

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

    def accounts(self) -> dict[str, dict[str, Any]]:
        """Each host's email with when they signed up and their site, never their password's
        hash; HostsUnreadable when the file can't be read."""
        with self._lock:
            hosts = self._load()["hosts"]
        return {
            email: {k: v for k, v in account.items() if k in ("created_at", SITE)}
            for email, account in hosts.items()
        }

    def site_of(self, email: str) -> str | None:
        """The host's site (R61), or None when there is no such host."""
        with self._lock:
            account = self._load()["hosts"].get(normal_email(email))
        return None if account is None else str(account.get(SITE, DEFAULT_SITE))

    def set_site(self, email: str, site: str) -> bool:
        """Make the host the site's (R61), ending their sign-ins, which were the old site's.
        False when there is no such host."""
        email = normal_email(email)
        with self._lock:
            data = self._load()
            if email not in data["hosts"]:
                logger.warning("Host site not set", extra={"email": email, "why": "no host"})
                return False
            account = {**data["hosts"][email]}
            old = account.get(SITE, DEFAULT_SITE)
            if site == DEFAULT_SITE:
                account.pop(SITE, None)
            else:
                account[SITE] = site
            sessions = {k: v for k, v in data["sessions"].items() if v["email"] != email}
            self._save({**data, "hosts": {**data["hosts"], email: account}, "sessions": sessions})
        logger.info("Host site set", extra={"email": email, "site": site, "old_site": old})
        return True

    def choices(self, email: str) -> tuple[Choice, Choice]:
        """The host's own Allow or Deny of a custom image and a custom voice (R242), each None
        when they follow Admin settings' checkbox; both None for no such host, or while the file
        can't be read, so the checkboxes decide."""
        with self._lock:
            try:
                account = self._load()["hosts"].get(normal_email(email), {})
            except HostsUnreadable:
                return None, None
        return _choice(account.get(CUSTOM_IMAGE)), _choice(account.get(CUSTOM_VOICE))

    def set_choices(self, email: str, changes: dict[str, Choice]) -> tuple[Choice, Choice] | None:
        """Change the host's own choices (R242), kept with the host so they go with it; `changes`
        has `custom_image` and/or `custom_voice`, each "allow", "deny" or None for the default.
        None when there is no such host. Logged as `Host properties changed` with each choice's
        old and new."""
        email = normal_email(email)
        with self._lock:
            data = self._load()
            if email not in data["hosts"]:
                logger.warning(
                    "Host properties not changed", extra={"email": email, "why": "no host"}
                )
                return None
            account = {**data["hosts"][email]}
            old = (_choice(account.get(CUSTOM_IMAGE)), _choice(account.get(CUSTOM_VOICE)))
            for key, choice in changes.items():
                if choice is None:
                    account.pop(key, None)
                else:
                    account[key] = choice
            self._save({**data, "hosts": {**data["hosts"], email: account}})
        new = (_choice(account.get(CUSTOM_IMAGE)), _choice(account.get(CUSTOM_VOICE)))
        logger.info(
            "Host properties changed",
            extra={
                "email": email,
                "custom_image_change": [old[0], new[0]],
                "custom_voice_change": [old[1], new[1]],
            },
        )
        return new


def _choice(value: object) -> Choice:
    """A stored choice, or None for anything else, so a hand-edited file can't allow by mistake."""
    return value if value in ("allow", "deny") else None
