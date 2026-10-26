"""Signing in as the administrator (roadmap R149, items 121 to 123).

The password is set only in a file on the computer, `admin.toml` in the app's home folder or the
config file's `admin_file`, never in the app (item 122). The file is read again whenever it
changes, so a new password works at once with no restart, and a sign-in made with the old one
ends. Sign-ins are kept in memory, so a restart signs the administrator out.
"""

import base64
import hashlib
import hmac
import logging
import secrets
import threading
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

FILENAME = "admin.toml"
# Without activity for this long, a sign-in ends (item 123); R155 makes it an admin setting.
TIMEOUT_MINUTES = 30
# After this many wrong passwords in a row, the next try waits (item 121).
WRONG_IN_A_ROW = 5
WAIT_S = 60.0
# scrypt's cost: about 50 ms and 16 MB a try, so guessing a hash taken from the file is slow.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1

NOT_SET = (
    "No administrator password is set on this computer, so signing in as the administrator is "
    "off. See the admin password guide to set one."
)
WRONG = "That isn't the administrator password."
WAIT = "Too many wrong passwords. Wait a minute, then try again."


class AdminRefused(Exception):
    """A sign-in that was refused, with the reason for the log and a message for the page."""

    def __init__(self, reason: str, message: str, status: int) -> None:
        super().__init__(message)
        self.reason = reason
        self.status = status


def hash_password(password: str) -> str:
    """The `password_hash` to write in the admin file for this password."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )
    b64 = base64.b64encode
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${b64(salt).decode()}${b64(digest).decode()}"


def password_matches(password: str, secret: "Secret") -> bool:
    """Whether the password is the one in the file, compared in constant time."""
    if secret.kind == "password":
        return hmac.compare_digest(password.encode(), secret.value.encode())
    try:
        _, n, r, p, salt, digest = secret.value.split("$")
        expected = base64.b64decode(digest)
        given = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except ValueError as e:  # a hash that wasn't made by hash_password, or was cut short
        logger.error("Admin password hash is not valid", extra={"error": str(e)})
        return False
    return hmac.compare_digest(given, expected)


@dataclass(frozen=True)
class Secret:
    # "password" written as it is, or "hash" from `imageskin admin-password-hash`.
    kind: str
    value: str

    @property
    def fingerprint(self) -> str:
        """Changes when the password in the file changes, so its sign-ins can be ended."""
        return hashlib.sha256(f"{self.kind}:{self.value}".encode()).hexdigest()


def read_secret(path: Path) -> Secret | None:
    """The password in the admin file, or None when there is no file or no password in it."""
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return None
    except (OSError, tomllib.TOMLDecodeError) as e:
        logger.error(
            "Could not read the admin password file", extra={"path": str(path), "error": str(e)}
        )
        return None
    hashed, plain = data.get("password_hash"), data.get("password")
    if isinstance(hashed, str) and hashed.strip():
        return Secret("hash", hashed.strip())
    if isinstance(plain, str) and plain:
        return Secret("password", plain)
    return None


@dataclass
class SignIn:
    last_activity: float
    fingerprint: str


class AdminSignIns:
    """Who is signed in as the administrator, by the token in their cookie."""

    def __init__(
        self,
        path: Path,
        timeout_minutes: Callable[[], int] = lambda: TIMEOUT_MINUTES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.path = path
        self.timeout_minutes = timeout_minutes
        self.clock = clock
        self._lock = threading.Lock()
        self._signed_in: dict[str, SignIn] = {}
        # Why each ended sign-in ended, so the page can say so; dropped once read.
        self._ended: dict[str, str] = {}
        self._wrong = 0
        self._wrong_at = 0.0
        self._file_seen: tuple[int, int] | None = None
        self._secret: Secret | None = None

    def secret(self) -> Secret | None:
        """The password in the file, read again only when the file has changed."""
        try:
            stat = self.path.stat()
            seen: tuple[int, int] | None = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            seen = None
        if seen != self._file_seen:
            before = self._secret
            self._secret = read_secret(self.path) if seen else None
            self._file_seen = seen
            changed = (before and before.fingerprint) != (self._secret and self._secret.fingerprint)
            logger.info(
                "Admin password file read",
                extra={
                    "path": str(self.path),
                    "password_set": self._secret is not None,
                    "changed": changed,
                },
            )
        return self._secret

    def sign_in(self, password: str, address: str) -> str:
        """A new sign-in's token; AdminRefused when the password is wrong, not set or waiting."""
        with self._lock:
            now = self.clock()
            if self._wrong >= WRONG_IN_A_ROW and now - self._wrong_at < WAIT_S:
                self._refuse("waiting", address)
                raise AdminRefused("waiting", WAIT, 429)
            secret = self.secret()
            if secret is None:
                self._refuse("no password set", address)
                raise AdminRefused("no password set", NOT_SET, 403)
            if not password_matches(password, secret):
                self._wrong += 1
                self._wrong_at = now
                self._refuse("wrong password", address)
                raise AdminRefused("wrong password", WRONG, 401)
            self._wrong = 0
            token = secrets.token_urlsafe(32)
            self._signed_in[token] = SignIn(now, secret.fingerprint)
        logger.info("Admin signed in", extra={"address": address})
        return token

    def _refuse(self, reason: str, address: str) -> None:
        logger.warning(
            "Admin sign-in refused",
            extra={"reason": reason, "address": address, "wrong_in_a_row": self._wrong},
        )

    def signed_in(self, token: str | None) -> bool:
        """Whether the token is signed in now. Not activity: the dashboard's refreshes ask this."""
        with self._lock:
            return self._current(token) is not None

    def activity(self, token: str | None) -> bool:
        """Note the administrator is active; False if the token is no longer signed in."""
        with self._lock:
            sign_in = self._current(token)
            if sign_in is None:
                return False
            sign_in.last_activity = self.clock()
            return True

    def sign_out(self, token: str | None) -> None:
        with self._lock:
            if token and self._signed_in.pop(token, None):
                logger.info("Admin signed out", extra={"why": "signed out"})

    def ended(self, token: str | None) -> str | None:
        """Why the token's sign-in ended, if it did by itself: "inactive" or "password changed"."""
        with self._lock:
            self._current(token)
            return self._ended.pop(token, None) if token else None

    def _current(self, token: str | None) -> SignIn | None:
        """The token's sign-in, ending it first if it has timed out or the password changed."""
        if not token or token not in self._signed_in:
            return None
        sign_in = self._signed_in[token]
        secret = self.secret()
        if secret is None or secret.fingerprint != sign_in.fingerprint:
            why = "password changed"
        elif self.clock() - sign_in.last_activity > self.timeout_minutes() * 60:
            why = "inactive"
        else:
            return sign_in
        del self._signed_in[token]
        self._ended[token] = why
        logger.info(
            "Admin signed out",
            extra={"why": why, "inactive_s": round(self.clock() - sign_in.last_activity)},
        )
        return None
