"""One set of app state per site (roadmap R61b, feature item 66).

The app keeps its state in objects it makes when it starts: the conversation, the uploads, the
content and its jobs, Prepare, the reply videos, the customization and more. With many sites,
sharing them would mix one site's conversation, job status or files with another's. So each
site gets an app of its own, made the first time the site is used and kept while the server
runs (`SiteApps`); its background jobs, their callbacks and the files they write belong to it.

What holds no site's data is shared by every site's app (`Service`): the host accounts, the
administrator's sign-in, settings and guidelines, the listed laptops' passes and the network's
month. Until R61 matches each request to its site, there is one site, the app's home folder.
"""

import logging
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
from imageskin.hosts import HostAccounts
from imageskin.network import NetworkMonth
from imageskin.settings_access import SettingsAccess

logger = logging.getLogger(__name__)

# The one site there is until R61: the app's home folder, at every address.
DEFAULT_SITE = "default"

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
Asgi = Callable[[Scope, Receive, Send], Awaitable[None]]


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
    )


def one_site(scope: Scope) -> str:
    """Every request is the one site's until R61 matches it by its address."""
    return DEFAULT_SITE


class SiteApps:
    """The server's ASGI app: each request goes to its site's own app, made by `make` the first
    time the site is used, once, however many requests ask for it at the same time."""

    def __init__(self, make: Callable[[str], Asgi], site_of: Callable[[Scope], str] = one_site):
        self._make = make
        self._site_of = site_of
        self._apps: dict[str, Asgi] = {}
        self._lock = threading.Lock()

    def app(self, site: str) -> Asgi:
        """The site's app, made now if it hasn't been. Making one can take seconds."""
        with self._lock:
            made = self._apps.get(site)
            if made is not None:
                return made
            start = time.perf_counter()
            try:
                made = self._make(site)
            except Exception:
                logger.exception("Site state not made", extra={"site": site})
                raise
            self._apps[site] = made
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
        with self._lock:
            made = self._apps.get(site)
        if made is None:  # made in a thread, so a slow start never holds up the other sites
            made = await anyio.to_thread.run_sync(self.app, site)
        await made(scope, receive, send)

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


def site_home(site: str) -> Path:
    """The folder a site's files are kept in. Until R61, the one site's is the app's home."""
    if site != DEFAULT_SITE:
        raise ValueError(f"No site {site!r} yet: there is one site until R61.")
    return default_home()
