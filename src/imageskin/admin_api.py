"""The administrator's sign-in routes (roadmap R149), and `require_admin` for every admin route."""

import logging
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Body, Cookie, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from imageskin.admin import AdminRefused, AdminSignIns

logger = logging.getLogger(__name__)

COOKIE = "imageskin_admin"
# Says nothing of signing in, so a browser that is not signed in learns nothing of the admin routes.
NOT_SIGNED_IN = "Not supported at this time."

Token = Annotated[str | None, Cookie(alias=COOKIE)]


def address(request: Request) -> str:
    """The browser's address, for the log and the wait after wrong passwords. X-Forwarded-For is
    never read here, as a browser can send any it likes: uvicorn puts the browser's address in
    its place only for a proxy the config's `trusted_proxies` names (Caddy on the hosted site)."""
    return request.client.host if request.client else "unknown"


def admin_router(sign_ins: AdminSignIns) -> tuple[APIRouter, Callable[[str | None], None]]:
    """The routes, and the dependency that refuses a request not signed in as administrator."""
    router = APIRouter(prefix="/api/admin")

    def require_admin(token: Token = None) -> None:
        if not sign_ins.signed_in(token):
            raise HTTPException(status_code=401, detail=NOT_SIGNED_IN)

    @router.get("/session")
    def session(token: Token = None) -> dict[str, object]:
        """Whether this browser is signed in, without counting as activity."""
        signed_in = sign_ins.signed_in(token)
        return {
            "signed_in": signed_in,
            "password_set": sign_ins.secret() is not None,
            "timeout_minutes": sign_ins.timeout_minutes(),
            # Why a sign-in ended by itself ("inactive" or "password changed"), said once.
            "ended": None if signed_in else sign_ins.ended(token),
        }

    @router.post("/sign-in", response_model=None)
    def sign_in(
        request: Request, response: Response, password: Annotated[str, Body(embed=True)]
    ) -> dict[str, object] | JSONResponse:
        try:
            token = sign_ins.sign_in(password, address(request))
        except AdminRefused as e:
            # The same status and words for every cause, with no Retry-After (R162).
            return JSONResponse({"detail": str(e), "code": e.code}, status_code=401)
        https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=https, path="/")
        return {"signed_in": True}

    @router.post("/sign-out")
    def sign_out(response: Response, token: Token = None) -> dict[str, object]:
        sign_ins.sign_out(token)
        response.delete_cookie(COOKIE, path="/")
        return {"signed_in": False}

    @router.post("/activity", status_code=204)
    def activity(token: Token = None) -> None:
        """A click or key press in the admin view or on the Settings page (R150)."""
        if not sign_ins.activity(token):
            raise HTTPException(status_code=401, detail=NOT_SIGNED_IN)

    return router, require_admin
