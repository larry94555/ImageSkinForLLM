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

from fastapi import HTTPException

from imageskin.admin import Secret, check_password, hash_password
from imageskin.admin_settings import Choice

logger = logging.getLogger(__name__)

FILENAME = "hosts.json"
# An acting token (R44a) starts with this; acting.py makes them.
ACT_PREFIX = "act-"
HOST_COOKIE = "imageskin_host"  # the cookie that keeps a host signed in (R188)
# The site at the main address (R61): every host's until they are given a site of their own.
DEFAULT_SITE = "default"
SITE = "site"  # the host's site, kept with the host; none for the main address's
# Every site of a host with several (R256): `site` is then the one they used last, which a
# sign-in at another address goes to (R255). A host from before has none: their one `site`.
SITES = "sites"
# The name of the host's folder beside their sites, where their PDFs are kept once (R258).
LIBRARY = "library"
# The name participants and visitors see for the host, in place of their email (R259). A host
# with none is shown the part of their email before the @.
DISPLAY_NAME = "display_name"
MAX_DISPLAY_NAME = 60
NO_DISPLAY_NAME = "Enter a display name, such as Dr. Smith."
LONG_DISPLAY_NAME = f"The display name can be at most {MAX_DISPLAY_NAME} characters."


def sites_in(account: dict[str, Any]) -> list[str]:
    """The host's sites (R256): the list kept with them, which always has their `site`, or, for
    a host from before, their one site. None once their site was deleted (R69a)."""
    site = str(account.get(SITE, DEFAULT_SITE))
    if site == NO_SITE:
        return []
    listed = [s for s in account.get(SITES) or [] if isinstance(s, str) and s != NO_SITE]
    return listed if site in listed else [site, *listed]


# The host's site was deleted (R69a): their account is kept, so they can sign in and resume
# (R69b), but no site is theirs. Never a site's name, which has letters or digits only.
NO_SITE = "-"
# Said only once the site's content is gone, after it was paused for the admin settings' days:
# while it is only paused, its host signs in and resumes it (R69b). A new, empty site is what
# they can start (R69c; Larry, on PR #302).
SITE_DELETED = (
    "Your site was paused for {days} days, so its content was deleted. You can start a new, "
    "empty site at the same address if it is still free."
)


def site_deleted_words(days: int = 30) -> str:
    """What signing in says once the host's site was deleted, after `days` paused (R69c)."""
    return SITE_DELETED.format(days=days)


# What a host's deleted site was (R69c): its subdomain, and Stripe's customer and last
# subscription, so starting it again uses the card Stripe keeps for them.
DELETED = "deleted_site"
# A host who signs in at another site's address goes to their own with a one-time link (R255),
# good for this long *(default)*; at most this many are kept, the oldest dropped first.
SIGN_IN_LINK_S = 60.0
SIGN_IN_LINKS_KEPT = 1000
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
# A customer who signs up at the main address confirms their email from a link before managing
# their site (R62b); hosts from before have no "confirmed" and count as confirmed.
CONFIRMED = "confirmed"
CONFIRM_KEY = "confirm"  # the hash of the link's token, while unconfirmed
CONFIRM_AT = "confirm_at"  # when the link was made
CONFIRM_DAYS = 7  # how long a confirmation link works
CONFIRM_AGAIN_S = 60  # how long before Send it again sends another
TOO_SOON = "The email was sent less than a minute ago. Please wait a moment and try again."
# Forgot password (R62a): a one-time link to set a new password, kept as its hash.
RESET_KEY = "reset"
RESET_AT = "reset_at"
RESET_HOURS = 1  # how long a link to set a new password works
# Changing the email (R62c): the new address, confirmed from a link sent to it, kept as its hash.
NEW_EMAIL = "new_email"
CHANGE_KEY = "change"
CHANGE_AT = "change_at"
CHANGE_HOURS = 24  # how long a link to confirm a new email works
SAME_EMAIL = "That is already your email address."
# A host's own Allow or Deny of a custom image and a custom voice (R242), kept with the host.
CUSTOM_IMAGE = "custom_image"
CUSTOM_VOICE = "custom_voice"
# A host the administrator disabled (R44c): their site is read-only for them, and only the
# administrator acting as them (R44a) changes it. Kept with the host; hosts from before have none.
DISABLED = "disabled"
# Said to a sign-up whose email address has had its one free trial (R66).
TRIAL_USED = "This email address has already had a free trial. Sign up with another address."
DISABLED_WORDS = "Changes to this site are turned off by the administrator."
CHANGES = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# The changing calls a disabled host still makes: signing in and out, a forgotten password,
# confirming their email, the administrator's own calls at the main address, acting as a host,
# and asking whether Settings is shown, which changes nothing.
STILL_OPEN = (
    "/api/host/sign-in",
    "/api/host/sign-out",
    "/api/host/forgot",
    "/api/host/reset",
    "/api/host/confirm",
    "/api/host/act-as/",
    "/api/host/sites/",  # opening another of their sites changes nothing (R256)
    "/api/admin/",
    "/api/settings/access",
)


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


class SiteDeleted(HostRefused):
    """The right password, but the host's site was deleted (R69a): they can start it again
    (R69c). Told only once the password is checked."""

    def __init__(self) -> None:
        super().__init__(site_deleted_words(), "site deleted")


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


def default_display_name(email: str) -> str:
    """What a host who hasn't set a display name is called (R259): their email before the @."""
    return normal_email(email).split("@", 1)[0]


def checked_display_name(name: str) -> str:
    """The display name as kept, with its spaces tidied (R259); HostRefused when it is empty or
    too long, or holds a line break or other control character."""
    shown = " ".join(name.split())
    if not shown or not shown.isprintable():
        raise HostRefused(NO_DISPLAY_NAME, "no display name")
    if len(shown) > MAX_DISPLAY_NAME:
        raise HostRefused(LONG_DISPLAY_NAME, "display name too long")
    return shown


def token_key(token: str) -> str:
    """What the file keeps for a sign-in's token."""
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Host:
    email: str
    created_at: float
    site: str = DEFAULT_SITE  # the site the host signs in to and manages (R61)
    confirmed: bool = True  # whether they confirmed their email (R62b)
    acting: bool = False  # the administrator acting as the host (R44a)
    disabled: bool = False  # turned off by the administrator: read-only for the host (R44c)


class HostAccounts:
    """The hosts signed up on this site, and who is signed in, by the token in their cookie."""

    def __init__(self, home: Path, clock: Callable[[], float] = time.time) -> None:
        self.path = home / FILENAME
        self.clock = clock
        self._lock = threading.Lock()
        self._file_seen: tuple[int, int] | None = None
        self._data: dict[str, Any] = {"hosts": {}, "sessions": {}}
        # The host an acting token acts as, while its administrator is signed in (R44a).
        self.acting: Callable[[str], str | None] | None = None
        # One-time sign-in links to a host's own site, by their hash: the email and when (R255).
        self._links: dict[str, tuple[str, float, str]] = {}

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

    def confirmation(self, email: str, again: bool = False) -> str | None:
        """A new confirmation link's token for an unconfirmed host (R62b), replacing any made
        before; None when the host is confirmed. With `again`, HostRefused (TOO_SOON) when the
        last one was made less than a minute ago."""
        email = normal_email(email)
        token = secrets.token_urlsafe(32)
        with self._lock:
            data = self._load()
            account = data["hosts"].get(email)
            if account is None:
                raise HostRefused(WRONG, "no such host")
            if account.get(CONFIRMED, True):
                return None
            since = self.clock() - float(account.get(CONFIRM_AT, 0))
            if again and since < CONFIRM_AGAIN_S:
                logger.warning(
                    "Confirmation email not sent again",
                    extra={"email": email, "why": "too soon", "seconds": round(since)},
                )
                raise HostRefused(TOO_SOON, "too soon")
            account = {**account, CONFIRM_KEY: token_key(token), CONFIRM_AT: self.clock()}
            self._save({**data, "hosts": {**data["hosts"], email: account}})
        return token

    def confirm(self, token: str) -> str | None:
        """Confirm the host whose link this is (R62b): their email, or None when the link is
        unknown, used or more than CONFIRM_DAYS old."""
        key = token_key(token)
        with self._lock:
            data = self._load()
            found = (str(e) for e, a in data["hosts"].items() if a.get(CONFIRM_KEY) == key)
            email = next(found, None)
            if email is None:
                logger.warning("Host email not confirmed", extra={"why": "unknown link"})
                return None
            account = {**data["hosts"][email]}
            age_days = (self.clock() - float(account.get(CONFIRM_AT, 0))) / 86400
            if age_days > CONFIRM_DAYS:
                logger.warning(
                    "Host email not confirmed",
                    extra={"email": email, "why": "link too old", "days": round(age_days, 1)},
                )
                return None
            account[CONFIRMED] = True
            account.pop(CONFIRM_KEY, None)
            account.pop(CONFIRM_AT, None)
            self._save({**data, "hosts": {**data["hosts"], email: account}})
        logger.info("Host email confirmed", extra={"email": email})
        return email

    def sign_up(
        self,
        email: str,
        password: str,
        address: str,
        confirm: bool = False,
        display_name: str | None = None,
    ) -> str:
        """Make a host account and sign it in, returning the sign-in's token; HostRefused when
        the email isn't one, the password is too short, the display name isn't one (R259) or
        the email is already signed up. With `confirm`, the host is unconfirmed until they use
        a confirmation link (R62b). With no `display_name`, the host is shown by their email
        before the @ until they set one."""
        start = time.perf_counter()
        email = normal_email(email)
        if not EMAIL.fullmatch(email):
            self._refuse(BAD_EMAIL, "not an email address", "sign-up", email, address)
        if len(password) < MIN_PASSWORD:
            self._refuse(SHORT_PASSWORD, "password too short", "sign-up", email, address)
        shown = None
        if display_name is not None and display_name.strip():
            try:
                shown = checked_display_name(display_name)
            except HostRefused as e:
                self._refuse(str(e), e.reason, "sign-up", email, address)
        # Hashed before the lock, as it takes about 50 ms.
        password_hash = hash_password(password)
        with self._lock:
            data = self._load()
            if email in data["hosts"]:
                self._refuse(EMAIL_TAKEN, "email already signed up", "sign-up", email, address)
            data = {**data, "hosts": {**data["hosts"]}, "sessions": {**data["sessions"]}}
            data["hosts"][email] = {"password_hash": password_hash, "created_at": self.clock()}
            if shown is not None:
                data["hosts"][email][DISPLAY_NAME] = shown
            if confirm:
                data["hosts"][email][CONFIRMED] = False
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
        if account and account.get(SITE) == NO_SITE:
            # Told only once the password is checked, as for another site's host; they can
            # start their site again (R69c).
            logger.warning(
                "Host sign-in failed",
                extra={"reason": "site deleted", "email": email, "address": address},
            )
            raise SiteDeleted()
        if account and site not in sites_in(account):
            # Sent to the one they used last (R255, R256).
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
            data = self._used(data, email, site)
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

    def _used(self, data: dict[str, Any], email: str, site: str) -> dict[str, Any]:
        """`data` with `site` as the host's site used last (R256), which a sign-in at another
        address then goes to (R255). Unchanged for a host with one site."""
        account = data["hosts"][email]
        if account.get(SITE, DEFAULT_SITE) == site or len(sites_in(account)) < 2:
            return data
        account = {**account, SITES: sites_in(account), SITE: site}
        return {**data, "hosts": {**data["hosts"], email: account}}

    def sign_in_link(self, email: str) -> str:
        """A one-time link token that signs the host in at their own site (R255), made once their
        password is checked at another site's address, whose cookie their site can't read. It
        holds the password's hash, so a password reset before it is opened ends it too."""
        link = secrets.token_urlsafe(32)
        now = self.clock()
        email = normal_email(email)
        with self._lock:
            password_hash = str(self._load()["hosts"].get(email, {}).get("password_hash", ""))
            kept = {k: v for k, v in self._links.items() if now - v[1] <= SIGN_IN_LINK_S}
            while len(kept) >= SIGN_IN_LINKS_KEPT:
                del kept[min(kept, key=lambda k: kept[k][1])]
            kept[token_key(link)] = (email, now, password_hash)
            self._links = kept
        return link

    def open_sign_in_link(self, link: str, site: str, address: str) -> str | None:
        """A new sign-in's token for the link's host, opened at their own `site`; the link then
        works no more. None when it is unknown, used, too old, not this site's host's, or the
        password was changed since it was made (Codex's review of PR #295)."""
        with self._lock:
            found = self._links.pop(token_key(link), None)
            why = None
            if found is None:
                why = "unknown link"
            elif self.clock() - found[1] > SIGN_IN_LINK_S:
                why = "link too old"
            else:
                data = self._load()
                account = data["hosts"].get(found[0])
                if account is None:
                    why = "no such host"
                elif account.get("password_hash") != found[2]:
                    why = "password changed"
                elif site not in sites_in(account):
                    why = "another site's host"
                else:
                    data = {**data, "sessions": {**data["sessions"]}}
                    data = self._used(data, found[0], site)
                    token = self._new_sign_in(data, found[0])
                    self._save(data)
        if why is not None or found is None:
            logger.warning("Host sign-in link refused", extra={"why": why, "address": address})
            return None
        logger.info(
            "Host signed in",
            extra={"email": found[0], "address": address, "from": "another address"},
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

    def host(
        self, token: str | None, site: str | None = None, unconfirmed: bool = False
    ) -> Host | None:
        """The host the token is signed in as, or None; with `site`, only that site's host
        (R61), so another site's sign-in counts as none. A host who hasn't confirmed their email
        counts as none too (R62b), but with `unconfirmed`, which only their sign-in's own calls
        use: its session and sending the email again."""
        if not token:
            return None
        acting = token.startswith(ACT_PREFIX)
        # The administrator acting as a host (R44a) is that host, with all of their abilities.
        acting_as = self.acting(token) if acting and self.acting else None
        if acting and acting_as is None:
            return None
        with self._lock:
            try:
                data = self._load()
            except HostsUnreadable:
                return None  # signed in as no one until the file can be read
            session = {"email": acting_as} if acting_as else data["sessions"].get(token_key(token))
            account = session and data["hosts"].get(session["email"])
        if not account:
            return None
        # Signed in on each of their sites (R256): here, the one at this address.
        theirs = sites_in(account)
        host = Host(
            session["email"],
            account["created_at"],
            site if site in theirs else account.get(SITE, DEFAULT_SITE),
            acting or bool(account.get(CONFIRMED, True)),
            acting,
            account.get(DISABLED) is True,
        )
        if site is not None and site not in theirs:
            logger.warning(
                "Host sign-in refused: another site",
                extra={"email": host.email, "site": site, "host_site": host.site},
            )
            return None
        if not (host.confirmed or unconfirmed):
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

    def reset_link(self, email: str) -> str | None:
        """Forgot password (R62a): a new one-time link's token to set the host's password,
        replacing any made before; None when there is no such host, or the last link was made
        less than a minute ago."""
        email = normal_email(email)
        token = secrets.token_urlsafe(32)
        with self._lock:
            data = self._load()
            account = data["hosts"].get(email)
            since = self.clock() - float(account.get(RESET_AT, 0)) if account else 0.0
            why = "no such host" if account is None else "too soon"
            if account is None or since < CONFIRM_AGAIN_S:
                logger.warning("Password reset link not made", extra={"email": email, "why": why})
                return None
            account = {**account, RESET_KEY: token_key(token), RESET_AT: self.clock()}
            self._save({**data, "hosts": {**data["hosts"], email: account}})
        return token

    def reset_with(self, token: str, password: str) -> str | None:
        """Set the password of the host whose Forgot password link this is (R62a), once, ending
        every sign-in they have: their email, or None when the link is unknown, used or more
        than RESET_HOURS old. The link came to their email, so it confirms it too (R62b)."""
        if len(password) < MIN_PASSWORD:
            raise HostRefused(SHORT_PASSWORD, "password too short")
        password_hash = hash_password(password)
        key = token_key(token)
        with self._lock:
            data = self._load()
            found = (str(e) for e, a in data["hosts"].items() if a.get(RESET_KEY) == key)
            email = next(found, None)
            if email is None:
                logger.warning("Host password not reset", extra={"why": "unknown link"})
                return None
            account = {**data["hosts"][email]}
            age_hours = (self.clock() - float(account.get(RESET_AT, 0))) / 3600
            if age_hours > RESET_HOURS:
                logger.warning(
                    "Host password not reset",
                    extra={"email": email, "why": "link too old", "hours": round(age_hours, 2)},
                )
                return None
            account["password_hash"] = password_hash
            for done in (RESET_KEY, RESET_AT, CONFIRM_KEY, CONFIRM_AT):
                account.pop(done, None)
            if CONFIRMED in account:
                account[CONFIRMED] = True
            sessions = {k: v for k, v in data["sessions"].items() if v["email"] != email}
            ended = len(data["sessions"]) - len(sessions)
            hosts = {**data["hosts"], email: account}
            self._save({**data, "hosts": hosts, "sessions": sessions})
        logger.info(
            "Host password reset", extra={"email": email, "sign_ins_ended": ended, "by": "link"}
        )
        return email

    def password_is(self, email: str, password: str) -> bool:
        """Whether this is the host's password, taking as long either way (R62c)."""
        with self._lock:
            account = self._load()["hosts"].get(normal_email(email))
        secret = Secret("hash", account["password_hash"]) if account else None
        return check_password(password, secret) and account is not None

    def email_change(self, email: str, new_email: str) -> str:
        """A link's token to confirm `new_email` as the host's (R62c), replacing any asked for
        before; HostRefused when it isn't an email, is theirs already or another host's, or the
        last link was made less than a minute ago."""
        email, new_email = normal_email(email), normal_email(new_email)
        if not EMAIL.fullmatch(new_email):
            raise HostRefused(BAD_EMAIL, "not an email address")
        if new_email == email:
            raise HostRefused(SAME_EMAIL, "same email")
        token = secrets.token_urlsafe(32)
        with self._lock:
            data = self._load()
            account = data["hosts"].get(email)
            if account is None:
                raise HostRefused(WRONG, "no such host")
            if new_email in data["hosts"]:
                raise HostRefused(EMAIL_TAKEN, "email already signed up")
            if self.clock() - float(account.get(CHANGE_AT, 0)) < CONFIRM_AGAIN_S:
                raise HostRefused(TOO_SOON, "too soon")
            account = {
                **account,
                NEW_EMAIL: new_email,
                CHANGE_KEY: token_key(token),
                CHANGE_AT: self.clock(),
            }
            self._save({**data, "hosts": {**data["hosts"], email: account}})
        logger.info("Email change asked for", extra={"email": email, "new_email": new_email})
        return token

    def email_change_of(self, token: str) -> tuple[str, str] | None:
        """The host's email and the new one a change link is for (R62c), without using it;
        None, logged, when it is unknown, used, more than CHANGE_HOURS old, or the new email
        has become another host's."""
        key = token_key(token)
        with self._lock:
            hosts = self._load()["hosts"]
        email = next((str(e) for e, a in hosts.items() if a.get(CHANGE_KEY) == key), None)
        if email is None:
            logger.warning("Host email not changed", extra={"why": "unknown link"})
            return None
        account = hosts[email]
        new_email = str(account[NEW_EMAIL])
        hours = (self.clock() - float(account.get(CHANGE_AT, 0))) / 3600
        why = (
            "link too old" if hours > CHANGE_HOURS else "email taken" if new_email in hosts else ""
        )
        if why:
            logger.warning("Host email not changed", extra={"email": email, "why": why})
            return None
        return email, new_email

    def change_email(self, token: str) -> tuple[str, str] | None:
        """Use the change link (R62c): the account, with its sign-ins, moves to the new email,
        which counts as confirmed, as the link came to it. The emails, or None as for
        email_change_of."""
        found = self.email_change_of(token)
        if found is None:
            return None
        email, new_email = found
        with self._lock:
            data = self._load()
            account = data["hosts"].get(email)
            if (
                account is None
                or account.get(CHANGE_KEY) != token_key(token)
                or new_email in data["hosts"]
            ):
                logger.warning("Host email not changed", extra={"email": email, "why": "changed"})
                return None
            moved = {
                k: v for k, v in account.items() if k not in (NEW_EMAIL, CHANGE_KEY, CHANGE_AT)
            }
            if CONFIRMED in moved:
                moved[CONFIRMED] = True
                moved.pop(CONFIRM_KEY, None)
                moved.pop(CONFIRM_AT, None)
            hosts = {e: a for e, a in data["hosts"].items() if e != email} | {new_email: moved}
            sessions = {
                k: {**v, "email": new_email} if v["email"] == email else v
                for k, v in data["sessions"].items()
            }
            self._save({**data, "hosts": hosts, "sessions": sessions})
        logger.info("Host email changed", extra={"email": email, "new_email": new_email})
        return email, new_email

    def reset_password(self, email: str, password: str) -> bool:
        """Set a host's password from the server, as a last resort beside Forgot password (R62a),
        ending every sign-in the host has; False when there is no such host."""
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
            email: {
                **{k: v for k, v in account.items() if k in ("created_at", SITE)},
                SITES: sites_in(account),
            }
            for email, account in hosts.items()
        }

    def site_of(self, email: str) -> str | None:
        """The host's site (R61), the one used last of several (R256), or None when there is no
        such host."""
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
            account.pop(SITES, None)  # their one site from now on (R256)
            if site != NO_SITE:
                account.pop(DELETED, None)  # a site of their own again (R69c)
            if site == DEFAULT_SITE:
                account.pop(SITE, None)
            else:
                account[SITE] = site
            sessions = {k: v for k, v in data["sessions"].items() if v["email"] != email}
            self._save({**data, "hosts": {**data["hosts"], email: account}, "sessions": sessions})
        logger.info("Host site set", extra={"email": email, "site": site, "old_site": old})
        return True

    def library_of(self, email: str, make: bool = True) -> str | None:
        """The name of the host's folder, where their PDFs are kept once for all their sites
        (R258), given them the first time it is asked for unless `make` is False. None when
        there is no such host, or it has none and none was made."""
        email = normal_email(email)
        with self._lock:
            data = self._load()
            account = data["hosts"].get(email)
            if account is None:
                return None
            if account.get(LIBRARY) or not make:
                return str(account[LIBRARY]) if account.get(LIBRARY) else None
            key = secrets.token_hex(8)
            self._save({**data, "hosts": {**data["hosts"], email: {**account, LIBRARY: key}}})
        logger.info("Host's PDF folder named", extra={"email": email, "library": key})
        return key

    def display_name_of(self, email: str) -> str | None:
        """The name participants and visitors see for the host (R259): the one they set, else
        their email before the @; None when there is no such host."""
        email = normal_email(email)
        with self._lock:
            account = self._load()["hosts"].get(email)
        if account is None:
            return None
        return str(account.get(DISPLAY_NAME) or default_display_name(email))

    def set_display_name(self, email: str, name: str) -> str | None:
        """Change the host's display name (R259), returning it as kept; HostRefused when it
        isn't one, None when there is no such host."""
        email = normal_email(email)
        shown = checked_display_name(name)
        with self._lock:
            data = self._load()
            account = data["hosts"].get(email)
            if account is None:
                logger.warning("Display name not set", extra={"email": email, "why": "no host"})
                return None
            old = account.get(DISPLAY_NAME)
            account = {**account, DISPLAY_NAME: shown}
            self._save({**data, "hosts": {**data["hosts"], email: account}})
        logger.info(
            "Host display name set",
            extra={"email": email, "display_name": shown, "was_set": old is not None},
        )
        return shown

    def sites_of(self, email: str) -> list[str]:
        """Every site of the host (R256), the one used last first; none for no such host or
        once their site was deleted (R69a)."""
        with self._lock:
            account = self._load()["hosts"].get(normal_email(email))
        if account is None:
            return []
        theirs = sites_in(account)
        last = str(account.get(SITE, DEFAULT_SITE))
        return [last, *[s for s in theirs if s != last]] if last in theirs else theirs

    def add_site(self, email: str, site: str) -> bool:
        """Give the host another site (R256): their sign-ins are good on it at once, and the
        site they used last stays so. A host whose only site is the main address's, or whose
        site was deleted, is given this one in its place, as `set_site` does. False when there
        is no such host."""
        email = normal_email(email)
        with self._lock:
            data = self._load()
            account = data["hosts"].get(email)
            if account is None:
                logger.warning("Host site not added", extra={"email": email, "why": "no host"})
                return False
            if account.get(SITE, DEFAULT_SITE) in (DEFAULT_SITE, NO_SITE):
                theirs = None
            else:
                theirs = sites_in(account)
                if site not in theirs:
                    account = {**account, SITES: [*theirs, site]}
                    self._save({**data, "hosts": {**data["hosts"], email: account}})
        if theirs is None:
            return self.set_site(email, site)
        logger.info(
            "Host site added", extra={"email": email, "site": site, "sites": len(theirs) + 1}
        )
        return True

    def remove_site(self, email: str, site: str) -> bool:
        """Take one of a host's several sites from them, as it is deleted (R256): whether they
        keep another, which becomes the one used last if it was this one. Their sign-ins stay
        good on the others. False, with nothing changed, when it was their only site."""
        email = normal_email(email)
        with self._lock:
            data = self._load()
            account = data["hosts"].get(email)
            theirs = [] if account is None else sites_in(account)
            left = [s for s in theirs if s != site]
            if account is None or not left or len(left) == len(theirs):
                return False
            last = account.get(SITE, DEFAULT_SITE)
            account = {**account, SITES: left, SITE: left[0] if last == site else last}
            self._save({**data, "hosts": {**data["hosts"], email: account}})
        logger.info("Host site removed", extra={"email": email, "site": site, "left": len(left)})
        return True

    def release_site(self, site: str, email: str) -> list[str]:
        """Take the site from every host but `email` before it is given to them (R256): the
        hosts it was taken from. A host whose deletion of it didn't reach this file (it failed
        to save, or the server stopped) would otherwise be signed in on another host's new site
        of that name (Codex's review of PR #303). Their sign-ins end, and they keep their other
        sites, or have none, as when a site is deleted (R69a). HostsUnreadable, or the error
        saving, when it can't be done; the site is then not given."""
        email = normal_email(email)
        with self._lock:
            data = self._load()
            hosts = dict(data["hosts"])
            taken = [
                other
                for other, account in hosts.items()
                if other != email
                and (site in sites_in(account) or account.get(SITE, DEFAULT_SITE) == site)
            ]
            if not taken:
                return []
            for other in taken:
                account = {**hosts[other]}
                left = [s for s in sites_in(account) if s != site]
                account.pop(SITES, None)
                if len(left) > 1:
                    account[SITES] = left
                account[SITE] = left[0] if left else NO_SITE
                hosts[other] = account
            sessions = {k: v for k, v in data["sessions"].items() if v["email"] not in taken}
            self._save({**data, "hosts": hosts, "sessions": sessions})
        logger.warning("Site taken from its old host", extra={"site": site, "hosts": len(taken)})
        return taken

    def site_deleted(self, email: str, deleted: dict[str, Any]) -> bool:
        """The host's site was deleted (R69a): their sign-ins end, their account is kept with
        no site, and what the site was is kept with it, so they can start it again (R69c)."""
        email = normal_email(email)
        with self._lock:
            data = self._load()
            if email not in data["hosts"]:
                return False
            account = {**data["hosts"][email], SITE: NO_SITE, DELETED: deleted}
            account.pop(SITES, None)
            sessions = {k: v for k, v in data["sessions"].items() if v["email"] != email}
            self._save({**data, "hosts": {**data["hosts"], email: account}, "sessions": sessions})
        logger.info("Host's site deleted", extra={"email": email, **deleted})
        return True

    def deleted_site(self, email: str) -> dict[str, Any] | None:
        """What the host's deleted site was (R69c), or None while they have a site."""
        with self._lock:
            account = self._load()["hosts"].get(normal_email(email)) or {}
        found = account.get(DELETED) if account.get(SITE) == NO_SITE else None
        return dict(found) if isinstance(found, dict) else None

    def is_disabled(self, email: str) -> bool:
        """Whether the administrator disabled the host (R44c); False for no such host."""
        with self._lock:
            account = self._load()["hosts"].get(normal_email(email), {})
        return account.get(DISABLED) is True

    def set_disabled(self, email: str, disabled: bool) -> bool:
        """Disable the host or enable them again (R44c). False when there is no such host.
        Their sign-ins are kept: a disabled host still reads their site."""
        email = normal_email(email)
        with self._lock:
            data = self._load()
            if email not in data["hosts"]:
                logger.warning("Host not disabled", extra={"email": email, "why": "no host"})
                return False
            account = {**data["hosts"][email]}
            was = account.get(DISABLED) is True
            if disabled:
                account[DISABLED] = True
            else:
                account.pop(DISABLED, None)
            self._save({**data, "hosts": {**data["hosts"], email: account}})
        logger.info(
            "Host disabled" if disabled else "Host enabled",
            extra={"email": email, "changed": was != disabled},
        )
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


def refuse_if_disabled(method: str, path: str, host: Host) -> None:
    """Refuse a change by a host the administrator disabled (R44c), with 403; the administrator
    acting as them (R44a) changes the site as before. Reading, and the calls in STILL_OPEN, stay
    open. Every host and Settings check calls this, so every changing route is covered."""
    if not host.disabled or host.acting or method not in CHANGES:
        return
    root_free = re.sub(r"^/t/[^/]+", "", path)  # a trial site's path (R61a)
    if any(root_free.startswith(p) for p in STILL_OPEN):
        return
    logger.warning(
        "Host change refused",
        extra={"email": host.email, "why": "disabled", "method": method, "path": path},
    )
    raise HTTPException(status_code=403, detail=DISABLED_WORDS)


def _choice(value: object) -> Choice:
    """A stored choice, or None for anything else, so a hand-edited file can't allow by mistake."""
    return value if value in ("allow", "deny") else None
