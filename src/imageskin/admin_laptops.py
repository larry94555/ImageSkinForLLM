"""Only the laptops listed on the host can sign in as the administrator (roadmap R163, item 133).

A web server never sees a laptop, only a browser, so each laptop's browser makes a key pair once
(WebCrypto, ECDSA P-256, not exportable; R164) and the laptop ID is a fingerprint of its public
key. At each sign-in the server gives a one-time challenge, the browser signs it, and the server
checks the signature and that the key's ID is in `admin-laptops.toml`, beside the password file.
The file is read again whenever it changes, like R149's password file. With no file, any laptop
can sign in; a file that lists none, or can't be read, lets none in.
"""

import base64
import hashlib
import logging
import secrets
import threading
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.serialization import load_der_public_key

logger = logging.getLogger(__name__)

FILENAME = "admin-laptops.toml"
# A challenge lasts this long, and is good for one sign-in.
CHALLENGE_S = 60.0
# Challenges kept at most: past this, the expired go, then the oldest, so asking for many can't
# use up the memory.
CHALLENGES_KEPT = 1000

# The reasons a laptop is refused, for the log only (R162: the page is told none of them).
NO_PROOF = "no laptop proof"
EXPIRED = "challenge expired"
BAD_PROOF = "bad laptop proof"
NOT_LISTED = "laptop not listed"


def laptop_id(public_key: bytes) -> str:
    """The laptop's ID from its public key (SPKI, DER): the first 20 characters of the SHA-256
    in base32, in groups of four, such as LT-3F9K-Q7MZ-AB2C-D4EF-GH5J. R164's browser code makes
    the same ID from the same key."""
    digest = base64.b32encode(hashlib.sha256(public_key).digest()).decode()[:20]
    return "LT-" + "-".join(digest[i : i + 4] for i in range(0, 20, 4))


@dataclass(frozen=True)
class LaptopProof:
    """What the browser sends with the password: its public key (SPKI, DER, in base64), the
    challenge it was given, and its signature over the challenge (WebCrypto's raw r and s, 64
    bytes, in base64)."""

    public_key: str
    challenge: str
    signature: str


def _signature_der(raw: bytes) -> bytes:
    """WebCrypto's ECDSA signature (r and s, 32 bytes each) as the DER `cryptography` checks."""
    if len(raw) != 64:
        raise ValueError("a P-256 signature is 64 bytes")
    return encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))


def verify(proof: LaptopProof) -> str:
    """The laptop's ID when the signature over the challenge is its key's; ValueError when not."""
    try:
        der = base64.b64decode(proof.public_key, validate=True)
        key = load_der_public_key(der)
        if not isinstance(key, ec.EllipticCurvePublicKey) or key.curve.name != "secp256r1":
            raise ValueError("not a P-256 key")
        signature = _signature_der(base64.b64decode(proof.signature, validate=True))
        key.verify(signature, proof.challenge.encode(), ec.ECDSA(hashes.SHA256()))
    except (ValueError, TypeError, InvalidSignature, UnsupportedAlgorithm) as e:
        raise ValueError(str(e) or type(e).__name__) from e
    return laptop_id(der)


def read_laptops(path: Path) -> frozenset[str] | None:
    """The laptop IDs listed in the file; None when there is no file, so any laptop can sign in.
    A file that can't be read lists none, so no laptop can sign in until it is fixed."""
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return None
    except (OSError, tomllib.TOMLDecodeError) as e:
        logger.error(
            "Could not read the admin laptops file", extra={"path": str(path), "error": str(e)}
        )
        return frozenset()
    entries = data.get("laptop", [])
    if not isinstance(entries, list):
        logger.error(
            "Could not read the admin laptops file",
            extra={"path": str(path), "error": "laptop must be a list of [[laptop]] entries"},
        )
        return frozenset()
    ids = set()
    for entry in entries:
        value = entry.get("id") if isinstance(entry, dict) else None
        if isinstance(value, str) and value.strip():
            ids.add(value.strip().upper())
        else:
            logger.error(
                "Admin laptops file has an entry with no id",
                extra={
                    "path": str(path),
                    "laptop_name": entry.get("name") if isinstance(entry, dict) else None,
                },
            )
    return frozenset(ids)


class AdminLaptops:
    """The allowed laptops file, read again when it changes, and the one-time challenges."""

    def __init__(self, path: Path, clock: Callable[[], float] = time.monotonic) -> None:
        self.path = path
        self.clock = clock
        self._lock = threading.Lock()
        self._file_seen: tuple[int, int] | None = None
        self._allowed: frozenset[str] | None = None
        # Each challenge given, with when it was given, oldest first.
        self._challenges: dict[str, float] = {}

    def allowed(self) -> frozenset[str] | None:
        """The listed laptop IDs, or None with no file; read again only when the file changed."""
        with self._lock:
            try:
                stat = self.path.stat()
                seen: tuple[int, int] | None = (stat.st_mtime_ns, stat.st_size)
            except OSError:
                seen = None
            if seen != self._file_seen:
                before = self._allowed
                self._allowed = read_laptops(self.path) if seen else None
                self._file_seen = seen
                logger.info(
                    "Admin laptops file read",
                    extra={
                        "path": str(self.path),
                        "exists": self._allowed is not None,
                        "laptops": len(self._allowed or ()),
                        "changed": before != self._allowed,
                    },
                )
            return self._allowed

    def challenge(self) -> str:
        """A new one-time challenge, good for CHALLENGE_S seconds."""
        with self._lock:
            now = self.clock()
            if len(self._challenges) >= CHALLENGES_KEPT:
                self._challenges = {
                    c: at for c, at in self._challenges.items() if now - at < CHALLENGE_S
                }
            while len(self._challenges) >= CHALLENGES_KEPT:
                del self._challenges[next(iter(self._challenges))]
            value = secrets.token_urlsafe(32)
            self._challenges[value] = now
            return value

    def _take(self, challenge: str) -> bool:
        """Whether the challenge was given and is still good; it can't be used again."""
        with self._lock:
            given = self._challenges.pop(challenge, None)
            return given is not None and self.clock() - given < CHALLENGE_S

    def check(self, proof: LaptopProof | None) -> tuple[str | None, str | None]:
        """Why the laptop may not sign in (None when it may), and its ID when the proof is good.
        With no file, any laptop may, and a proof sent anyway is not looked at."""
        allowed = self.allowed()
        if allowed is None:
            return None, None
        if proof is None:
            return NO_PROOF, None
        if not self._take(proof.challenge):
            return EXPIRED, None
        try:
            found = verify(proof)
        except ValueError as e:
            logger.info("Admin laptop proof not valid", extra={"error": str(e)})
            return BAD_PROOF, None
        return (None if found in allowed else NOT_LISTED), found

    def listed(self, proof: LaptopProof | None) -> bool:
        """Whether this laptop may sign in, so the Settings page shows the sign-in only where it
        can work (Larry, 2026-10-29). Not a sign-in: it neither signs in nor counts as a failure."""
        refused, laptop = self.check(proof)
        logger.info(
            "Admin laptop checked",
            extra={"laptop": laptop, "listed": refused is None, "reason": refused},
        )
        return refused is None

    def still_allowed(self, laptop: str | None) -> bool:
        """Whether a sign-in made from this laptop (None: made with no file) may go on."""
        allowed = self.allowed()
        return allowed is None or (laptop is not None and laptop in allowed)
