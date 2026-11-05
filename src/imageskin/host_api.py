"""The host's sign-up, sign-in and sign-out routes (roadmap R188), and `require_host` for every
host-only route (R190 on)."""

import logging
import os
import re
import time
from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Cookie, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from imageskin.admin_api import address
from imageskin.admin_settings import CustomUse
from imageskin.email_sending import FAILED, EmailFailed
from imageskin.email_sending import Email as Message
from imageskin.hosts import (
    DEFAULT_SITE,
    HOST_COOKIE,
    INVALID_EMAIL,
    TOO_SOON,
    TRIAL_USED,
    Host,
    HostAccounts,
    HostElsewhere,
    HostRefused,
    HostsUnreadable,
    SiteDeleted,
    ends_admin,
    normal_email,
    refuse_if_disabled,
    site_deleted_words,
    trial_cookie,
    without_admin,
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
NOT_YOURS = "That isn't one of your sites."
ALREADY_CONFIRMED = "Your email address is already confirmed."
CONFIRM_SUBJECT = "Confirm your email for your me0.ai site"

Token = Annotated[str | None, Cookie(alias=COOKIE)]
Email = Annotated[str, Body(embed=True)]
Password = Annotated[str, Body(embed=True)]
DisplayName = Annotated[str | None, Body(embed=True)]
# The host pages the browser says it opened (R189); anything else is refused, not logged.
HostPage = Literal["sign-up", "sign-in"]


# The main address, such as app.me0.ai, that a site's own address sends a main-site host to (R255):
# compose.yaml passes the deploy's SITE_ADDRESS as it.
MAIN_ADDRESS_VARIABLE = "IMAGESKIN_MAIN_ADDRESS"


def origin_of(request: Request) -> str:
    """The scheme and address the browser used, for a link in an email (R62b)."""
    https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    return f"{'https' if https else 'http'}://{request.headers.get('host', 'localhost')}"


def site_address(
    request: Request,
    here: str,
    site: str,
    is_trial: Callable[[str], bool] = lambda _: False,
    subdomain: Callable[[str], str | None] = lambda site: site,
) -> str:
    """Where a site is, with the scheme the browser used, from the address this request came
    to, which is the site `here`'s: the main address, the site's name in front of it, or its
    trial path after it (R61a). A host who signs in elsewhere is sent there (R255). From a
    site's own address, the main address is the configured one (MAIN_ADDRESS_VARIABLE, the
    deploy's SITE_ADDRESS, such as app.me0.ai), not the bare domain, which needn't reach the
    app (Codex's review of PR #295); with none set, as on a laptop, it is the domain. A trial
    site whose host picked its subdomain (R63) is at that subdomain."""
    https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    host = request.headers.get("host", "localhost")
    if here == DEFAULT_SITE or is_trial(here):
        main, domain = host, re.sub(r"^(www|app)\.", "", host)
    else:
        domain = host.split(".", 1)[-1]
        main = os.environ.get(MAIN_ADDRESS_VARIABLE, "").strip().strip("/").lower() or domain
    if site == DEFAULT_SITE:
        where = main
    elif is_trial(site):
        where = f"{main}/t/{site}"
    else:
        where = f"{subdomain(site) or site}.{domain}"
    return f"{'https' if https else 'http'}://{where}"


def host_router(
    accounts: HostAccounts,
    may_use: Callable[[Host], CustomUse],
    site: str = DEFAULT_SITE,
    is_trial: Callable[[str], bool] = lambda _: False,
    make_site: Callable[[str], str] | None = None,
    send_email: Callable[[Message], object] | None = None,
    trial_used: Callable[[str], bool] = lambda _: False,
    paused: Callable[[str], str | None] = lambda _: None,
    subscribed: Callable[[str], bool] = lambda _: False,
    subdomain: Callable[[str], str | None] = lambda site: site,
    restart: Callable[[str], str] | None = None,
    days_before_deleting: Callable[[], int] = lambda: 30,
    acting_link: Callable[[str], str | None] = lambda _: None,
    site_host: Callable[[str], str | None] = lambda _: None,
    test_mode: Callable[[Request], str | None] = lambda _: "no test mode here",
) -> tuple[APIRouter, Callable[..., Host]]:
    """The routes, and the dependency that refuses a request not signed in as a host. `may_use`
    says whether a host may use a custom image and voice (R239), read at each request so an
    Admin settings change applies at once. Only the `site`'s host is signed in here (R61): another
    site's sign-in, sent here by hand, counts as none. With `make_site`, each sign-up at the main
    address makes the new host a trial site of their own (R62): it is given their email and
    returns the site's trial code. The customer then confirms their email from a link sent with
    `send_email` before managing it (R62b). `trial_used` says whether an email address has had
    its one free trial, and `paused` why a site is paused (R66); `subscribed` whether it is paid
    for (R67). With `restart`, a host whose site was deleted starts it again (R69c): it is given
    their email and returns the new site's name. A host with several sites (R256) opens each
    signed in, with a one-time link, made with `acting_link` for the administrator acting as
    them (R44a). `site_host` gives a site's host's email, whose display name (R259) is the only
    way any answer here names the host to someone else. `test_mode` says why a sign-up with
    "-admin" may not make the administrator's test account (R265), or None when it may."""

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
        # Who the top bar names (R259); with a trial `code`, the new site is theirs.
        body["display_name"] = accounts.display_name_of(email)
        body["host_name"] = body["display_name"] if code is not None else host_name()
        host = accounts.host(token, unconfirmed=True)
        body["confirmed"] = host is None or host.confirmed
        if host is not None and host.disabled:
            body["disabled"] = True  # so the pages are read-only at once (R44d)
        if code is None and paused(site):
            body["paused"] = True  # so the bar with Resume subscription shows at once (R69b)
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

    def host_name() -> str | None:
        """The site's host's display name (R259), for everyone who opens it; None when the site
        has no host, or it can't be read just now."""
        try:
            email = site_host(site)
            return accounts.display_name_of(email) if email else None
        except Exception:
            logger.exception("Host's display name not read", extra={"site": site})
            return None

    @router.get("/session")
    def session(token: Token = None) -> dict[str, object]:
        """Whether this browser is signed in as a host, and as whom; and, for anyone, the site's
        host by their display name, never their email (R259)."""
        host = accounts.host(token, site, unconfirmed=True)
        answer: dict[str, object] = {
            "signed_in": host is not None,
            "email": host and host.email,
            "host_name": host_name(),
            # Until they confirm their email, a host's pages only say to (R62b).
            "confirmed": host is None or host.confirmed,
        }
        if host:
            answer["display_name"] = accounts.display_name_of(host.email)
        if host and host.acting:
            # The administrator acting as this host (R44a), for the bar that says so (R44b).
            answer["acting_as_admin"] = True
        if host and host.disabled:
            answer["disabled"] = True  # read-only for the host (R44c)
        if subscribed(site):
            answer["subscribed"] = True  # paid for (R67)
        elif is_trial(site):
            answer["trial"] = True  # its host can cancel it (R66)
        if paused(site):
            answer["paused"] = True  # visitors see a notice (R66, R69)
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
    def sign_up(
        request: Request, email: Email, password: Password, display_name: DisplayName = None
    ) -> JSONResponse:
        if site != DEFAULT_SITE:
            logger.info(
                "Host sign-up refused", extra={"site": site, "why": "the site has its host"}
            )
            return JSONResponse({"detail": SITE_HAS_HOST}, status_code=403)
        began = time.perf_counter()
        # "-admin" at the end makes the administrator's test account for the email without it
        # (R265), only for the signed-in administrator with a test email set. The address with
        # "-admin" is never logged, stored or answered.
        test = ends_admin(email)
        if test:
            why = test_mode(request)
            if why is not None:
                logger.warning("Test sign-up refused", extra={"why": why})
                return JSONResponse({"detail": INVALID_EMAIL}, status_code=400)
            email = without_admin(email)
        # One free trial per email address (R66), checked before the account is made. One
        # signed up already is still told so, or has their site finished, below. A test
        # account's trial uses up nothing (R265).
        if make_site is not None and not test and not accounts.exists(email) and trial_used(email):
            logger.warning(
                "Trial refused: email already used", extra={"email": normal_email(email)}
            )
            return JSONResponse({"detail": TRIAL_USED}, status_code=409)
        try:
            token = accounts.sign_up(
                email,
                password,
                address(request),
                confirm=make_site is not None,
                display_name=display_name,
                test_account=test,
            )
        except HostRefused as e:
            if e.reason != "email already signed up":
                return JSONResponse({"detail": str(e)}, status_code=400)
            # A test account is never made over an account already there (R265).
            if make_site is None or test or not unfinished(request, email, password):
                return JSONResponse({"detail": str(e)}, status_code=409)
            # Signed up before, and making their site stopped partway: it is finished now.
            logger.info("Sign-up finished from before", extra={"email": normal_email(email)})
        except HostsUnreadable as e:
            return JSONResponse({"detail": str(e)}, status_code=503)
        else:
            if test:
                logger.info(
                    "Test account signed up",
                    extra={
                        "email": normal_email(email),
                        "duration_ms": round((time.perf_counter() - began) * 1000, 1),
                    },
                )
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
            # The password was right, at another site's address: the browser goes to the host's
            # own site with a one-time link, which signs them in there (R255). A cookie set here
            # wouldn't reach a site at another subdomain.
            link = accounts.sign_in_link(email)
            to = site_address(request, site, e.site, is_trial, subdomain)
            logger.info(
                "Host sent to their own site",
                extra={"email": normal_email(email), "here": site, "site": e.site, "to": to},
            )
            return JSONResponse(
                {
                    "signed_in": False,
                    "email": normal_email(email),
                    "site": e.site,
                    "sign_in_at": f"{to}/api/host/sign-in/{link}",
                }
            )
        except SiteDeleted:
            # The page then offers to start a new one (R69c), saying the admin settings' days.
            return JSONResponse(
                {
                    "detail": site_deleted_words(days_before_deleting()),
                    "deleted": restart is not None,
                },
                status_code=401,
            )
        except HostRefused as e:
            return JSONResponse({"detail": str(e)}, status_code=401)
        except HostsUnreadable as e:
            return JSONResponse({"detail": str(e)}, status_code=503)
        return signed_in(request, token, email)

    @router.post("/restart")
    def restart_site(request: Request, email: Email, password: Password) -> JSONResponse:
        """Start my site again (R69c), for a host whose site was deleted, with their password:
        a new, empty site, paused until paid for, at its old subdomain if still free. The
        browser goes there with a one-time link that signs them in (R255), where Resume
        subscription brings it live (R69b)."""
        start = time.perf_counter()
        try:
            accounts.sign_in(email, password, address(request), site)
        except SiteDeleted:
            pass  # the right password, and the site was deleted: started again below
        except HostRefused as e:
            if not isinstance(e, HostElsewhere):
                return JSONResponse({"detail": str(e)}, status_code=401)
            return JSONResponse({"detail": "Your site wasn't deleted."}, status_code=409)
        except HostsUnreadable as e:
            return JSONResponse({"detail": str(e)}, status_code=503)
        else:
            return JSONResponse({"detail": "Your site wasn't deleted."}, status_code=409)
        if restart is None:
            return JSONResponse({"detail": NO_SITE_MADE}, status_code=503)
        try:
            name = restart(normal_email(email))
        except Exception:
            logger.exception("Site not started again", extra={"email": normal_email(email)})
            return JSONResponse({"detail": NO_SITE_MADE}, status_code=503)
        link = accounts.sign_in_link(email)
        to = site_address(request, site, name, is_trial, subdomain)
        logger.info(
            "Host sent to their site started again",
            extra={
                "email": normal_email(email),
                "site": name,
                "to": to,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return JSONResponse({"site": name, "sign_in_at": f"{to}/api/host/sign-in/{link}"})

    @router.get("/sign-in/{link}", response_model=None)
    def open_sign_in_link(request: Request, link: str) -> RedirectResponse:
        """The one-time link from a sign-in at another address (R255): signed in here, the
        host's own site, with the cookie that keeps them so, then its home page. A link that
        doesn't work goes to Host sign in."""
        root = request.scope.get("root_path", "")
        token = accounts.open_sign_in_link(link, site, address(request))
        if token is None:
            return RedirectResponse(f"{root}/#/host/sign-in", status_code=303)
        response = RedirectResponse(f"{root}/#/", status_code=303)
        https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        # The site's own host cookie, renamed for a trial site by `SiteApps`, as at sign-in.
        response.set_cookie(
            COOKIE,
            token,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="strict",
            secure=https,
            path="/",
        )
        return response

    @router.get("/sites")
    def own_sites(request: Request, host: Annotated[Host, Depends(require_host)]) -> dict[str, Any]:
        """Each of the host's sites (R256), the one used last first, with where it is: what
        R257's switcher lists. `here` is this one."""
        return {
            "sites": [
                {
                    "site": each,
                    "address": site_address(request, site, each, is_trial, subdomain),
                    "here": each == site,
                    # Paused, such as one added and not yet paid for (R257).
                    "paused": paused(each) is not None,
                }
                for each in accounts.sites_of(host.email)
            ]
        }

    @router.post("/sites/{name}/open")
    def open_site(
        request: Request,
        name: str,
        host: Annotated[Host, Depends(require_host)],
        token: Token = None,
    ) -> JSONResponse:
        """Open another of the host's sites signed in (R256): the browser goes to `go_to`, a
        one-time link that signs them in there, as after a sign-in at another address (R255),
        since this site's cookie doesn't reach another subdomain. Only their own sites."""
        start = time.perf_counter()
        if name not in accounts.sites_of(host.email):
            logger.warning(
                "Host site not opened",
                extra={"email": host.email, "site": name, "why": "not theirs"},
            )
            return JSONResponse({"detail": NOT_YOURS}, status_code=404)
        to = site_address(request, site, name, is_trial, subdomain)
        if host.acting:
            link = acting_link(token or "")
            go_to = f"{to}/api/host/act-as/{link}"
        else:
            link = accounts.sign_in_link(host.email)
            go_to = f"{to}/api/host/sign-in/{link}"
        if link is None:
            return JSONResponse({"detail": NOT_SIGNED_IN}, status_code=401)
        logger.info(
            "Host site opened",
            extra={
                "email": host.email,
                "here": site,
                "site": name,
                "acting": host.acting,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return JSONResponse({"site": name, "go_to": go_to})

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
            "display_name": accounts.display_name_of(host.email),
        }

    @router.put("/display-name")
    def set_display_name(
        host: Annotated[Host, Depends(require_host)],
        display_name: Annotated[str, Body(embed=True)],
    ) -> JSONResponse:
        """Change the name participants and visitors see for the host (R259)."""
        try:
            shown = accounts.set_display_name(host.email, display_name)
        except HostRefused as e:
            logger.warning("Display name refused", extra={"email": host.email, "reason": e.reason})
            return JSONResponse({"detail": str(e)}, status_code=400)
        except HostsUnreadable as e:
            return JSONResponse({"detail": str(e)}, status_code=503)
        if shown is None:
            return JSONResponse({"detail": NOT_SIGNED_IN}, status_code=401)
        return JSONResponse({"display_name": shown})

    return router, require_host
