"""Forgot password (roadmap R62a): a host asks for a link by email, valid for an hour and used
once, and sets a new password from it."""

import logging
import time
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from imageskin.admin_api import address
from imageskin.email_sending import Email, EmailFailed
from imageskin.host_api import origin_of
from imageskin.hosts import (
    INVALID_EMAIL,
    RESET_HOURS,
    HostAccounts,
    HostRefused,
    HostsUnreadable,
    ends_admin,
    normal_email,
)

logger = logging.getLogger(__name__)

# The same answer whether or not the email has an account, so it can't be used to learn which do.
LINK_ON_ITS_WAY = (
    "If an account has that email address, a link to set a new password is on its way."
    f" It works for {RESET_HOURS} hour."
)
LINK_FAILED = (
    "That link didn't work: it was already used, a newer one was sent, or it is more than an"
    " hour old. Ask for a new one."
)
RESET_SUBJECT = "Set a new password for your me0.ai site"


def reset_router(accounts: HostAccounts, send_email: Callable[[Email], object]) -> APIRouter:
    """Forgot password's two calls, on every site: an account is one host's whatever site it
    is asked from, and the sign-in page then says where their site is (R61e)."""
    router = APIRouter(prefix="/api/host")

    @router.post("/forgot")
    def forgot(
        request: Request, email: Annotated[str, Body(embed=True, max_length=320)]
    ) -> JSONResponse:
        """Email a link to set a new password, if the email has an account."""
        start = time.perf_counter()
        if ends_admin(email):  # only sign-up takes "-admin" (R265)
            logger.info("Password reset refused", extra={"why": "ends in -admin"})
            return JSONResponse({"detail": INVALID_EMAIL}, status_code=400)
        try:
            token = accounts.reset_link(email)
        except HostsUnreadable as e:
            return JSONResponse({"detail": str(e)}, status_code=503)
        if token is not None:
            link = f"{origin_of(request)}{request.scope.get('root_path', '')}/#/host/reset/{token}"
            text = (
                "Someone, we hope you, asked to set a new password for your me0.ai site.\n\n"
                f"Set it here:\n\n{link}\n\n"
                f"The link works for {RESET_HOURS} hour, once. If you didn't ask, you can ignore"
                " this email: your password stays as it is.\n"
            )
            try:
                send_email(Email(normal_email(email), RESET_SUBJECT, text, "password reset"))
                logger.info(
                    "Password reset link sent",
                    extra={
                        "email": normal_email(email),
                        "address": address(request),
                        "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                    },
                )
            except EmailFailed:
                # Said the same way: the answer must not tell an account apart (see above).
                logger.exception("Password reset email failed", extra={"email": email})
        return JSONResponse({"detail": LINK_ON_ITS_WAY})

    @router.post("/reset")
    def reset(
        token: Annotated[str, Body(embed=True, max_length=200)],
        password: Annotated[str, Body(embed=True, max_length=1000)],
    ) -> JSONResponse:
        """Set the new password from the link: every sign-in the host had ends, and they sign in
        with the new one."""
        try:
            email = accounts.reset_with(token, password)
        except HostRefused as e:
            return JSONResponse({"detail": str(e)}, status_code=400)
        except HostsUnreadable as e:
            return JSONResponse({"detail": str(e)}, status_code=503)
        if email is None:
            return JSONResponse({"detail": LINK_FAILED}, status_code=400)
        return JSONResponse({"reset": True, "email": email})

    return router
