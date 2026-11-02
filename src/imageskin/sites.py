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
`name.<main_domain>` (me0.ai) on the hosted service. The main address, and its `www` and `app`
subdomains, are the main address's site, kept in the app's home folder as before; every other
site keeps its files in `sites/<name>` there. The sites are listed in `sites.json`, each with its
one host, added with `imageskin site add`; an address with no site is answered Site not found.
"""

import json
import logging
import os
import re
import threading
import time
from collections.abc import Awaitable, Callable, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio

from imageskin.admin import FILENAME as ADMIN_FILENAME
from imageskin.admin import AdminSignIns
from imageskin.admin_guidelines import EMPTY as NO_ADMIN_GUIDELINES
from imageskin.admin_guidelines import HISTORY_FILE as ADMIN_HISTORY_FILE
from imageskin.admin_guidelines import AdminGuidelinesFile
from imageskin.admin_guidelines import value_of as admin_value_of
from imageskin.admin_laptops import FILENAME as LAPTOPS_FILENAME
from imageskin.admin_laptops import AdminLaptops
from imageskin.admin_settings import AdminSettingsStore
from imageskin.config import default_home
from imageskin.customization_history import History
from imageskin.hosts import DEFAULT_SITE as DEFAULT_SITE
from imageskin.hosts import HostAccounts
from imageskin.network import NetworkMonth
from imageskin.settings_access import SettingsAccess

logger = logging.getLogger(__name__)

# Site names are subdomains (R61): letters, digits and hyphens, not starting or ending with one.
SITE_NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
# Subdomains of the main address that are the main address's site, and names kept for the
# service's own uses, so no site can have them.
MAIN_NAMES = frozenset({"www", "app"})
RESERVED = MAIN_NAMES | {"admin", "api", "trial", "mail", DEFAULT_SITE}
SITES_FILE = "sites.json"
SITES_FOLDER = "sites"
NOT_FOUND_PAGE = (
    "<!doctype html><meta charset=utf-8><title>Site not found</title>"
    "<p>Site not found. Check the address, or go to the main address.</p>"
)

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
Asgi = Callable[[Scope, Receive, Send], Awaitable[None]]


class SiteError(Exception):
    """A site can't be added, said in plain words."""


class SiteDirectory:
    """The sites besides the main address's, each with its host, kept in sites.json."""

    def __init__(self, home: Path, hosts: HostAccounts) -> None:
        self.home = home
        self.path = home / SITES_FILE
        self._hosts = hosts
        self._lock = threading.Lock()
        self._seen: tuple[int, int] | None = None
        self._sites: dict[str, dict[str, Any]] = {}

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
            return {}
        if seen != self._seen:
            sites: dict[str, dict[str, Any]] = {}
            if seen is not None:
                try:
                    sites = json.loads(self.path.read_text(encoding="utf-8"))["sites"]
                    if not isinstance(sites, dict):
                        raise ValueError("sites must be an object")
                except (OSError, ValueError, KeyError, TypeError) as e:
                    logger.error(
                        "Could not read the sites file",
                        extra={"path": str(self.path), "error": str(e)},
                    )
                    return {}
            self._sites, self._seen = sites, seen
        return self._sites

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._load())

    def exists(self, name: str) -> bool:
        with self._lock:
            return name in self._load()

    def host(self, name: str) -> str | None:
        """The site's host's email."""
        with self._lock:
            site = self._load().get(name)
        return None if site is None else str(site["host"])

    def add(self, name: str, email: str) -> Path:
        """Add the site, with the host as its one host, and return its folder. SiteError when
        the name can't be a subdomain or is taken, or the host isn't one or has a site."""
        name = name.strip().lower()
        if not SITE_NAME.fullmatch(name):
            raise SiteError(
                "A site's name can have only letters, digits and hyphens, at most 63 of them,"
                " and can't start or end with a hyphen."
            )
        if name in RESERVED:
            raise SiteError(f"{name} is kept for the service. Choose another name.")
        with self._lock:
            sites = dict(self._load())
            if name in sites:
                raise SiteError(f"There is already a site called {name}.")
            host_site = self._hosts.site_of(email)
            if host_site is None:
                raise SiteError(f"No host has signed up as {email}.")
            if host_site != DEFAULT_SITE:
                raise SiteError(f"{email} is already the host of {host_site}.")
            sites[name] = {"host": email.strip().lower(), "created_at": time.time()}
            writing = self.path.with_name(f"{SITES_FILE}.writing")
            writing.write_text(json.dumps({"sites": sites}, indent=2), encoding="utf-8")
            os.replace(writing, self.path)
            self._hosts.set_site(email, name)
        folder = site_home(name, self.home)
        folder.mkdir(parents=True, exist_ok=True)
        logger.info("Site added", extra={"site": name, "host": email, "path": str(folder)})
        return folder


def site_matcher(sites: SiteDirectory, main_domain: str) -> Callable[[Scope], str | None]:
    """Each request's site by its address (R61): None for an address with no site."""
    suffixes = (".localhost", f".{main_domain.strip('.').lower()}")

    def site_of(scope: Scope) -> str | None:
        host = address_of(scope).lower()
        label = next((host[: -len(s)] for s in suffixes if host.endswith(s)), None)
        if label is None or label in MAIN_NAMES:
            return DEFAULT_SITE  # localhost, the main domain or the server's own IP address
        return label if sites.exists(label) else None

    return site_of


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


def make_service(
    home: Path, admin_file: Path | None = None, admin_laptops_file: Path | None = None
) -> Service:
    """The shared part, kept in `home`. The administrator's password file is admin.toml there
    unless `admin_file` says otherwise (R149), and the laptops file is beside it (R163)."""
    admin_settings = AdminSettingsStore(home)
    admin_file = admin_file or home / ADMIN_FILENAME
    admin_sign_ins = AdminSignIns(
        admin_file,
        # The minutes before an inactive administrator is signed out (R155), read at each check.
        timeout_minutes=lambda: admin_settings.current.timeout_minutes,
        laptops=AdminLaptops(admin_laptops_file or admin_file.parent / LAPTOPS_FILENAME),
    )
    host_accounts = HostAccounts(home)
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
    )


def one_site(scope: Scope) -> str | None:
    """Every request the main address's: for an app with one site, as the tests have."""
    return DEFAULT_SITE


class SiteApps:
    """The server's ASGI app: each request goes to its site's own app, made by `make` the first
    time the site is used, once, however many requests ask for it at the same time."""

    def __init__(
        self, make: Callable[[str], Asgi], site_of: Callable[[Scope], str | None] = one_site
    ):
        self._make = make
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

    def sites(self) -> list[str]:
        """The sites whose app is made, in the order they were."""
        with self._lock:
            return list(self._apps)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
            return
        site = self._site_of(scope)
        address = address_of(scope)
        if site is None:
            logger.warning("Site not found", extra={"address": address, "path": scope.get("path")})
            await self._not_found(scope, send)
            return
        with self._lock:
            first = site not in self._matched
            self._matched.add(site)
            made = self._apps.get(site)
        # Once per site at info level, then at debug, as every request is matched.
        logger.log(
            logging.INFO if first else logging.DEBUG,
            "Site matched",
            extra={"site": site, "address": address},
        )
        if made is None:  # made in a thread, so a slow start never holds up the other sites
            made = await anyio.to_thread.run_sync(self.app, site)
        await made(scope, receive, send)

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
