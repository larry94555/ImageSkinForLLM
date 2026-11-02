"""The host's sign-up, sign-in and sign-out routes (roadmap R188), and `require_host` for every
host-only route (R190 on)."""

import logging
import re
import time
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Cookie, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from imageskin.admin_api import address
from imageskin.admin_settings import CustomUse
from imageskin.hosts import (
    DEFAULT_SITE,
    HOST_COOKIE,
    Host,
    HostAccounts,
    HostElsewhere,
    HostRefused,
    HostsUnreadable,
    normal_email,
    trial_cookie,
)

logger = logging.getLogger(__name__)

COOKIE = HOST_COOKIE
# Kept until the host signs out (item 148): the browser's longest, about 400 days.
COOKIE_MAX_AGE = 400 * 24 * 60 * 60
NOT_SIGNED_IN = "Sign in as a host to do this."
# Hosts sign up at the main address, which makes each one a site (R62); every other site has its
# one host.
SITE_HAS_HOST = "This site already has its host. Sign up at the main address instead."
NO_SITE_MADE = "Your account was made, but its site wasn't. Please try signing in in a minute."

Token = Annotated[str | None, Cookie(alias=COOKIE)]
Email = Annotated[str, Body(embed=True)]
Password = Annotated[str, Body(embed=True)]
# The host pages the browser says it opened (R189); anything else is refused, not logged.
HostPage = Literal["sign-up", "sign-in"]


def elsewhere(
    request: Request, here: str, site: str, is_trial: Callable[[str], bool] = lambda _: False
) -> str:
    """Where a host of another site signs in: the main address, their site's name in front of
    it, or their trial site's path after it (R61a), from the address this request came to, which
    is the site `here`'s."""
    host = request.headers.get("host", "localhost")
    at_main = here == DEFAULT_SITE or is_trial(here)
    main = re.sub(r"^(www|app)\.", "", host) if at_main else host.split(".", 1)[-1]
    if site == DEFAULT_SITE:
        where = main
    elif is_trial(site):
        where = f"{main}/t/{site}"
    else:
        where = f"{site}.{main}"
    return f"Your site is at {where}. Sign in there."


def host_router(
    accounts: HostAccounts,
    may_use: Callable[[Host], CustomUse],
    site: str = DEFAULT_SITE,
    is_trial: Callable[[str], bool] = lambda _: False,
    make_site: Callable[[str], str] | None = None,
) -> tuple[APIRouter, Callable[[str | None], Host]]:
    """The routes, and the dependency that refuses a request not signed in as a host. `may_use`
    says whether a host may use a custom image and voice (R239), read at each request so an
    Admin settings change applies at once. Only the `site`'s host is signed in here (R61): another
    site's sign-in, sent here by hand, counts as none. With `make_site`, each sign-up at the main
    address makes the new host a trial site of their own (R62): it is given their email and
    returns the site's trial code."""

    def own_host(token: str | None) -> Host | None:
        return accounts.host(token, site)

    router = APIRouter(prefix="/api/host")

    def require_host(token: Token = None) -> Host:
        host = own_host(token)
        if host is None:
            raise HTTPException(status_code=401, detail=NOT_SIGNED_IN)
        return host

    def signed_in(
        request: Request, token: str, email: str, code: str | None = None
    ) -> JSONResponse:
        """Signed in, with the cookie that keeps them so; with a trial `code`, signed in to that
        new trial site, whose page the browser goes to (R62)."""
        body: dict[str, object] = {"signed_in": True, "email": normal_email(email)}
        name, path = COOKIE, "/"
        if code is not None:
            path = f"{request.scope.get('root_path', '')}/t/{code}/"
            body |= {"site": code, "go_to": path}
            name = trial_cookie(code)
        response = JSONResponse(body)
        https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        response.set_cookie(
            name,
            token,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="strict",
            secure=https,
            path=path,
        )
        return response

    @router.get("/session")
    def session(token: Token = None) -> dict[str, object]:
        """Whether this browser is signed in as a host, and as whom."""
        host = own_host(token)
        return {"signed_in": host is not None, "email": host and host.email}

    def unfinished(request: Request, email: str, password: str) -> bool:
        """Whether the host signed up with this password and has no site yet, or only a trial
        site, so signing up again finishes making it (Codex's review of PR #279)."""
        try:
            accounts.sign_in(email, password, address(request), DEFAULT_SITE)
        except HostElsewhere as e:
            return is_trial(e.site)
        except (HostRefused, HostsUnreadable):
            return False
        return True

    @router.post("/sign-up")
    def sign_up(request: Request, email: Email, password: Password) -> JSONResponse:
        if site != DEFAULT_SITE:
            logger.info(
                "Host sign-up refused", extra={"site": site, "why": "the site has its host"}
            )
            return JSONResponse({"detail": SITE_HAS_HOST}, status_code=403)
        try:
            token = accounts.sign_up(email, password, address(request))
        except HostRefused as e:
            if e.reason != "email already signed up":
                return JSONResponse({"detail": str(e)}, status_code=400)
            if make_site is None or not unfinished(request, email, password):
                return JSONResponse({"detail": str(e)}, status_code=409)
            # Signed up before, and making their site stopped partway: it is finished now.
            logger.info("Sign-up finished from before", extra={"email": normal_email(email)})
        except HostsUnreadable as e:
            return JSONResponse({"detail": str(e)}, status_code=503)
        else:
            if make_site is None:
                return signed_in(request, token, email)
        start = time.perf_counter()
        try:
            code = make_site(email)
            # Making the site ends the sign-in made with the account, which was the main
            # address's: the host is signed in again, to their site.
            token = accounts.sign_in_now(email)
        except Exception:
            logger.exception("Site not created", extra={"email": normal_email(email)})
            return JSONResponse({"detail": NO_SITE_MADE}, status_code=503)
        logger.info(
            "Site created",
            extra={
                "trial": code,
                "email": normal_email(email),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return signed_in(request, token, email, code)

    @router.post("/sign-in")
    def sign_in(request: Request, email: Email, password: Password) -> JSONResponse:
        try:
            token = accounts.sign_in(email, password, address(request), site)
        except HostElsewhere as e:
            # The password was right: say where their site is (R61e).
            return JSONResponse(
                {"detail": elsewhere(request, site, e.site, is_trial), "site": e.site},
                status_code=401,
            )
        except HostRefused as e:
            return JSONResponse({"detail": str(e)}, status_code=401)
        except HostsUnreadable as e:
            return JSONResponse({"detail": str(e)}, status_code=503)
        return signed_in(request, token, email)

    @router.post("/sign-out")
    def sign_out(request: Request, token: Token = None) -> JSONResponse:
        try:
            accounts.sign_out(token, address(request))
        except HostsUnreadable as e:
            # The cookie is kept: the sign-in can't be ended on the server until the file reads.
            return JSONResponse({"detail": str(e)}, status_code=503)
        response = JSONResponse({"signed_in": False})
        response.delete_cookie(COOKIE, path="/")
        return response

    @router.post("/page", status_code=204)
    def page_opened(request: Request, page: Annotated[HostPage, Body(embed=True)]) -> None:
        """For the log: a host page opened in the browser (R189)."""
        logger.info("Host page opened", extra={"page": page, "address": address(request)})

    @router.get("/me")
    def me(host: Annotated[Host, Depends(require_host)]) -> dict[str, object]:
        """The signed-in host's account: the first host-only route. With whether they may use
        their own photo and voice (R239), so the browser knows what to offer."""
        use = may_use(host)
        return {
            "email": host.email,
            "created_at": host.created_at,
            "custom_image": use.image,
            "custom_voice": use.voice,
        }

    return router, require_host
