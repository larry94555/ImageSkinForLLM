"""The participant sign-up, sign-in and sign-out routes (roadmap R46), under `/api/participant`."""

import logging
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from imageskin.participants import (
    COOKIE_MAX_AGE,
    Participant,
    ParticipantAccounts,
    ParticipantRefused,
    ParticipantsUnreadable,
)

logger = logging.getLogger(__name__)

Email = Annotated[str, Body(embed=True)]
Password = Annotated[str, Body(embed=True)]
NOT_SIGNED_IN = "Sign in to do this."


def give_cookie(
    response: Response,
    request: Request,
    accounts: ParticipantAccounts,
    token: str,
    domain: str | None,
) -> None:
    """Keep the browser signed in: the participant cookie, for `domain` when there is one."""
    https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    # A trial site's own name and path are given it on the way out (R61a).
    response.set_cookie(
        accounts.cookie,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=https,
        path="/",
        domain=domain,
    )


def participant_router(
    accounts: ParticipantAccounts,
    cookie_domain: Callable[[Request], str | None] = lambda _: None,
) -> APIRouter:
    """The routes. The cookie is `accounts.cookie`, set for `cookie_domain` when it gives one, so
    a host's participant is signed in on each of their sites (R260)."""
    router = APIRouter(prefix="/api/participant")

    def token_of(request: Request) -> str | None:
        # A sign-in from before R260 is still good here; the app swaps its cookie on the way out.
        return accounts.token_in(request.cookies)[0]

    def signed_in(request: Request, token: str, email: str) -> JSONResponse:
        response = JSONResponse({"signed_in": True, "email": email})
        give_cookie(response, request, accounts, token, cookie_domain(request))
        return response

    def account(request: Request, up: bool, email: str, password: str) -> JSONResponse:
        try:
            token = (accounts.sign_up if up else accounts.sign_in)(email, password)
        except ParticipantRefused as e:
            status = 409 if e.reason == "email already signed up" else 400 if up else 401
            return JSONResponse({"detail": str(e)}, status_code=status)
        except ParticipantsUnreadable as e:
            return JSONResponse({"detail": str(e)}, status_code=503)
        found = accounts.participant(token)
        return signed_in(request, token, found.email if found else email)

    @router.get("/session")
    def session(request: Request) -> dict[str, object]:
        """Whether this browser is signed in as a participant of this site, and as whom."""
        found = accounts.participant(token_of(request))
        return {"signed_in": found is not None, "email": found and found.email}

    @router.post("/sign-up")
    def sign_up(request: Request, email: Email, password: Password) -> JSONResponse:
        return account(request, True, email, password)

    @router.post("/sign-in")
    def sign_in(request: Request, email: Email, password: Password) -> JSONResponse:
        return account(request, False, email, password)

    @router.post("/sign-out")
    def sign_out(request: Request) -> JSONResponse:
        try:
            accounts.sign_out(token_of(request))
        except ParticipantsUnreadable as e:
            return JSONResponse({"detail": str(e)}, status_code=503)
        response = JSONResponse({"signed_in": False})
        response.delete_cookie(accounts.cookie, path="/", domain=cookie_domain(request))
        return response

    def require(token: str | None) -> Participant:
        found = accounts.participant(token)
        if found is None:
            raise HTTPException(status_code=401, detail=NOT_SIGNED_IN)
        return found

    @router.get("/progress")
    def progress(request: Request) -> dict[str, Any]:
        """The signed-in participant's Teach me, Quiz me and assessment under way (R46)."""
        return accounts.progress(require(token_of(request)))

    @router.put("/progress", response_model=None)
    def save_progress(request: Request, kept: Annotated[dict[str, Any], Body()]) -> Response:
        try:
            accounts.save_progress(require(token_of(request)), kept)
        except ParticipantRefused as e:
            return JSONResponse({"detail": str(e)}, status_code=400)
        return Response(status_code=204)

    return router
