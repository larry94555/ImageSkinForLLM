"""Participant accounts (roadmap R46, item 32): a participant signs up on a site with an email and
a password, and a cookie keeps them signed in on that browser.

Each site keeps its own participants in `participants.json` in its folder, so an account belongs
to one site, as R65 asks: the same email signed up on two sites is two accounts, with two
histories. Each account records its site, so R260 can widen an account to the host's sites.

An account has an `id`, made once and never shown, that names the participant's conversation
(R65a) in place of a browser's visitor cookie, so their history follows them from browser to
browser. The file keeps a hash of each sign-in's token, never the token itself."""

import hashlib
import json
import logging
import os
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from imageskin.admin import Secret, check_password, hash_password
from imageskin.hosts import BAD_EMAIL, EMAIL, MIN_PASSWORD, SHORT_PASSWORD, WRONG, normal_email

logger = logging.getLogger(__name__)

FILENAME = "participants.json"
COOKIE = "imageskin_participant"
COOKIE_MAX_AGE = 400 * 24 * 60 * 60  # as long as browsers keep a cookie
SESSIONS_KEPT_S = COOKIE_MAX_AGE  # a sign-in older than its cookie is dropped
TAKEN = "That email address already has an account here. Sign in instead."
UNREADABLE = "Accounts can't be read right now. Please try again later."
# Each signed-in participant's Teach me, Quiz me and assessment under way (R41h to R41j), kept
# for their account rather than their browser, one file each, named by the account's id.
PROGRESS_FOLDER = "participant_progress"
PROGRESS_KEYS = frozenset({"lesson", "quiz", "assessment"})
MAX_PROGRESS_BYTES = 64_000
BAD_PROGRESS = "That progress can't be kept."


class ParticipantRefused(Exception):
    """A refused sign-up or sign-in: the words for the page, and the reason for the log."""

    def __init__(self, message: str, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class ParticipantsUnreadable(Exception):
    """The file is there but can't be used, so nothing reads or writes it until it is fixed."""

    def __init__(self) -> None:
        super().__init__(UNREADABLE)


@dataclass(frozen=True)
class Participant:
    email: str
    id: str  # names their conversation (R65a); never sent to the browser
    site: str  # the site the account belongs to (R46), which R260 widens to the host
    created_at: float


def _token_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class ParticipantAccounts:
    """The site's participants, and who is signed in, by the token in their cookie."""

    def __init__(self, home: Path, site: str, clock: Callable[[], float] = time.time) -> None:
        self.path = home / FILENAME
        self.site = site
        self.clock = clock
        self._lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {"participants": {}, "sessions": {}}
        except OSError as e:
            logger.error(
                "Could not read the participants file",
                extra={"path": str(self.path), "error": str(e)},
            )
            raise ParticipantsUnreadable() from e
        try:
            data = json.loads(text)
            if not all(isinstance(data.get(k), dict) for k in ("participants", "sessions")):
                raise ValueError("participants and sessions must be objects")
        except (ValueError, TypeError, AttributeError) as e:
            logger.error(
                "Could not read the participants file",
                extra={"path": str(self.path), "error": str(e)},
            )
            raise ParticipantsUnreadable() from e
        return dict(data)

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Written beside it, then put in its place, so a read never sees half a file.
        part = self.path.with_suffix(".part")
        part.write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.chmod(part, 0o600)  # it holds the password hashes
        os.replace(part, self.path)

    def _new_sign_in(self, data: dict[str, Any], email: str) -> str:
        token = secrets.token_urlsafe(32)
        now = self.clock()
        sessions = {
            k: v
            for k, v in data["sessions"].items()
            if now - float(v.get("at", 0)) < SESSIONS_KEPT_S
        }
        sessions[_token_key(token)] = {"email": email, "at": now}
        data["sessions"] = sessions
        return token

    def _refuse(self, message: str, reason: str, action: str, email: str) -> ParticipantRefused:
        logger.warning(
            f"Participant {action} refused",
            extra={"reason": reason, "email": email, "site": self.site},
        )
        return ParticipantRefused(message, reason)

    def sign_up(self, email: str, password: str) -> str:
        """Make an account on this site and sign it in, returning the sign-in's token;
        ParticipantRefused when the email isn't one, the password is too short or the email
        already has an account here."""
        start = time.perf_counter()
        email = normal_email(email)
        if not EMAIL.fullmatch(email):
            raise self._refuse(BAD_EMAIL, "not an email address", "sign-up", email)
        if len(password) < MIN_PASSWORD:
            raise self._refuse(SHORT_PASSWORD, "password too short", "sign-up", email)
        password_hash = hash_password(password)  # before the lock, as it takes about 50 ms
        with self._lock:
            data = self._load()
            if email in data["participants"]:
                raise self._refuse(TAKEN, "email already signed up", "sign-up", email)
            data["participants"] = {
                **data["participants"],
                email: {
                    "password_hash": password_hash,
                    "id": secrets.token_urlsafe(24),
                    "site": self.site,
                    "created_at": self.clock(),
                },
            }
            token = self._new_sign_in(data, email)
            self._save(data)
        logger.info(
            "Participant signed up",
            extra={
                "email": email,
                "site": self.site,
                "participants": len(data["participants"]),
                "took_ms": round((time.perf_counter() - start) * 1000),
            },
        )
        return token

    def sign_in(self, email: str, password: str) -> str:
        """A new sign-in's token; ParticipantRefused, with the same words for an unknown email
        and a wrong password, taking as long either way."""
        email = normal_email(email)
        with self._lock:
            account = self._load()["participants"].get(email)
        secret = Secret("hash", account["password_hash"]) if account else None
        if not (check_password(password, secret) and account is not None):
            raise self._refuse(WRONG, "wrong email or password", "sign-in", email)
        with self._lock:
            data = self._load()
            if email not in data["participants"]:
                raise self._refuse(WRONG, "account removed meanwhile", "sign-in", email)
            token = self._new_sign_in(data, email)
            self._save(data)
        logger.info("Participant signed in", extra={"email": email, "site": self.site})
        return token

    def participant(self, token: str | None) -> Participant | None:
        """Who the token is signed in as on this site, or None (also while the file can't be
        read, so no one is signed in until it can)."""
        if not token:
            return None
        try:
            with self._lock:
                data = self._load()
        except ParticipantsUnreadable:
            return None
        session = data["sessions"].get(_token_key(token))
        if not session or self.clock() - float(session.get("at", 0)) >= SESSIONS_KEPT_S:
            return None
        account = data["participants"].get(session["email"])
        if not account:
            return None
        return Participant(
            session["email"],
            str(account["id"]),
            str(account.get("site", self.site)),
            float(account["created_at"]),
        )

    def progress(self, participant: Participant) -> dict[str, Any]:
        """The participant's lesson, quiz and assessment under way, as their browser last sent
        them; none for a file that is missing or can't be read (logged)."""
        path = self.path.parent / PROGRESS_FOLDER / f"{participant.id}.json"
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            logger.error(
                "Could not read a participant's progress",
                extra={"email": participant.email, "site": self.site, "error": str(e)},
            )
            return {}
        if not isinstance(saved, dict):
            return {}
        return {k: v for k, v in saved.items() if k in PROGRESS_KEYS}

    def save_progress(self, participant: Participant, progress: dict[str, Any]) -> None:
        """Keep the participant's progress in place of what was kept; ParticipantRefused for
        anything but a lesson, quiz and assessment, or more than MAX_PROGRESS_BYTES."""
        text = json.dumps(progress)
        if set(progress) - PROGRESS_KEYS or len(text.encode()) > MAX_PROGRESS_BYTES:
            raise self._refuse(BAD_PROGRESS, "progress not kept", "progress", participant.email)
        folder = self.path.parent / PROGRESS_FOLDER
        folder.mkdir(parents=True, exist_ok=True)
        part = folder / f"{participant.id}.part"
        part.write_text(text, encoding="utf-8")
        os.replace(part, folder / f"{participant.id}.json")
        logger.debug(
            "Participant progress kept",
            extra={"email": participant.email, "site": self.site, "kept": sorted(progress)},
        )

    def sign_out(self, token: str | None) -> None:
        """End the sign-in, on the server, so the cookie is no good even if it is sent again."""
        if not token:
            return
        with self._lock:
            data = self._load()
            session = data["sessions"].pop(_token_key(token), None)
            if session is not None:
                self._save(data)
        if session is not None:
            logger.info(
                "Participant signed out", extra={"email": session["email"], "site": self.site}
            )
