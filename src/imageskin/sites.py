"""One set of app state per site (roadmap R61b, feature item 66).

The app keeps its state in objects it makes when it starts: the conversation, the uploads, the
content and its jobs, Prepare, the reply videos, the customization and more. With many sites,
sharing them would mix one site's conversation, job status or files with another's. So each
site gets an app of its own, made the first time the site is used and kept while the server
runs (`SiteApps`); its background jobs, their callbacks and the files they write belong to it.

What holds no site's data is shared by every site's app (`Service`): the host accounts, the
administrator's sign-in, settings and guidelines, the listed laptops' passes and the network's
month.

Each request is matched to its site by its address (R61): `name.localhost` locally, and
`name.<main_domain>` (me0.ai) on the hosted service. The main address (`localhost`, the main
domain, its `www` and `app` subdomains, or the server's IP address) is the main address's site,
kept in the app's home folder as before; every other site keeps its files in `sites/<name>`
there. The sites are listed in `sites.json`, each with its one host, added with `imageskin site
add`; any other address, or none, is answered Site not found.

A trial site (R61a, R62) has no subdomain: it is at a path of the main address, `/t/<code>`,
with a code of random letters and digits. Its page is served at that path, with every file and
call it makes under it (`/t/<code>/api/...`), so each reaches the site: the path is matched
before the address, and is the site's `root_path`, so its app sees the paths it always has.
"""

import hashlib
import ipaddress
import json
import logging
import os
import re
import secrets
import shutil
import string
import threading
import time
from collections.abc import Awaitable, Callable, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import anyio

from imageskin.acting import ActingAsHost
from imageskin.admin import FILENAME as ADMIN_FILENAME
from imageskin.admin import AdminSignIns
from imageskin.admin_guidelines import EMPTY as NO_ADMIN_GUIDELINES
from imageskin.admin_guidelines import HISTORY_FILE as ADMIN_HISTORY_FILE
from imageskin.admin_guidelines import AdminGuidelinesFile
from imageskin.admin_guidelines import value_of as admin_value_of
from imageskin.admin_laptops import FILENAME as LAPTOPS_FILENAME
from imageskin.admin_laptops import AdminLaptops
from imageskin.admin_settings import AdminSettingsStore
from imageskin.chatgpt_signin import CALLBACK_PATH
from imageskin.config import default_home
from imageskin.customization_history import History
from imageskin.email_sending import Mailer
from imageskin.hosts import DEFAULT_SITE as DEFAULT_SITE
from imageskin.hosts import HOST_COOKIE as HOST_COOKIE
from imageskin.hosts import NO_SITE, TRIAL_USED, HostAccounts, normal_email, trial_cookie
from imageskin.network import NetworkMonth
from imageskin.payments import Stripe
from imageskin.settings_access import SettingsAccess

logger = logging.getLogger(__name__)

# Site names are subdomains (R61): letters, digits and hyphens, not starting or ending with one.
SITE_NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
# Subdomains of the main address that are the main address's site, and names kept for the
# service's own uses, so no site can have them.
MAIN_NAMES = frozenset({"www", "app"})
RESERVED = MAIN_NAMES | {"admin", "api", "trial", "mail", DEFAULT_SITE}
# A trial site's code, and the path it is at (R61a).
TRIAL_CODE_LENGTH = 12
TRIAL_PATH = re.compile(rf"/t/([a-z0-9]{{{TRIAL_CODE_LENGTH}}})(?=/|$)")
# The subdomain a trial site's host picked at their first payment (R63), kept in its record.
PICKED = "subdomain"
NAME_LETTERS = (
    "A site's name can have only letters, digits and hyphens, at most 63 of them, and can't"
    " start or end with a hyphen."
)
NOT_A_TRIAL = "This site has its address already."
NO_SUBDOMAIN_YET = "This site has no address of its own yet: subscribe to pick one."
SUBSCRIBE_FIRST = "Subscribe first: the address is picked once the first payment is made."
SITES_FILE = "sites.json"
SITES_FOLDER = "sites"
# Where a deleted site's folder is moved before it is removed, so a removal that fails is tried
# again (R69a).
DELETED_FOLDER = "deleted-sites"
NOT_FOUND_PAGE = (
    "<!doctype html><meta charset=utf-8><title>Site not found</title>"
    "<p>Site not found. Check the address, or go to the main address.</p>"
)

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
Asgi = Callable[[Scope, Receive, Send], Awaitable[None]]


class SignInReturns:
    """Which site started each Sign in with ChatGPT (R43), and the page to return to. OpenAI
    sends the browser back to the server's own loopback address, the main address's, so the
    callback is matched to its site by the sign-in's `state` (Codex's review of PR #277)."""

    KEEP_S = 15 * 60  # longer than a sign-in takes
    MOST = 100

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._started: dict[str, tuple[str, str, float]] = {}

    def started(self, state: str, site: str, page: str) -> None:
        with self._lock:
            now = self._clock()
            self._started = {s: v for s, v in self._started.items() if now - v[2] < self.KEEP_S}
            while len(self._started) >= self.MOST:
                del self._started[next(iter(self._started))]
            self._started[state] = (site, page, now)

    def site_of(self, state: str) -> str | None:
        with self._lock:
            found = self._started.get(state)
        return None if found is None else found[0]

    def page_of(self, state: str) -> str | None:
        """The page the sign-in was started from, once: the callback returns there."""
        with self._lock:
            found = self._started.pop(state, None)
        return None if found is None else found[1]


class SiteError(Exception):
    """A site can't be added, said in plain words."""


# Stripe's statuses of a subscription in force (R67).
ACTIVE = ("active", "trialing", "past_due")
# Stripe's statuses of a subscription it has ended, which pause its site (R69).
ENDED = ("canceled", "unpaid", "incomplete_expired")
# Why a site whose subscription ended is paused, and when a cancelled one ends (R69).
SUBSCRIPTION_ENDED = "subscription ended"
ENDS_AT = "ends_at"
# Stripe's statuses a subscription never leaves, and when its last event was made (R69).
FINAL = ("canceled", "incomplete_expired")
EVENT_AT = "event_at"
# Every Stripe subscription id a site has had, so an old checkout can't bring one back (R67).
SUBSCRIPTIONS_HAD = "subscriptions_had"
# Why a site is paused once its host asked to delete it (R69a): its content is deleted after
# the days in the admin settings, as any paused site's is.
DELETING = "deleted by its host"
# Why a site its host started again after it was deleted is paused, until paid for (R69c).
RESTARTED = "started again, not yet paid for"


class TrialUsed(SiteError):
    """The email address has had its free trial (R66)."""


def email_key(email: str) -> str:
    """What is kept of an email address that had a trial: a hash, not the address (R66)."""
    return hashlib.sha256(normal_email(email).encode()).hexdigest()


class SiteDirectory:
    """The sites besides the main address's, each with its host, kept in sites.json."""

    def __init__(self, home: Path, hosts: HostAccounts) -> None:
        self.home = home
        self.path = home / SITES_FILE
        self._hosts = hosts
        self._lock = threading.Lock()
        self._seen: tuple[int, int] | None = None
        self._sites: dict[str, dict[str, Any]] = {}
        # A hash of each email address that has had a free trial, kept when its site or account
        # goes, so each has one (R66).
        self._trials_used: list[str] = []
        # The codes of trial sites since deleted (R69a): a trial path is never given again, so a
        # link to a deleted trial can't open another's site (R63).
        self._codes_kept: list[str] = []
        # Whether the last read of sites.json found it and read it whole: only then may
        # `purge_deleted` remove anything (Codex's review of PR #300).
        self._read_whole = False
        # Called with each deleted site's name, so the server forgets its app (R69a).
        self.on_deleted: list[Callable[[str], None]] = []

    def _load(self) -> dict[str, dict[str, Any]]:
        """The sites, read again only when the file has changed. One that can't be read is
        logged and has no sites, so no request reaches a site it may not be."""
        try:
            stat = self.path.stat()
            seen: tuple[int, int] | None = (stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            seen = None
        except OSError as e:
            logger.error("Could not read the sites file", extra={"error": str(e)})
            self._read_whole = False
            return {}
        self._read_whole = seen is not None
        if seen != self._seen:
            sites: dict[str, dict[str, Any]] = {}
            used: list[str] = []
            kept: list[str] = []
            if seen is not None:
                try:
                    data = json.loads(self.path.read_text(encoding="utf-8"))
                    sites, used = data["sites"], data.get("trials_used", [])
                    kept = data.get("codes_kept", [])
                    if not isinstance(sites, dict):
                        raise ValueError("sites must be an object")
                    if not isinstance(used, list):
                        raise ValueError("trials_used must be a list")
                    if not isinstance(kept, list):
                        raise ValueError("codes_kept must be a list")
                except (OSError, ValueError, KeyError, TypeError) as e:
                    logger.error(
                        "Could not read the sites file",
                        extra={"path": str(self.path), "error": str(e)},
                    )
                    self._read_whole = False
                    return {}
            self._sites, self._trials_used, self._seen = sites, used, seen
            self._codes_kept = kept
            self._record_old_trials()
        return self._sites

    def _record_old_trials(self) -> None:
        """With the lock held, as sites.json is read: the host of each trial site made before
        trials were recorded is recorded now, in the file, so a later email change or the
        site's removal can't free the address for another trial (Codex's review of PR #292)."""
        missing = {
            email_key(str(s["host"]))
            for s in self._sites.values()
            if s.get("trial") and email_key(str(s["host"])) not in self._trials_used
        }
        if not missing:
            return
        used = [*self._trials_used, *sorted(missing)]
        try:
            self._write(self._sites, used)
        except OSError as e:
            logger.error("Could not record the trials made before", extra={"error": str(e)})
        self._trials_used = used  # kept in memory either way, and written at the next change
        try:
            stat = self.path.stat()
            self._seen = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            pass
        logger.info("Trials made before recorded", extra={"trials": len(missing)})

    def _write(
        self,
        sites: dict[str, dict[str, Any]],
        used: list[str] | None = None,
        kept: list[str] | None = None,
    ) -> None:
        """Write sites.json, with the lock held, keeping the emails that had a trial and the
        codes of deleted trials."""
        used = self._trials_used if used is None else used
        kept = self._codes_kept if kept is None else kept
        writing = self.path.with_name(f"{SITES_FILE}.writing")
        writing.write_text(
            json.dumps({"sites": sites, "trials_used": used, "codes_kept": kept}, indent=2),
            encoding="utf-8",
        )
        os.replace(writing, self.path)
        self._codes_kept = kept

    def trial_used(self, email: str) -> bool:
        """Whether the email address has had a free trial (R66), even one since gone."""
        with self._lock:
            return self._used(email, self._load())

    def _used(self, email: str, sites: dict[str, dict[str, Any]]) -> bool:
        """With the lock held, the sites just read: whether the address had a trial. Every trial
        site's host is recorded as it is read (`_record_old_trials`)."""
        return email_key(email) in self._trials_used

    def paused(self, name: str) -> str | None:
        """Why the site is paused, such as "cancelled" (R66, R69), or None while it runs."""
        with self._lock:
            site = self._load().get(name)
        return None if site is None else site.get("paused")

    def cancel_trial(self, name: str) -> bool:
        """Pause the trial site as its host cancelled it (R66): whether it was a trial that was
        running. Paused, visitors see a notice and its host can still sign in (R69)."""
        with self._lock:
            sites = dict(self._load())
            site = sites.get(name)
            if site is None or not site.get("trial") or site.get("paused"):
                return False
            sites[name] = {**site, "paused": "cancelled", "paused_at": time.time()}
            self._write(sites)
        logger.info("Trial cancelled", extra={"site": name, "host": site.get("host")})
        return True

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._load())

    def exists(self, name: str) -> bool:
        """Whether a site is at the subdomain `name`."""
        return self.site_at(name) is not None

    def site_at(self, name: str) -> str | None:
        """The site at the subdomain `name`: the site of that name, or the trial site whose host
        picked it at their first payment (R63), which keeps its code as its name inside, so its
        folder and its host's account stay as they are."""
        with self._lock:
            return _site_at(self._load(), name)

    def subdomain(self, site: str) -> str | None:
        """The site's subdomain, or None for a trial site at its path still (R63)."""
        with self._lock:
            found = self._load().get(site)
        return None if found is None else _subdomain(site, found)

    def moved_to(self, code: str) -> str | None:
        """The subdomain a trial path now goes to, once its host picked one (R63)."""
        with self._lock:
            found = self._load().get(code)
        return None if found is None or not found.get(PICKED) else str(found[PICKED])

    def name_problem(self, name: str) -> str | None:
        """Why `name` can't be a site's subdomain, said plainly, or None when it can (R63)."""
        with self._lock:
            return _name_problem(self._load(), name, self._codes_kept)

    def pick_subdomain(self, site: str, name: str) -> str:
        """Give the subscribed trial site its subdomain, picked by its host at their first
        payment (R63): the name. The trial path then goes there, and stays the site's, so no
        other trial gets it. SiteError, said plainly, when the name can't be had or the site
        isn't a subscribed trial."""
        name = name.strip().lower()
        with self._lock:
            sites = dict(self._load())
            found = sites.get(site)
            why = None
            if found is None or not found.get("trial") or found.get(PICKED):
                why = "not a trial", NOT_A_TRIAL
            elif (found.get("subscription") or {}).get("status") not in ACTIVE:
                why = "not subscribed", SUBSCRIBE_FIRST
            else:
                problem = _name_problem(sites, name)
                if problem is not None:
                    why = "name refused", problem
            if why is not None:
                logger.warning(
                    "Subdomain not picked", extra={"site": site, "subdomain": name, "why": why[0]}
                )
                raise SiteError(why[1])
            assert found is not None
            sites[site] = {**found, PICKED: name, "picked_at": time.time()}
            self._write(sites)
        logger.info("Subdomain picked", extra={"site": site, "subdomain": name})
        return name

    def change_subdomain(self, site: str, name: str) -> tuple[str, str]:
        """Change the site's subdomain to another free one, from its Settings (R64): the old
        name and the new. The old name is released at once, so any site can pick it, and its
        address finds no site; a trial path that moved (R63) goes to the new one. The site keeps
        its name inside, so its folder and its host's account stay as they are. SiteError, said
        plainly, when the name can't be had or the site has no subdomain yet."""
        name = name.strip().lower()
        with self._lock:
            sites = dict(self._load())
            found = sites.get(site)
            old = None if found is None else _subdomain(site, found)
            why = None
            if found is None or old is None:
                why = "no subdomain yet", NO_SUBDOMAIN_YET
            elif name == old:
                why = "same name", f"{name} is your site's address already."
            else:
                problem = _name_problem(sites, name)
                if problem is not None:
                    why = "name refused", problem
            if why is not None:
                logger.warning(
                    "Subdomain not changed", extra={"site": site, "subdomain": name, "why": why[0]}
                )
                raise SiteError(why[1])
            assert found is not None and old is not None
            sites[site] = {**found, PICKED: name, "changed_at": time.time()}
            self._write(sites)
        logger.info("Subdomain changed", extra={"site": site, "old": old, "subdomain": name})
        return old, name

    def is_trial(self, code: str) -> bool:
        """Whether a trial site is at `/t/<code>` (R61a), and not yet at the subdomain its host
        picked (R63)."""
        with self._lock:
            site = self._load().get(code)
        return site is not None and bool(site.get("trial")) and not site.get(PICKED)

    def host(self, name: str) -> str | None:
        """The site's host's email."""
        with self._lock:
            site = self._load().get(name)
        return None if site is None else str(site["host"])

    def subscription(self, name: str) -> dict[str, Any] | None:
        """The site's subscription as Stripe's events recorded it (R67): its id, customer and
        status, or None for a site that never subscribed."""
        with self._lock:
            site = self._load().get(name)
        found = None if site is None else site.get("subscription")
        return dict(found) if isinstance(found, dict) else None

    def subscribed(self, name: str) -> bool:
        """Whether the site's subscription is in force (R67)."""
        found = self.subscription(name)
        return found is not None and found.get("status") in ACTIVE

    def subscribe(self, name: str, subscription_id: str, customer: str) -> bool:
        """Record the site's paid subscription from Stripe's event (R67), and unpause it: whether
        the site is there. A checkout for a subscription the site has had before changes nothing,
        whatever its status now: Stripe sends an event again, or late, so a replayed checkout
        mustn't bring back a subscription cancelled since (Codex's review of PR #293). Only a new
        subscription does; the ids the site has had are kept in sites.json, so this holds across
        restarts."""
        with self._lock:
            sites = dict(self._load())
            site = sites.get(name)
            if site is None:
                return False
            kept = site.get("subscription") or {}
            had = list(site.get(SUBSCRIPTIONS_HAD, []))
            if subscription_id in had or kept.get("id") == subscription_id:
                if kept.get("id") != subscription_id or kept.get("status") not in ACTIVE:
                    logger.warning(
                        "Old checkout ignored",
                        extra={
                            "site": name,
                            "subscription": subscription_id,
                            "now": kept.get("id"),
                            "status": kept.get("status"),
                        },
                    )
                return True
            was_paused = "paused" in site
            site = {k: v for k, v in site.items() if k not in ("paused", "paused_at")}
            site["subscription"] = {
                "id": subscription_id,
                "customer": customer,
                "status": "active",
                "since": time.time(),
            }
            site[SUBSCRIPTIONS_HAD] = [*had, subscription_id]
            sites[name] = site
            self._write(sites)
        logger.info(
            "Site subscribed",
            extra={"site": name, "subscription": subscription_id, "was_paused": was_paused},
        )
        return True

    def subscription_changed(
        self,
        subscription_id: str,
        status: str,
        ends_at: float | None = None,
        event_at: float | None = None,
    ) -> str | None:
        """Record a subscription's new status from Stripe's event (R67), and when it ends if it
        is cancelled (R69): the site's name, or None for a subscription no site has. A
        subscription Stripe has ended pauses its site (R69), which visitors then see; its host
        can still sign in and subscribe again. A failed renewal (`past_due`) keeps the site
        working while Stripe tries again, with a notice to its host only; once paid, an `unpaid`
        one that paused the site brings it back.

        Stripe doesn't send events in order, so one older than the last recorded (`event_at`,
        the event's `created`) changes nothing, and nothing changes a subscription once it is
        `canceled` or `incomplete_expired`, for good at Stripe: a late `updated` can't make it
        active again while the site stays paused (Codex's review of PR #299). A new
        subscription, from a new checkout, still subscribes the site."""
        with self._lock:
            sites = dict(self._load())
            name = next(
                (
                    n
                    for n, s in sites.items()
                    if (s.get("subscription") or {}).get("id") == subscription_id
                ),
                None,
            )
            if name is None:
                return None
            site = dict(sites[name])
            kept = site["subscription"]
            last = kept.get(EVENT_AT)
            stale = event_at is not None and isinstance(last, int | float) and event_at < last
            if kept.get("status") in FINAL or stale:
                logger.warning(
                    "Old subscription event ignored",
                    extra={
                        "site": name,
                        "subscription": subscription_id,
                        "status": status,
                        "now": kept.get("status"),
                        "why": "ended for good" if kept.get("status") in FINAL else "older",
                    },
                )
                return name
            site["subscription"] = {
                **kept,
                "status": status,
                ENDS_AT: ends_at,
                EVENT_AT: event_at if event_at is not None else last,
            }
            pause = status in ENDED and not site.get("paused")
            unpause = status in ACTIVE and site.get("paused") == SUBSCRIPTION_ENDED
            if pause:
                site.update(paused=SUBSCRIPTION_ENDED, paused_at=time.time())
            if unpause:
                site = {k: v for k, v in site.items() if k not in ("paused", "paused_at")}
            sites[name] = site
            self._write(sites)
        logger.info(
            "Subscription changed",
            extra={
                "site": name,
                "subscription": subscription_id,
                "status": status,
                "ends_at": ends_at,
            },
        )
        if pause:
            logger.info("Site paused", extra={"site": name, "why": SUBSCRIPTION_ENDED})
        if unpause:
            logger.info("Site unpaused", extra={"site": name, "why": "paid"})
        return name

    def set_ends_at(self, name: str, ends_at: float | None) -> bool:
        """Record when the site's subscription ends, as its host cancelled it or kept it after
        all (R69), before Stripe's event says so too: whether it has a subscription."""
        with self._lock:
            sites = dict(self._load())
            site = sites.get(name)
            if site is None or not site.get("subscription"):
                return False
            sites[name] = {**site, "subscription": {**site["subscription"], ENDS_AT: ends_at}}
            self._write(sites)
        return True

    def set_host(self, name: str, email: str, new_email: str) -> bool:
        """Give the site the host's new email (R62c), if `email` is its host: whether it did."""
        with self._lock:
            sites = dict(self._load())
            site = sites.get(name)
            if site is None or site.get("host") != normal_email(email):
                return False
            sites[name] = {**site, "host": normal_email(new_email)}
            used = self._trials_used
            if site.get("trial") and email_key(new_email) not in used:
                used = [*used, email_key(new_email)]  # the new address has had it too (R66)
            self._write(sites, used)
        logger.info("Site host changed", extra={"site": name, "host": new_email})
        return True

    def deletable(
        self, name: str, paused_before: float | None, subscription_id: str | None
    ) -> str | None:
        """Why the site mustn't be deleted now, or None when it may (R69a): no such site, or,
        for the sweep (`paused_before`), not paused since before then any more, or its
        subscription changed, as a host who paid again unpauses it (Codex's review of PR
        #300)."""
        with self._lock:
            return self._not_deletable(self._load(), name, paused_before, subscription_id)

    @staticmethod
    def _not_deletable(
        sites: dict[str, dict[str, Any]],
        name: str,
        paused_before: float | None,
        subscription_id: str | None,
    ) -> str | None:
        site = sites.get(name)
        if site is None:
            return "no such site"
        if paused_before is None:
            return None
        at = site.get("paused_at")
        if not site.get("paused") or not isinstance(at, int | float) or at >= paused_before:
            return "no longer paused long enough"
        if (site.get("subscription") or {}).get("id") != subscription_id:
            return "subscription changed"
        return None

    def delete(
        self,
        name: str,
        why: str,
        paused_before: float | None = None,
        subscription_id: str | None = None,
    ) -> bool:
        """Delete the site (R69a): its record, so its subdomain is free at once, and its folder,
        with everything in it. A trial's code is kept, never given again. Its host's account is
        kept, with no site, so they can still sign in and resume (R69b); their sign-ins end.
        Any subscription Stripe keeps must be cancelled first (`site_deletion`). False, with
        nothing changed, when it mustn't be deleted (`deletable`), checked again under the lock
        as the record goes, so a payment that came meanwhile always wins, or when its folder
        can't be moved aside.

        The folder is first moved aside, into `deleted-sites`, in the same lock, so the site's
        files leave its address together with its record; it is then removed. A removal that
        fails is retried at each sweep (`purge_deleted`), logged until it succeeds (Codex's
        review of PR #300)."""
        start = time.perf_counter()
        with self._lock:
            sites = dict(self._load())
            refused = self._not_deletable(sites, name, paused_before, subscription_id)
            if refused is not None:
                logger.warning("Site not deleted", extra={"site": name, "why": refused})
                return False
            site = sites.pop(name)
            folder = site_home(name, self.home)
            aside = self.home / DELETED_FOLDER / f"{name}-{time.time_ns()}"
            if folder.exists():
                try:
                    aside.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(folder, aside)
                except OSError as e:
                    logger.error(
                        "Site not deleted",
                        extra={"site": name, "why": "folder not moved aside", "error": str(e)},
                    )
                    return False
            kept = self._codes_kept
            if site.get("trial") and name not in kept:
                kept = [*kept, name]
            try:
                self._write(sites, kept=kept)
            except OSError as e:
                # The record stays, so its folder goes back (Codex's review of PR #300). A crash
                # here instead is put right by `purge_deleted`, which never removes a listed
                # site's folder.
                if aside.exists():
                    os.replace(aside, folder)
                logger.error(
                    "Site not deleted",
                    extra={"site": name, "why": "sites file not written", "error": str(e)},
                )
                return False
            host = str(site.get("host", ""))
            if host and self._hosts.site_of(host) == name:
                # Kept with the host's account, so they can start it again (R69c).
                paid = site.get("subscription") or {}
                self._hosts.site_deleted(
                    host,
                    {
                        "subdomain": _subdomain(name, site),
                        "customer": paid.get("customer") or None,
                        "subscription": paid.get("id") or None,
                    },
                )
        for forget in self.on_deleted:
            forget(name)
        left = self.purge_deleted()
        logger.info(
            "Site deleted",
            extra={
                "site": name,
                "host": host,
                "why": why,
                "subdomain": _subdomain(name, site),
                "trial": bool(site.get("trial")),
                "files_removed": not any(p.name.startswith(f"{name}-") for p in left),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return True

    def purge_deleted(self) -> list[Path]:
        """Remove the folders of deleted sites, moved aside as each was deleted (R69a): the ones
        that couldn't be removed, logged, and tried again at the next sweep.

        A folder moved aside for a site still listed in sites.json, as when the server stopped
        between the move and writing the file, is never removed: it goes back to the site, or,
        when the site has a folder again, is kept and logged (Codex's review of PR #300). A
        site added since with the same name is a new one, made after the folder was moved. While
        sites.json is missing or can't be read, nothing is removed or moved."""
        aside = self.home / DELETED_FOLDER
        left: list[Path] = []
        removable = []
        with self._lock:
            sites = self._load()
            if not self._read_whole and aside.is_dir() and any(aside.iterdir()):
                # A sites file that is missing or can't be read says nothing about which sites
                # are listed, so nothing is removed until it is read again (Codex's review).
                left = sorted(aside.iterdir())
                logger.error(
                    "Deleted sites' files kept: the sites file could not be read",
                    extra={"folders": len(left)},
                )
                return left
            for folder in sorted(aside.iterdir()) if aside.is_dir() else []:
                name, _, moved_ns = folder.name.rpartition("-")
                site = sites.get(name)
                made = site.get("created_at", 0) if site else None
                if (
                    site is None
                    or not moved_ns.isdigit()
                    or not isinstance(made, int | float)
                    or made * 1e9 > int(moved_ns)
                ):
                    removable.append(folder)
                    continue
                home = site_home(name, self.home)
                if home.exists():
                    logger.error(
                        "Deleted site's files kept: the site is still listed",
                        extra={"site": name, "path": str(folder)},
                    )
                    left.append(folder)
                    continue
                try:
                    os.replace(folder, home)
                except OSError as e:
                    logger.error("Site's files not restored", extra={"site": name, "error": str(e)})
                    left.append(folder)
                else:
                    logger.warning("Site's files restored", extra={"site": name})
        for folder in removable:
            try:
                shutil.rmtree(folder)
            except OSError as e:
                logger.error(
                    "Deleted site's files not removed yet",
                    extra={"path": str(folder), "error": str(e)},
                )
                left.append(folder)
            else:
                logger.info("Deleted site's files removed", extra={"path": str(folder)})
        return left

    def pause_to_delete(self, name: str) -> float | None:
        """Pause the site as its host asked to delete it (R69a): when it was paused, from which
        its content is deleted after the admin settings' days, or None for no such site. A site
        paused already keeps the time it paused, so asking again never puts the deletion off.
        Until then its host still signs in, and subscribing again brings it back (R69)."""
        with self._lock:
            sites = dict(self._load())
            site = sites.get(name)
            if site is None:
                return None
            at = site.get("paused_at")
            if not site.get("paused") or not isinstance(at, int | float):
                at = time.time()
            sites[name] = {**site, "paused": DELETING, "paused_at": at}
            self._write(sites)
        logger.info("Site paused", extra={"site": name, "why": DELETING, "paused_at": at})
        return float(at)

    def paused_at(self, name: str) -> float | None:
        """When the site paused, or None while it runs (R69, R69a)."""
        with self._lock:
            site = self._load().get(name) or {}
        at = site.get("paused_at")
        return float(at) if site.get("paused") and isinstance(at, int | float) else None

    def paused_since(self, before: float) -> list[str]:
        """The sites paused before the time `before` (R69a), oldest first."""
        with self._lock:
            sites = self._load()
            paused = [
                (float(s["paused_at"]), n)
                for n, s in sites.items()
                if s.get("paused") and isinstance(s.get("paused_at"), int | float)
            ]
        return [n for at, n in sorted(paused) if at < before]

    def restart(self, email: str) -> str:
        """Start again the site of a host whose site was deleted (R69c): the new site's name.
        It is empty, at its old subdomain if that is still free, or else at a new random one
        its host can change (R64). It is paused until paid for, which is what Resume
        subscription (R69b) does, with the card Stripe keeps for the customer the deleted site
        had; one never paid for subscribes on Stripe's page. Left unpaid, it is deleted as any
        paused site is (R69a). SiteError when the host's site wasn't deleted."""
        deleted = self._hosts.deleted_site(email)
        if deleted is None:
            raise SiteError("Only a host whose site was deleted can start it again.")
        old = deleted.get("subdomain")
        letters = string.ascii_lowercase + string.digits
        with self._lock:
            sites = self._load()
            taken = set(sites) | {str(s[PICKED]) for s in sites.values() if s.get(PICKED)}
            name = str(old) if old else ""
            if not name or _name_problem(sites, name, self._codes_kept) is not None:
                name = ""
                while not name or name in taken or name in self._codes_kept:
                    name = "".join(secrets.choice(letters) for _ in range(TRIAL_CODE_LENGTH))
        self._add(name, email, trial=False)
        with self._lock:
            sites = dict(self._load())
            site = {**sites[name], "paused": RESTARTED, "paused_at": time.time()}
            if deleted.get("customer"):
                # Resume subscription then uses the deleted site's customer and card (R69b).
                site["subscription"] = {
                    "id": deleted.get("subscription"),
                    "customer": deleted["customer"],
                    "status": "canceled",
                }
                if deleted.get("subscription"):
                    site[SUBSCRIPTIONS_HAD] = [deleted["subscription"]]
            sites[name] = site
            self._write(sites)
        logger.info(
            "Site started again",
            extra={"site": name, "host": email, "old_subdomain": old, "same": name == old},
        )
        return name

    def add_trial(self, email: str, finish: bool = False) -> tuple[str, Path]:
        """Add a trial site, at `/t/<code>` with a new random code, with the host as its one
        host: its code and folder. SiteError as for `add`.

        With `finish`, for a host who has a trial site, it is that site, finished where making
        it stopped partway (Codex's review of PR #279): the host's account says it's theirs,
        and its folder is there."""
        host = email.strip().lower()
        with self._lock:
            sites = self._load()
            # A subdomain picked may look like a code, so a new trial's code is neither (R63).
            taken = set(sites) | {str(s[PICKED]) for s in sites.values() if s.get(PICKED)}
            taken |= set(self._codes_kept)  # and never a deleted trial's (R69a)
            own = next(
                (n for n, s in sites.items() if s.get("trial") and s.get("host") == host), None
            )
            if not finish:
                own = None
            if own is not None and self._hosts.site_of(email) != own:
                self._hosts.set_site(email, own)
        if own is not None:
            folder = site_home(own, self.home)
            folder.mkdir(parents=True, exist_ok=True)
            logger.info("Trial site finished", extra={"site": own, "host": host})
            return own, folder
        letters = string.ascii_lowercase + string.digits
        code = ""
        while not code or code in taken:
            code = "".join(secrets.choice(letters) for _ in range(TRIAL_CODE_LENGTH))
        return code, self._add(code, email, trial=True)

    def add(self, name: str, email: str) -> Path:
        """Add the site, with the host as its one host, and return its folder. SiteError when
        the name can't be a subdomain or is taken, or the host isn't one or has a site."""
        return self._add(name.strip().lower(), email, trial=False)

    def _add(self, name: str, email: str, trial: bool) -> Path:
        if not SITE_NAME.fullmatch(name):
            raise SiteError(NAME_LETTERS)
        if name in RESERVED:
            raise SiteError(f"{name} is kept for the service. Choose another name.")
        with self._lock:
            sites = dict(self._load())
            if name in sites or _site_at(sites, name) is not None or name in self._codes_kept:
                raise SiteError(f"There is already a site called {name}.")
            host_site = self._hosts.site_of(email)
            if host_site is None:
                raise SiteError(f"No host has signed up as {email}.")
            # A host whose site was deleted (R69a) may have another.
            if host_site not in (DEFAULT_SITE, NO_SITE):
                raise SiteError(f"{email} is already the host of {host_site}.")
            used = self._trials_used
            if trial:
                if self._used(email, sites):  # one free trial per email address (R66)
                    logger.warning("Trial refused: email already used", extra={"email": email})
                    raise TrialUsed(TRIAL_USED)
                used = [*used, email_key(email)]
            sites[name] = {"host": email.strip().lower(), "created_at": time.time()}
            if trial:
                sites[name]["trial"] = True
            self._write(sites, used)
            self._hosts.set_site(email, name)
        folder = site_home(name, self.home)
        folder.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Site added",
            extra={"site": name, "host": email, "path": str(folder), "trial": trial},
        )
        return folder


def _subdomain(site: str, found: dict[str, Any]) -> str | None:
    """The subdomain of the site `site`, whose record is `found`: the one picked (R63) or
    changed to (R64), its own name, or None for a trial at its path still."""
    if found.get(PICKED):
        return str(found[PICKED])
    return None if found.get("trial") else site


def _site_at(sites: dict[str, dict[str, Any]], name: str) -> str | None:
    """The site at the subdomain `name`, in the sites just read (R61, R63, R64): the one whose
    host picked it, or the site of that name that hasn't changed its subdomain since."""
    picked = next((n for n, s in sites.items() if s.get(PICKED) == name), None)
    if picked is not None:
        return picked
    found = sites.get(name)
    if found is not None and not found.get("trial") and not found.get(PICKED):
        return name
    return None


def _name_problem(
    sites: dict[str, dict[str, Any]], name: str, kept: list[str] | None = None
) -> str | None:
    """Why `name` can't be a subdomain, in the sites just read (R63): its letters, a name kept
    for the service, or one in use, which counts every trial's code, even one moved or deleted
    since (`kept`, R69a). A name a site changed away from, or a deleted site's, is free at once
    (R64, R69a)."""
    if not SITE_NAME.fullmatch(name):
        return NAME_LETTERS
    if name in RESERVED:
        return f"{name} is kept for the service. Choose another name."
    if (
        _site_at(sites, name) is not None
        or sites.get(name, {}).get("trial")
        or name in (kept or [])
    ):
        return f"{name} is taken. Choose another name."
    return None


def site_matcher(
    sites: SiteDirectory, main_domain: str, returns: SignInReturns | None = None
) -> Callable[[Scope], str | None]:
    """Each request's site by its address (R61), or its trial path (R61a): None for an address
    with no site. Sign in with ChatGPT's callback goes to the site that started it."""
    domain = main_domain.strip(".").lower()
    suffixes = (".localhost", f".{domain}")
    # Only these are the main address's: any other name, an empty or a malformed Host header
    # is Site not found, never the main address's site (Codex's review of PR #274).
    main = {"localhost", domain} | {f"{name}.{domain}" for name in MAIN_NAMES}

    def site_of(scope: Scope) -> str | None:
        host = address_of(scope).lower()
        label = next((host[: -len(s)] for s in suffixes if host.endswith(s)), None)
        # The server's own address, as health checks use, or www.localhost and app.localhost.
        if host in main or is_ip_address(host) or label in MAIN_NAMES:
            code = trial_code(scope)
            if code is not None:  # a trial site's path (R61a)
                return code if sites.is_trial(code) else None
            if returns is not None and scope.get("path") == CALLBACK_PATH:
                query = bytes(scope.get("query_string") or b"").decode("latin-1")
                state = parse_qs(query).get("state", [""])[0]
                return returns.site_of(state) or DEFAULT_SITE
            return DEFAULT_SITE
        if label is None:
            return None
        return sites.site_at(label)

    return site_of


def trial_mover(sites: SiteDirectory, main_domain: str) -> Callable[[Scope], str | None]:
    """Where a request to a trial path goes once its host picked a subdomain (R63): the same
    path at the subdomain, with the scheme, port and query kept, or None."""
    domain = main_domain.strip(".").lower()

    def moved(scope: Scope) -> str | None:
        code = trial_code(scope)
        name = None if code is None else sites.moved_to(code)
        if code is None or name is None:
            return None
        headers = dict(scope.get("headers") or [])
        host = bytes(headers.get(b"host", b"")).decode("latin-1")
        address = address_of(scope).lower()
        port = host[len(address) :] if host.lower().startswith(address) else ""
        local = address == "localhost" or address.endswith(".localhost")
        proto = bytes(headers.get(b"x-forwarded-proto", b"")).decode("latin-1")
        scheme = "https" if "https" in (proto, scope.get("scheme")) else "http"
        rest = str(scope.get("path", ""))[len(f"/t/{code}") :] or "/"
        query = bytes(scope.get("query_string") or b"").decode("latin-1")
        where = f"{scheme}://{name}.{'localhost' if local else domain}{port}{rest}"
        return f"{where}?{query}" if query else where

    return moved


def trial_code(scope: Scope) -> str | None:
    """The trial code the request's path starts with (`/t/<code>`), if any."""
    found = TRIAL_PATH.match(str(scope.get("path", "")))
    return found.group(1) if found else None


def trial_cookies_in(headers: list[tuple[bytes, bytes]], code: str) -> list[tuple[bytes, bytes]]:
    """The request's headers with the trial site's host cookie as the host cookie, and no other."""
    own, plain = trial_cookie(code).encode(), HOST_COOKIE.encode()
    kept: list[tuple[bytes, bytes]] = []
    for name, value in headers:
        if name.lower() != b"cookie":
            kept.append((name, value))
            continue
        pairs = []
        for pair in value.split(b";"):
            key = pair.split(b"=", 1)[0].strip()
            if key == plain:
                continue
            pairs.append(plain + pair.strip()[len(own) :] if key == own else pair.strip())
        kept.append((name, b"; ".join(p for p in pairs if p)))
    return kept


def trial_cookies_out(send: Send, code: str, path: str) -> Send:
    """`send`, with the host cookie the site's app sets renamed to its own, for its path."""
    plain, own = f"{HOST_COOKIE}=".encode(), f"{trial_cookie(code)}=".encode()

    async def sending(message: Message) -> None:
        if message["type"] == "http.response.start":
            headers = []
            for name, value in message.get("headers", []):
                if name.lower() == b"set-cookie" and value.startswith(plain):
                    value = own + value[len(plain) :]
                    value = re.sub(rb"(?i)(;\s*path=)[^;]*", rb"\g<1>" + path.encode(), value)
                headers.append((name, value))
            message = {**message, "headers": headers}
        await send(message)

    return sending


def is_ip_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def address_of(scope: Scope) -> str:
    """The request's Host header without its port."""
    headers = dict(scope.get("headers") or [])
    host = bytes(headers.get(b"host", b"")).decode("latin-1")
    if host.startswith("["):  # an IPv6 address
        return host[: host.find("]") + 1]
    return host.rsplit(":", 1)[0]


@dataclass(frozen=True)
class Service:
    """What every site's app shares: none of it is one site's (R61b)."""

    home: Path
    admin_settings: AdminSettingsStore
    admin_sign_ins: AdminSignIns
    host_accounts: HostAccounts
    settings_access: SettingsAccess
    network_month: NetworkMonth
    admin_history: History
    admin_guidelines: AdminGuidelinesFile
    sites: SiteDirectory
    # Sends the service's emails, such as a customer's confirmation (R62b), or writes them to the
    # outbox with no mail service set (R215).
    mailer: Mailer
    sign_in_returns: SignInReturns = field(default_factory=SignInReturns)
    # The administrator acting as a host (R44a); made with the administrator's sign-in.
    acting: ActingAsHost | None = None
    # Subscribing through Stripe (R67), or None when it isn't set up.
    payments: Stripe | None = None


def make_service(
    home: Path,
    admin_file: Path | None = None,
    admin_laptops_file: Path | None = None,
    mailer: Mailer | None = None,
    payments: Stripe | None = None,
) -> Service:
    """The shared part, kept in `home`. The administrator's password file is admin.toml there
    unless `admin_file` says otherwise (R149), and the laptops file is beside it (R163). Without
    a `mailer`, emails go to the outbox in `home`."""
    admin_settings = AdminSettingsStore(home)
    admin_file = admin_file or home / ADMIN_FILENAME
    admin_sign_ins = AdminSignIns(
        admin_file,
        # The minutes before an inactive administrator is signed out (R155), read at each check.
        timeout_minutes=lambda: admin_settings.current.timeout_minutes,
        laptops=AdminLaptops(admin_laptops_file or admin_file.parent / LAPTOPS_FILENAME),
    )
    host_accounts = HostAccounts(home)
    acting = ActingAsHost(admin_sign_ins)
    host_accounts.acting = acting.email_of
    # The administrator's guidelines keep a history of each part, as a host's do (R253).
    admin_history = History(
        home, ADMIN_HISTORY_FILE, admin_value_of, NO_ADMIN_GUIDELINES, "Admin guidelines"
    )
    return Service(
        home=home,
        admin_settings=admin_settings,
        admin_sign_ins=admin_sign_ins,
        host_accounts=host_accounts,
        settings_access=SettingsAccess(host_accounts, admin_sign_ins.laptops),
        network_month=NetworkMonth(home),
        admin_history=admin_history,
        admin_guidelines=AdminGuidelinesFile(home, admin_history.saved),
        sites=SiteDirectory(home, host_accounts),
        mailer=mailer or Mailer(home, None),
        acting=acting,
        payments=payments,
    )


def one_site(scope: Scope) -> str | None:
    """Every request the main address's: for an app with one site, as the tests have."""
    return DEFAULT_SITE


class SiteApps:
    """The server's ASGI app: each request goes to its site's own app, made by `make` the first
    time the site is used, once, however many requests ask for it at the same time."""

    def __init__(
        self,
        make: Callable[[str], Asgi],
        site_of: Callable[[Scope], str | None] = one_site,
        moved: Callable[[Scope], str | None] = lambda scope: None,
    ):
        self._make = make
        # A trial path whose site moved to its subdomain (R63) goes there.
        self._moved = moved
        self._matched: set[str] = set()  # the sites already logged at info level
        self._site_of = site_of
        self._apps: dict[str, Asgi] = {}
        # Held only to look in or change the two dicts, never while a site is made, so a site
        # being made never holds up another (Codex's review of PR #271).
        self._lock = threading.Lock()
        # One lock per site being made, so it is made once however many requests ask for it.
        self._making: dict[str, threading.Lock] = {}

    def app(self, site: str) -> Asgi:
        """The site's app, made now if it hasn't been. Making one can take seconds."""
        with self._lock:
            made = self._apps.get(site)
            if made is not None:
                return made
            making = self._making.setdefault(site, threading.Lock())
        with making:
            with self._lock:  # made by another request while this one waited
                made = self._apps.get(site)
            if made is not None:
                return made
            start = time.perf_counter()
            try:
                made = self._make(site)
            except Exception:
                logger.exception("Site state not made", extra={"site": site})
                raise
            with self._lock:
                self._apps[site] = made
                del self._making[site]
        logger.info(
            "Site state made",
            extra={"site": site, "duration_ms": round((time.perf_counter() - start) * 1000, 1)},
        )
        return made

    def forget(self, site: str) -> None:
        """Drop the deleted site's app (R69a), so a new site given its name later starts
        afresh."""
        with self._lock:
            dropped = self._apps.pop(site, None)
            self._matched.discard(site)
        if dropped is not None:
            logger.info("Site state dropped", extra={"site": site})

    def sites(self) -> list[str]:
        """The sites whose app is made, in the order they were."""
        with self._lock:
            return list(self._apps)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
            return
        moved = self._moved(scope)
        if moved is not None:
            await self._moved_away(scope, send, moved)
            return
        site = self._site_of(scope)
        address = address_of(scope)
        if site is None:
            logger.warning("Site not found", extra={"address": address, "path": scope.get("path")})
            await self._not_found(scope, send)
            return
        trial = trial_code(scope) == site
        if trial:
            prefix = f"/t/{site}"
            if scope["path"] == prefix and scope["type"] == "http":
                # The page's files and calls are relative to it, so its path ends with a slash.
                await self._redirect(scope, send, f"{scope.get('root_path', '')}{prefix}/")
                return
            # The site's app sees the paths it always has (Starlette strips its root_path).
            scope = dict(scope, root_path=f"{scope.get('root_path', '')}{prefix}")
            # And the host's cookie it always has: each trial site's is its own (R62).
            scope["headers"] = trial_cookies_in(scope.get("headers") or [], site)
            send = trial_cookies_out(send, site, f"{scope['root_path']}/")
        with self._lock:
            first = site not in self._matched
            self._matched.add(site)
            made = self._apps.get(site)
        # Once per site at info level, then at debug, as every request is matched.
        logger.log(
            logging.INFO if first else logging.DEBUG,
            "Site matched",
            extra={"site": site, "address": address, **({"trial": site} if trial else {})},
        )
        if made is None:  # made in a thread, so a slow start never holds up the other sites
            made = await anyio.to_thread.run_sync(self.app, site)
        await made(scope, receive, send)

    @staticmethod
    async def _redirect(scope: Scope, send: Send, location: str, query: bool = True) -> None:
        kept = bytes(scope.get("query_string") or b"").decode("latin-1") if query else ""
        target = f"{location}?{kept}" if kept else location
        await send(
            {
                "type": "http.response.start",
                "status": 308,
                "headers": [(b"location", target.encode("latin-1")), (b"content-length", b"0")],
            }
        )
        await send({"type": "http.response.body", "body": b""})

    @staticmethod
    async def _moved_away(scope: Scope, send: Send, moved: str) -> None:
        """A trial path whose site moved to its subdomain (R63). A page is redirected there. A
        call isn't: a tab opened before the move makes it from the trial path's origin, and a
        redirect to another origin would be blocked without the trial path's cookie anyway, so
        it is answered here with the site's new address (`X-Site-Moved`), which the page goes
        to (`site-path.ts`) (Codex's review of PR #297)."""
        rest = str(scope.get("path", ""))[len("/t/") + TRIAL_CODE_LENGTH :]
        call = rest.startswith("/api/")
        logger.info(
            "Trial path moved",
            extra={"path": scope.get("path"), "to": moved, "call": call or None},
        )
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4404})
            return
        if not call:
            await SiteApps._redirect(scope, send, moved, query=False)
            return
        # The site's home page there: the address without the call's path and query.
        home = moved.split("?", 1)[0].removesuffix(rest) + "/"
        body = json.dumps({"detail": f"This site has moved to {home}", "moved_to": home}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 409,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"x-site-moved", home.encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    async def _not_found(scope: Scope, send: Send) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4404})
            return
        await send(
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [(b"content-type", b"text/html; charset=utf-8")],
            }
        )
        await send({"type": "http.response.body", "body": NOT_FOUND_PAGE.encode()})

    @staticmethod
    async def _lifespan(receive: Receive, send: Send) -> None:
        """The sites' apps need nothing at start or stop, so both are answered at once."""
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return


def site_home(site: str, home: Path | None = None) -> Path:
    """The folder a site's files are kept in: the main address's is the app's home folder, as
    before R61, and every other site's is a folder of its own in it."""
    home = home or default_home()
    if site == DEFAULT_SITE:
        return home
    if not SITE_NAME.fullmatch(site):
        raise ValueError(f"{site!r} is not a site's name.")
    return home / SITES_FOLDER / site
