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

import ipaddress
import json
import logging
import os
import re
import secrets
import string
import threading
import time
from collections.abc import Awaitable, Callable, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

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
from imageskin.chatgpt_signin import CALLBACK_PATH
from imageskin.config import default_home
from imageskin.customization_history import History
from imageskin.email_sending import Mailer
from imageskin.hosts import DEFAULT_SITE as DEFAULT_SITE
from imageskin.hosts import HOST_COOKIE as HOST_COOKIE
from imageskin.hosts import HostAccounts, trial_cookie
from imageskin.network import NetworkMonth
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
        """Whether a site is at the subdomain `name`."""
        with self._lock:
            site = self._load().get(name)
        return site is not None and not site.get("trial")

    def is_trial(self, code: str) -> bool:
        """Whether a trial site is at `/t/<code>` (R61a)."""
        with self._lock:
            site = self._load().get(code)
        return site is not None and bool(site.get("trial"))

    def host(self, name: str) -> str | None:
        """The site's host's email."""
        with self._lock:
            site = self._load().get(name)
        return None if site is None else str(site["host"])

    def add_trial(self, email: str, finish: bool = False) -> tuple[str, Path]:
        """Add a trial site, at `/t/<code>` with a new random code, with the host as its one
        host: its code and folder. SiteError as for `add`.

        With `finish`, for a host who has a trial site, it is that site, finished where making
        it stopped partway (Codex's review of PR #279): the host's account says it's theirs,
        and its folder is there."""
        host = email.strip().lower()
        with self._lock:
            sites = self._load()
            taken = set(sites)
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
            if trial:
                sites[name]["trial"] = True
            writing = self.path.with_name(f"{SITES_FILE}.writing")
            writing.write_text(json.dumps({"sites": sites}, indent=2), encoding="utf-8")
            os.replace(writing, self.path)
            self._hosts.set_site(email, name)
        folder = site_home(name, self.home)
        folder.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Site added",
            extra={"site": name, "host": email, "path": str(folder), "trial": trial},
        )
        return folder


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
        return label if sites.exists(label) else None

    return site_of


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


def make_service(
    home: Path,
    admin_file: Path | None = None,
    admin_laptops_file: Path | None = None,
    mailer: Mailer | None = None,
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
    async def _redirect(scope: Scope, send: Send, location: str) -> None:
        query = bytes(scope.get("query_string") or b"").decode("latin-1")
        target = f"{location}?{query}" if query else location
        await send(
            {
                "type": "http.response.start",
                "status": 308,
                "headers": [(b"location", target.encode("latin-1")), (b"content-length", b"0")],
            }
        )
        await send({"type": "http.response.body", "body": b""})

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
