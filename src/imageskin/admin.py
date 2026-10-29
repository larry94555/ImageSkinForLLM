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
from functools import cache
from pathlib import Path
from typing import NoReturn

from imageskin.admin_laptops import FILENAME as LAPTOPS_FILENAME
from imageskin.admin_laptops import AdminLaptops, LaptopProof
from imageskin.failure import new_reference

logger = logging.getLogger(__name__)

FILENAME = "admin.toml"
# Without activity for this long, a sign-in ends (item 123); R155 makes it an admin setting.
TIMEOUT_MINUTES = 30
# After this many failed sign-ins in a row, whatever their cause, the next try waits (item 121).
WRONG_IN_A_ROW = 5
WAIT_S = 60.0
# scrypt's cost: about 50 ms and 16 MB a try, so guessing a hash taken from the file is slow.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
# The most a hash in the file may ask of scrypt: hashlib's own memory limit, 32 MB a try.
SCRYPT_MAX_MEMORY = 32 * 1024**2
# Addresses with wrong passwords kept at most: past this, those whose wait is over are dropped,
# then the ones that guessed longest ago, so a flood of addresses can't use up the memory.
WRONG_KEPT = 1000

# Every failed sign-in gets these words and a new code, whatever the cause (R162): a different
# message, status or fixed code for each cause would tell someone guessing which guess came
# close. Only the log, under the same code, says why.
FAILED = "Admin login failed with error code {code}."


class AdminRefused(Exception):
    """A refused sign-in: the reason, only for the log, and the code the page shows."""

    def __init__(self, reason: str, code: str) -> None:
        super().__init__(FAILED.format(code=code))
        self.reason = reason
        self.code = code


def hash_password(password: str) -> str:
    """The `password_hash` to write in the admin file for this password."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )
    b64 = base64.b64encode
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${b64(salt).decode()}${b64(digest).decode()}"


def parse_hash(value: str) -> tuple[int, int, int, bytes, bytes]:
    """scrypt's N, r and p, the salt and the digest from a `password_hash`; ValueError when it
    isn't one hash_password could have made, with costs scrypt can run."""
    parts = value.split("$")
    if len(parts) != 6 or parts[0] != "scrypt":
        raise ValueError("expected scrypt$N$r$p$salt$digest")
    n, r, p = (int(part) for part in parts[1:4])
    if n < 2 or n & (n - 1) or not 1 <= r <= 32 or not 1 <= p <= 16:
        raise ValueError("N must be a power of two, r from 1 to 32 and p from 1 to 16")
    if 128 * n * r > SCRYPT_MAX_MEMORY:
        raise ValueError("N and r ask for more than 32 MB")
    salt = base64.b64decode(parts[4], validate=True)
    digest = base64.b64decode(parts[5], validate=True)
    if not 8 <= len(salt) <= 64 or not 16 <= len(digest) <= 64:
        raise ValueError("the salt must be 8 to 64 bytes and the digest 16 to 64")
    return n, r, p, salt, digest


_HASH_ERRORS = (ValueError, TypeError, OverflowError, MemoryError)


def _hash_matches(password: str, value: str) -> bool:
    """Whether the password is the one this `password_hash` was made from; raises one of
    _HASH_ERRORS when the hash can't be used."""
    n, r, p, salt, expected = parse_hash(value)
    given = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=len(expected))
    return hmac.compare_digest(given, expected)


def password_matches(password: str, secret: "Secret") -> bool:
    """Whether the password is the one in the file, compared in constant time. A hash that
    can't be used matches nothing, so signing in is refused rather than failing; the dummy hash
    is checked once in its place, so even then the work is one scrypt run (R162)."""
    if secret.kind == "password":
        return hmac.compare_digest(password.encode(), secret.value.encode())
    try:
        return _hash_matches(password, secret.value)
    except _HASH_ERRORS as e:
        # A hash that wasn't made by hash_password, was cut short or was edited by hand.
        logger.error("Admin password hash is not valid", extra={"error": str(e)})
    try:
        _hash_matches(password, _dummy().value)
    except _HASH_ERRORS as e:
        # scrypt itself failing, such as out of memory: refused all the same, never a 500.
        logger.error("Admin dummy password check failed", extra={"error": str(e)})
    return False


@cache
def _dummy() -> "Secret":
    """A hash no password matches, checked when there is nothing real to check, so every
    failure takes about as long as a wrong password against a hash (R162). AdminSignIns makes
    it when the app starts."""
    return Secret("hash", hash_password(secrets.token_urlsafe(32)))


def check_password(password: str, secret: "Secret | None") -> bool:
    """password_matches, with one scrypt run whatever the file holds: none for a plain password
    or no password would answer sooner and tell those causes apart by the time taken."""
    if secret is not None and secret.kind == "hash":
        return password_matches(password, secret)
    password_matches(password, _dummy())
    return secret is not None and password_matches(password, secret)


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
    # The laptop it was made from (R163), or None when no laptops file was in use.
    laptop: str | None = None


class AdminSignIns:
    """Who is signed in as the administrator, by the token in their cookie."""

    def __init__(
        self,
        path: Path,
        timeout_minutes: Callable[[], int] = lambda: TIMEOUT_MINUTES,
        clock: Callable[[], float] = time.monotonic,
        laptops: AdminLaptops | None = None,
    ) -> None:
        self.path = path
        # The allowed laptops (R163): admin-laptops.toml beside the password file by default.
        self.laptops = laptops or AdminLaptops(path.parent / LAPTOPS_FILENAME, clock=clock)
        self.timeout_minutes = timeout_minutes
        self.clock = clock
        self._lock = threading.Lock()
        self._signed_in: dict[str, SignIn] = {}
        # Why each ended sign-in ended, so the page can say so; dropped once read.
        self._ended: dict[str, str] = {}
        # Wrong passwords in a row from each address, and when the last came, so one visitor's
        # guesses make only that visitor wait, never the administrator signing in elsewhere.
        self._wrong: dict[str, tuple[int, float]] = {}
        self._file_seen: tuple[int, int] | None = None
        self._secret: Secret | None = None
        # Made now, not at the first sign-in that needs it, which would run scrypt twice (R162).
        _dummy()

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

    def sign_in(self, password: str, address: str, proof: LaptopProof | None = None) -> str:
        """A new sign-in's token; AdminRefused, with one message for every cause, when the
        password is wrong or not set, the address is waiting after 5 failures (R162), or the
        laptop isn't one listed in the laptops file (R163)."""
        with self._lock:
            now = self.clock()
            failures, failed_at = self._wrong.get(address, (0, 0.0))
            waiting = failures >= WRONG_IN_A_ROW and now - failed_at < WAIT_S
            secret = self.secret()
            # Checked whatever the cause, so the answer takes as long either way.
            matches = check_password(password, secret)
            # Checked whatever the password, so the work is the same whichever fails (R163).
            laptop_refused, laptop = self.laptops.check(proof)
            if waiting:
                # Not counted again, so trying while waiting doesn't make the wait longer.
                self._refuse("waiting", address)
            if secret is None:
                self._note_wrong(address, failures + 1, now)
                self._refuse("no password set", address)
            if laptop_refused:
                self._note_wrong(address, failures + 1, now)
                # password_ok true means someone on an unlisted laptop knows the password.
                self._refuse(laptop_refused, address, laptop=laptop, password_ok=matches)
            if not matches:
                self._note_wrong(address, failures + 1, now)
                self._refuse("wrong password", address)
            self._wrong.pop(address, None)
            token = secrets.token_urlsafe(32)
            self._signed_in[token] = SignIn(now, secret.fingerprint, laptop)
        logger.info("Admin signed in", extra={"address": address, "laptop": laptop})
        return token

    def _note_wrong(self, address: str, wrong: int, now: float) -> None:
        # Moved to the end, so the map runs from the oldest failure to the newest.
        self._wrong.pop(address, None)
        if len(self._wrong) >= WRONG_KEPT:
            # Many addresses guessing: keep only those still counting towards a wait.
            self._wrong = {a: w for a, w in self._wrong.items() if now - w[1] < WAIT_S}
        while len(self._wrong) >= WRONG_KEPT:
            # Still too many, all within the minute (Codex's review): the oldest go first.
            del self._wrong[next(iter(self._wrong))]
        self._wrong[address] = (wrong, now)

    def _refuse(self, reason: str, address: str, **laptop: object) -> NoReturn:
        """Log the cause under a new code, and raise the one answer the page shows. A laptop
        refused (R163) adds its ID and whether the password was right."""
        code = new_reference("A")
        logger.warning(
            "Admin sign-in refused",
            extra={
                "code": code,
                "reason": reason,
                "address": address,
                "failures_in_a_row": self._wrong.get(address, (0, 0.0))[0],
                **laptop,
            },
        )
        raise AdminRefused(reason, code)

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
        """Why the token's sign-in ended, if it did by itself: "inactive", "password changed" or
        "laptop removed"."""
        with self._lock:
            self._current(token)
            return self._ended.pop(token, None) if token else None

    def _current(self, token: str | None) -> SignIn | None:
        """The token's sign-in, ending it first if it has timed out, the password changed or its
        laptop is no longer listed."""
        if not token or token not in self._signed_in:
            return None
        sign_in = self._signed_in[token]
        secret = self.secret()
        if secret is None or secret.fingerprint != sign_in.fingerprint:
            why = "password changed"
        elif not self.laptops.still_allowed(sign_in.laptop):
            why = "laptop removed"
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
