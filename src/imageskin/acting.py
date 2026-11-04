"""The administrator acting as a host (roadmap R44a): signed in at the main address, they get a
host's site with all of that host's abilities, while still signed in as the administrator.

The administrator's cookie isn't sent to a host's subdomain, so the main address gives them a
one-time link to the host's site. Opening it there gives that browser an acting token in the
site's own host cookie. Every host check reads that cookie through `HostAccounts.host`, which
asks `email_of` here, so everything the host can do works for the administrator, on that site
only, for as long as the administrator stays signed in."""

import hashlib
import logging
import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Body, Cookie, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from imageskin.admin import AdminSignIns
from imageskin.admin_api import COOKIE as ADMIN_COOKIE
from imageskin.hosts import (
    ACT_PREFIX,
    DEFAULT_SITE,
    HOST_COOKIE,
    NO_SITE,
    HostAccounts,
    normal_email,
)

logger = logging.getLogger(__name__)

LINK_S = 60  # how long the link works *(default)*
NO_SUCH_HOST = "There is no host with that email address."


def key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class Acting:
    admin_token: str
    email: str
    made_at: float
    back: str = ""  # the main address the link was made at, to go back to (R44b)


class ActingAsHost:
    """The links made and the acting tokens in use, kept in memory: a restart ends them all."""

    def __init__(self, admin: AdminSignIns, clock: Callable[[], float] = time.time) -> None:
        self.admin = admin
        self.clock = clock
        self._lock = threading.Lock()
        self._links: dict[str, Acting] = {}
        self._acting: dict[str, Acting] = {}

    def _end(self, token_key: str, why: str) -> None:
        acting = self._acting.pop(token_key, None)
        if acting is not None:
            logger.info("Admin acting as host stopped", extra={"email": acting.email, "why": why})

    def link(self, admin_token: str, email: str, back: str = "") -> str:
        """A one-time link token for acting as the host; acting as another host ends the first,
        and an earlier link of this administrator stops working."""
        email = normal_email(email)
        token = secrets.token_urlsafe(32)
        with self._lock:
            for k in [k for k, a in self._acting.items() if a.admin_token == admin_token]:
                self._end(k, "acting as another host")
            self._links = {k: a for k, a in self._links.items() if a.admin_token != admin_token}
            self._links[key(token)] = Acting(admin_token, email, self.clock(), back)
        logger.info("Admin acting link made", extra={"email": email})
        return token

    def again(self, token: str) -> str | None:
        """A one-time link for acting as the same host on another of their sites (R256), from
        an acting token in use, which goes on working; None for one no longer in use."""
        if self.email_of(token) is None:
            return None
        link = secrets.token_urlsafe(32)
        with self._lock:
            acting = self._acting.get(key(token))
            if acting is None:
                return None
            self._links[key(link)] = Acting(
                acting.admin_token, acting.email, self.clock(), acting.back
            )
        logger.info("Admin acting link made", extra={"email": acting.email, "from": "acting"})
        return link

    def open(self, link: str, takes: Callable[[str], bool]) -> tuple[str, str] | None:
        """The acting token and the host's email for a link opened where `takes` says its host
        is; the link then works no more. None, and the link kept, when it is opened on another
        site; None when it is unknown, used, too old or its administrator signed out."""
        with self._lock:
            acting = self._links.get(key(link))
            why = None
            if acting is None:
                why = "unknown link"
            elif self.clock() - acting.made_at > LINK_S:
                why = "link too old"
            elif not self.admin.signed_in(acting.admin_token):
                why = "administrator signed out"
            elif not takes(acting.email):
                logger.warning("Admin acting link refused", extra={"why": "another site's host"})
                return None
            if why is not None or acting is None:
                self._links.pop(key(link), None)
                logger.warning("Admin acting link refused", extra={"why": why})
                return None
            del self._links[key(link)]
            token = ACT_PREFIX + secrets.token_urlsafe(32)
            self._acting[key(token)] = Acting(
                acting.admin_token, acting.email, self.clock(), acting.back
            )
        logger.info("Admin acting as host started", extra={"email": acting.email})
        return token, acting.email

    def email_of(self, token: str) -> str | None:
        """The host the acting token acts as, while its administrator is still signed in."""
        with self._lock:
            acting = self._acting.get(key(token))
            if acting is None:
                return None
            if not self.admin.signed_in(acting.admin_token):
                self._end(key(token), "administrator signed out")
                return None
            return acting.email

    def activity(self, token: str) -> bool:
        """A click on the host's site counts as the administrator's activity (R150)."""
        with self._lock:
            acting = self._acting.get(key(token))
        return acting is not None and self.admin.activity(acting.admin_token)

    def stop(self, token: str) -> str | None:
        """Stop acting: the main address it was started from, or None for an unknown token."""
        with self._lock:
            acting = self._acting.get(key(token))
            self._end(key(token), "stopped")
        return None if acting is None else acting.back


def site_address(
    request: Request,
    site: str,
    is_trial: Callable[[str], bool],
    subdomain: Callable[[str], str | None] = lambda site: site,
) -> str:
    """Where a site is, from the main address this request came to: the main address itself,
    its trial path (R61a), or its subdomain (R61), the one its host picked for a trial site
    (R63), with the scheme and port kept."""
    https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    host = request.headers.get("host", "localhost")
    scheme = "https" if https else "http"
    if site == DEFAULT_SITE:
        return f"{scheme}://{host}"
    if is_trial(site):
        return f"{scheme}://{host}/t/{site}"
    main = re.sub(r"^(www|app)\.", "", host)
    return f"{scheme}://{subdomain(site) or site}.{main}"


def acting_routes(
    acting: ActingAsHost,
    accounts: HostAccounts,
    site: str,
    is_trial: Callable[[str], bool],
    require_admin: Callable[..., None],
    subdomain: Callable[[str], str | None] = lambda site: site,
) -> tuple[APIRouter, APIRouter]:
    """The administrator's route that makes the link, at the main address only through
    `require_admin` (R44), and the routes every site has for opening it, its activity and
    stopping."""
    admin = APIRouter(prefix="/api/admin")
    host = APIRouter(prefix="/api/host/act-as")

    @admin.post("/act-as")
    def act_as(
        request: Request,
        email: Annotated[str, Body(embed=True)],
        admin_token: Annotated[str | None, Cookie(alias=ADMIN_COOKIE)] = None,
    ) -> dict[str, str]:
        require_admin(request, admin_token)
        target = accounts.site_of(email)
        if target is None or admin_token is None:
            raise HTTPException(status_code=404, detail=NO_SUCH_HOST)
        if target == NO_SITE:
            # Nothing to act on until they start their site again (R69a, R69c).
            raise HTTPException(status_code=409, detail="This host's site was deleted.")
        link = acting.link(admin_token, email, site_address(request, DEFAULT_SITE, is_trial))
        where = site_address(request, target, is_trial, subdomain)
        return {"link": f"{where}/api/host/act-as/{link}"}

    @host.get("/{link}", response_model=None)
    def open_link(request: Request, link: str) -> RedirectResponse | JSONResponse:
        root = request.scope.get("root_path", "")
        opened = acting.open(link, lambda email: site in accounts.sites_of(email))
        if opened is None:
            return RedirectResponse(f"{root}/#/host/act-as-failed", status_code=303)
        token, _ = opened
        response = RedirectResponse(f"{root}/#/", status_code=303)
        https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        # The site's own host cookie, renamed for a trial site by `SiteApps`, for this browser
        # session only: acting ends with the administrator's sign-in anyway.
        response.set_cookie(
            HOST_COOKIE, token, httponly=True, samesite="strict", secure=https, path="/"
        )
        return response

    @host.post("/activity", status_code=204)
    def activity(token: Annotated[str | None, Cookie(alias=HOST_COOKIE)] = None) -> None:
        if not (token and token.startswith(ACT_PREFIX) and acting.activity(token)):
            raise HTTPException(status_code=401, detail="Not acting as a host.")

    @host.post("/stop")
    def stop(
        request: Request, token: Annotated[str | None, Cookie(alias=HOST_COOKIE)] = None
    ) -> JSONResponse:
        """Stop acting; the page then goes back to the admin view at the main address (R44b)."""
        back = acting.stop(token) if token and token.startswith(ACT_PREFIX) else None
        stopped = back is not None
        go_to = f"{back}/#/admin/settings" if back else None
        response = JSONResponse({"stopped": stopped, "go_to": go_to})
        if stopped:
            response.delete_cookie(HOST_COOKIE, path="/")
        return response

    return admin, host
