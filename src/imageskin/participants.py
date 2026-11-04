"""Participant accounts (roadmap R46, item 32): a participant signs up on a site with an email and
a password, and a cookie keeps them signed in on that browser.

A participant signs up to a host, not to one site (R260): a site with a host keeps its
participants in `participants.json` in the host's folder (R258), shared by all their sites, so
one account and one sign-in work on each of them. A site with no host, such as the main address,
keeps its own in its folder. Another host's sites never know the account.

An account has an `id`, made once and never shown, that names the participant's conversation
(R65a) in place of a browser's visitor cookie, so their history follows them from browser to
browser. History and Teach me progress stay with each site (R65): each site's folder keeps its
own, by that id. The file keeps a hash of each sign-in's token, never the token itself."""

import hashlib
import json
import logging
import os
import secrets
import threading
import time
from collections.abc import Callable, Mapping
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
    site: str  # the site they are signed in on; the account is the host's (R260)
    created_at: float


def _token_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# One lock for each file, shared by every site's accounts that use it: a host's sites all read
# and write the host's one file (R260).
_locks: dict[Path, threading.Lock] = {}
_locks_lock = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    with _locks_lock:
        return _locks.setdefault(path.resolve(), threading.Lock())


class ParticipantAccounts:
    """The site's participants, and who is signed in, by the token in their cookie. `home` is the
    site's folder, which keeps their progress; `accounts` the folder whose file keeps the
    accounts: the host's, shared by their sites (R260), or the site's own by default."""

    def __init__(
        self,
        home: Path,
        site: str,
        clock: Callable[[], float] = time.time,
        accounts: Path | None = None,
        cookie: str = COOKIE,
    ) -> None:
        self.home = home
        # A host's participants have a cookie of their own, named for the host's folder, so the
        # sign-in another host's sites are sent is never read there (R260).
        self.cookie = cookie
        self.path = (accounts or home) / FILENAME
        self.site = site
        self.clock = clock
        self._lock = _lock_for(self.path)
        self._progress_lock = threading.Lock()

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
                    "site": self.site,  # where it was made; it works on all the host's
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

    def token_in(self, cookies: Mapping[str, str]) -> tuple[str | None, bool]:
        """The browser's sign-in token, and whether it came in the site's own cookie from before
        R260, which then is to be swapped for the host's. That old cookie is taken only for a
        sign-in made on this very site and moved to the host's file, so it never signs anyone
        in across sites."""
        token = cookies.get(self.cookie)
        if token or self.cookie == COOKIE:
            return token, False
        old = cookies.get(COOKIE)
        if old and self.participant(old, moved_here=True):
            return old, True
        return None, False

    def participant(self, token: str | None, moved_here: bool = False) -> Participant | None:
        """Who the token is signed in as on this site, or None (also while the file can't be
        read, so no one is signed in until it can). `moved_here` takes only a sign-in moved
        from this site's own file (R260)."""
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
        if moved_here and session.get("moved_from") != self.site:
            return None
        account = data["participants"].get(session["email"])
        if not account:
            return None
        # An account joined from two sites (R260) keeps each one's own conversation there.
        ids = account.get("site_ids")
        own = ids.get(self.site) if isinstance(ids, dict) else None
        return Participant(
            session["email"],
            str(own or account["id"]),
            self.site,
            float(account["created_at"]),
        )

    def progress(self, participant: Participant) -> dict[str, Any]:
        """The participant's lesson, quiz and assessment under way, as their browser last sent
        them; none for a file that is missing or can't be read (logged)."""
        path = self.home / PROGRESS_FOLDER / f"{participant.id}.json"
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
        folder = self.home / PROGRESS_FOLDER
        # A file of its own for each save, and one save at a time, so two browsers of the same
        # account saving at once never trip over each other; the last one kept wins (Codex's
        # review of PR #308).
        part = folder / f"{participant.id}.{secrets.token_hex(6)}.part"
        with self._progress_lock:
            folder.mkdir(parents=True, exist_ok=True)
            try:
                part.write_text(text, encoding="utf-8")
                os.replace(part, folder / f"{participant.id}.json")
            except OSError as e:
                # A full disk or a folder that can't be written: said in the log, with whose.
                logger.error(
                    "Could not keep a participant's progress",
                    extra={"email": participant.email, "site": self.site, "error": str(e)},
                )
                raise
            finally:
                part.unlink(missing_ok=True)
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


def move_site_participants(site_home: Path, accounts: ParticipantAccounts) -> int:
    """Join the site's own participants from before R260 into the host's file, keeping their
    passwords and sign-ins, and each one's conversation and progress on this site; then remove
    the site's file. An email already in the host's file keeps its password there, and this
    site's conversation stays theirs. Answers how many were moved; nothing when there is no file,
    and nothing is removed when the host's file can't be read or written, so it is tried again."""
    old = site_home / FILENAME
    if not old.exists() or old.resolve() == accounts.path.resolve():
        return 0
    start = time.perf_counter()
    site = ParticipantAccounts(site_home, accounts.site)
    try:
        with site._lock:
            theirs = site._load()
        with accounts._lock:
            data = accounts._load()
            people = {**data["participants"]}
            joined = 0
            for email, account in theirs["participants"].items():
                here = people.get(email)
                if here is None:
                    people[email] = {**account, "site": account.get("site", accounts.site)}
                elif here.get("id") != account.get("id"):
                    ids = dict(here.get("site_ids") or {})
                    ids.setdefault(accounts.site, account["id"])
                    people[email] = {**here, "site_ids": ids}
                    joined += 1
            # Each sign-in says where it came from, so the site's old cookie is read only there.
            moved = {k: {**v, "moved_from": accounts.site} for k, v in theirs["sessions"].items()}
            sessions = {**moved, **data["sessions"]}
            accounts._save({**data, "participants": people, "sessions": sessions})
    except (ParticipantsUnreadable, OSError) as e:
        logger.error(
            "Participants not moved to the host",
            extra={"site": accounts.site, "error": str(e)},
        )
        return 0
    old.unlink(missing_ok=True)
    logger.info(
        "Participants moved to the host",
        extra={
            "site": accounts.site,
            "moved": len(theirs["participants"]),
            "joined": joined,
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )
    return len(theirs["participants"])
