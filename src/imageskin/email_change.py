"""Changing a host's email address (roadmap R62c): asked for with their password, confirmed from
a link sent to the new address, with a notice to the old one once it is done."""

import logging
import time
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse

from imageskin.email_sending import FAILED, Email, EmailFailed
from imageskin.host_api import origin_of
from imageskin.host_disk import Owners, OwnersUnreadable
from imageskin.hosts import (
    CHANGE_HOURS,
    DEFAULT_SITE,
    EMAIL_TAKEN,
    TOO_SOON,
    Host,
    HostAccounts,
    HostRefused,
    HostsUnreadable,
)
from imageskin.sites import SiteDirectory

logger = logging.getLogger(__name__)

WRONG_PASSWORD = "The password is wrong."
CHANGE_SUBJECT = "Confirm your new email for your me0.ai site"
CHANGED_SUBJECT = "The email for your me0.ai site was changed"


def email_router(
    accounts: HostAccounts,
    require_host: Callable[..., Host],
    sites: SiteDirectory,
    site: str,
    owners: Owners,
    send_email: Callable[[Email], object],
) -> APIRouter:
    """The two calls of Change email on the site's Account page. `owners` is the site's record of
    who added each file, which follows the host to their new email."""
    router = APIRouter(prefix="/api/host/email")

    @router.post("")
    def ask(
        request: Request,
        host: Annotated[Host, Depends(require_host)],
        new_email: Annotated[str, Body(embed=True, max_length=320)],
        password: Annotated[str, Body(embed=True, max_length=1000)],
    ) -> JSONResponse:
        """Send a link to the new email, to confirm it; nothing changes until it is used."""
        start = time.perf_counter()
        if not accounts.password_is(host.email, password):
            logger.warning(
                "Email change refused", extra={"email": host.email, "why": "wrong password"}
            )
            return JSONResponse({"detail": WRONG_PASSWORD}, status_code=401)
        try:
            token = accounts.email_change(host.email, new_email)
        except HostRefused as e:
            logger.warning("Email change refused", extra={"email": host.email, "why": e.reason})
            status = {TOO_SOON: 429, EMAIL_TAKEN: 409}.get(str(e), 400)
            return JSONResponse({"detail": str(e)}, status_code=status)
        except HostsUnreadable as e:
            return JSONResponse({"detail": str(e)}, status_code=503)
        to = new_email.strip().lower()
        site_path = f"{origin_of(request)}{request.scope.get('root_path', '')}"
        link = f"{site_path}/api/host/email/confirm/{token}"
        text = (
            f"Someone, we hope you, asked to change the email for your me0.ai site from"
            f" {host.email} to this address.\n\n"
            f"Confirm it here:\n\n{link}\n\n"
            f"The link works for {CHANGE_HOURS} hours. Until then the email stays {host.email}."
            " If you didn't ask, you can ignore this email.\n"
        )
        try:
            send_email(Email(to, CHANGE_SUBJECT, text, "email change"))
        except EmailFailed:
            logger.exception("Email change link failed", extra={"email": host.email})
            return JSONResponse({"detail": FAILED}, status_code=503)
        logger.info(
            "Email change link sent",
            extra={
                "email": host.email,
                "new_email": to,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return JSONResponse({"sent_to": to})

    @router.get("/confirm/{token}")
    def confirm(request: Request, token: str) -> RedirectResponse:
        """The link in the email to the new address: the account, its site and its files move to
        it, and the old address is told."""
        root = request.scope.get("root_path", "")
        failed = RedirectResponse(f"{root}/#/host/email-failed", status_code=303)
        try:
            found = accounts.email_change_of(token)
            if found is None:
                return failed
            email, new_email = found
            own = accounts.site_of(email) == site
            # The site's records first, so each follows the account; put back if it can't move.
            if own and site != DEFAULT_SITE:
                sites.set_host(site, email, new_email)
            if own:
                owners.rename(email, new_email)
            if accounts.change_email(token) is None:
                if own:
                    owners.rename(new_email, email)
                if own and site != DEFAULT_SITE:
                    sites.set_host(site, new_email, email)
                return failed
        except (HostsUnreadable, OwnersUnreadable, OSError):
            logger.exception("Host email not changed", extra={"why": "files unreadable"})
            return failed
        text = (
            f"The email for your me0.ai site was changed from {email} to {new_email}. Sign in"
            f" with {new_email} from now on.\n\n"
            "If you didn't change it, reply to this email at once.\n"
        )
        try:
            send_email(Email(email, CHANGED_SUBJECT, text, "email changed"))
        except EmailFailed:
            logger.exception("Email change notice failed", extra={"email": email})
        return RedirectResponse(f"{root}/#/host/email-changed", status_code=303)

    return router
