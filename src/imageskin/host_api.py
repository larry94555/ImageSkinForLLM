"""The host's sign-up, sign-in and sign-out routes (roadmap R188), and `require_host` for every
host-only route (R190 on)."""

import logging
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Cookie, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from imageskin.admin_api import address
from imageskin.admin_settings import CustomUse
from imageskin.hosts import Host, HostAccounts, HostRefused, HostsUnreadable, normal_email

logger = logging.getLogger(__name__)

COOKIE = "imageskin_host"
# Kept until the host signs out (item 148): the browser's longest, about 400 days.
COOKIE_MAX_AGE = 400 * 24 * 60 * 60
NOT_SIGNED_IN = "Sign in as a host to do this."

Token = Annotated[str | None, Cookie(alias=COOKIE)]
Email = Annotated[str, Body(embed=True)]
Password = Annotated[str, Body(embed=True)]
# The host pages the browser says it opened (R189); anything else is refused, not logged.
HostPage = Literal["sign-up", "sign-in"]


def host_router(
    accounts: HostAccounts, may_use: Callable[[Host], CustomUse]
) -> tuple[APIRouter, Callable[..., Host]]:
    """The routes, and the dependency that refuses a request not signed in as a host. `may_use`
    says whether a host may use a custom image and voice (R239), read at each request so an
    Admin settings change applies at once."""
    router = APIRouter(prefix="/api/host")

    def require_host(request: Request, token: Token = None) -> Host:
        host = accounts.host(token)
        if host is None:
            # A visitor opening the wiki by its address lands here too (R45).
            logger.info(
                "Host call refused", extra={"method": request.method, "path": request.url.path}
            )
            raise HTTPException(status_code=401, detail=NOT_SIGNED_IN)
        return host

    def signed_in(request: Request, token: str, email: str) -> JSONResponse:
        response = JSONResponse({"signed_in": True, "email": normal_email(email)})
        https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
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

    @router.get("/session")
    def session(token: Token = None) -> dict[str, object]:
        """Whether this browser is signed in as a host, and as whom."""
        host = accounts.host(token)
        return {"signed_in": host is not None, "email": host and host.email}

    @router.post("/sign-up")
    def sign_up(request: Request, email: Email, password: Password) -> JSONResponse:
        try:
            token = accounts.sign_up(email, password, address(request))
        except HostRefused as e:
            status = 409 if e.reason == "email already signed up" else 400
            return JSONResponse({"detail": str(e)}, status_code=status)
        except HostsUnreadable as e:
            return JSONResponse({"detail": str(e)}, status_code=503)
        return signed_in(request, token, email)

    @router.post("/sign-in")
    def sign_in(request: Request, email: Email, password: Password) -> JSONResponse:
        try:
            token = accounts.sign_in(email, password, address(request))
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
