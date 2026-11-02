"""The host's sign-up, sign-in and sign-out routes (roadmap R188), and `require_host` for every
host-only route (R190 on)."""

import logging
import re
import time
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Cookie, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from imageskin.admin_api import address
from imageskin.admin_settings import CustomUse
from imageskin.email_sending import FAILED, EmailFailed
from imageskin.email_sending import Email as Message
from imageskin.hosts import (
    DEFAULT_SITE,
    HOST_COOKIE,
    TOO_SOON,
    Host,
    HostAccounts,
    HostElsewhere,
    HostRefused,
    HostsUnreadable,
    normal_email,
    refuse_if_disabled,
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
ALREADY_CONFIRMED = "Your email address is already confirmed."
CONFIRM_SUBJECT = "Confirm your email for your me0.ai site"

Token = Annotated[str | None, Cookie(alias=COOKIE)]
Email = Annotated[str, Body(embed=True)]
Password = Annotated[str, Body(embed=True)]
# The host pages the browser says it opened (R189); anything else is refused, not logged.
HostPage = Literal["sign-up", "sign-in"]


def origin_of(request: Request) -> str:
    """The scheme and address the browser used, for a link in an email (R62b)."""
    https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    return f"{'https' if https else 'http'}://{request.headers.get('host', 'localhost')}"


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
    send_email: Callable[[Message], object] | None = None,
) -> tuple[APIRouter, Callable[..., Host]]:
    """The routes, and the dependency that refuses a request not signed in as a host. `may_use`
    says whether a host may use a custom image and voice (R239), read at each request so an
    Admin settings change applies at once. Only the `site`'s host is signed in here (R61): another
    site's sign-in, sent here by hand, counts as none. With `make_site`, each sign-up at the main
    address makes the new host a trial site of their own (R62): it is given their email and
    returns the site's trial code. The customer then confirms their email from a link sent with
    `send_email` before managing it (R62b)."""

    def own_host(token: str | None) -> Host | None:
        return accounts.host(token, site)

    router = APIRouter(prefix="/api/host")

    def require_host(request: Request, token: Token = None) -> Host:
        host = own_host(token)
        if host is None:
            raise HTTPException(status_code=401, detail=NOT_SIGNED_IN)
        refuse_if_disabled(request.method, request.url.path, host)
        return host

    def signed_in(
        request: Request, token: str, email: str, code: str | None = None
    ) -> JSONResponse:
        """Signed in, with the cookie that keeps them so; with a trial `code`, signed in to that
        new trial site, whose page the browser goes to (R62)."""
        body: dict[str, object] = {"signed_in": True, "email": normal_email(email)}
        host = accounts.host(token, unconfirmed=True)
        body["confirmed"] = host is None or host.confirmed
        if host is not None and host.disabled:
            body["disabled"] = True  # so the pages are read-only at once (R44d)
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
        host = accounts.host(token, site, unconfirmed=True)
        answer: dict[str, object] = {
            "signed_in": host is not None,
            "email": host and host.email,
            # Until they confirm their email, a host's pages only say to (R62b).
            "confirmed": host is None or host.confirmed,
        }
        if host and host.acting:
            # The administrator acting as this host (R44a), for the bar that says so (R44b).
            answer["acting_as_admin"] = True
        if host and host.disabled:
            answer["disabled"] = True  # read-only for the host (R44c)
        return answer

    def send_confirmation(request: Request, email: str, token: str, site_path: str) -> bool:
        """Email the confirmation link for the site at `site_path` (R62b): whether it went. Not
        sent, the site's pages offer to send it again."""
        link = f"{origin_of(request)}{site_path}api/host/confirm/{token}"
        text = (
            "Welcome to me0.ai.\n\n"
            "Confirm your email address to start setting up your site:\n\n"
            f"{link}\n\n"
            "The link works for 7 days. If you didn't sign up, you can ignore this email.\n"
        )
        start = time.perf_counter()
        try:
            if send_email is not None:
                send_email(Message(email, CONFIRM_SUBJECT, text, "sign-up confirmation"))
        except EmailFailed:
            logger.exception("Confirmation email failed", extra={"email": email})
            return False
        logger.info(
            "Confirmation email sent",
            extra={"email": email, "duration_ms": round((time.perf_counter() - start) * 1000, 1)},
        )
        return True

    @router.get("/confirm/{token}")
    def confirm(request: Request, token: str) -> RedirectResponse:
        """The link in the confirmation email (R62b): confirms the host, then their site's setup;
        or a page that says the link didn't work, where signed in they can send another."""
        try:
            email = accounts.confirm(token)
        except HostsUnreadable:
            logger.exception("Host email not confirmed", extra={"why": "hosts unreadable"})
            email = None
        page = "#/setup" if email else "#/host/confirm-failed"
        return RedirectResponse(f"{request.scope.get('root_path', '')}/{page}", status_code=303)

    @router.post("/confirm/send")
    def confirm_again(request: Request, token: Token = None) -> JSONResponse:
        """Send it again: a new confirmation link for the signed-in, unconfirmed host (R62b)."""
        host = accounts.host(token, site, unconfirmed=True)
        if host is None:
            return JSONResponse({"detail": NOT_SIGNED_IN}, status_code=401)
        try:
            link = accounts.confirmation(host.email, again=True)
        except HostRefused as e:
            return JSONResponse({"detail": str(e)}, status_code=429 if str(e) == TOO_SOON else 400)
        except HostsUnreadable as e:
            return JSONResponse({"detail": str(e)}, status_code=503)
        if link is None:
            return JSONResponse({"detail": ALREADY_CONFIRMED}, status_code=409)
        if not send_confirmation(
            request, host.email, link, f"{request.scope.get('root_path', '')}/"
        ):
            return JSONResponse({"detail": FAILED}, status_code=503)
        return JSONResponse({"sent": True})

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
            token = accounts.sign_up(
                email, password, address(request), confirm=make_site is not None
            )
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
            # A new link, unless they confirmed already. Signing up again sends another only as
            # Send it again would, at most once a minute, and keeps the last link working till
            # then (Codex's review of PR #280).
            try:
                link = accounts.confirmation(email, again=True)
            except HostRefused as e:
                if e.reason != "too soon":
                    raise
                link = None
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
        response = signed_in(request, token, email, code)
        if link is not None:
            go_to = f"{request.scope.get('root_path', '')}/t/{code}/"
            send_confirmation(request, normal_email(email), link, go_to)
        return response

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
            "disabled": host.disabled,
        }

    return router, require_host
