"""The participant sign-up, sign-in and sign-out routes (roadmap R46), under `/api/participant`."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body, Cookie, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from imageskin.participants import (
    COOKIE,
    COOKIE_MAX_AGE,
    Participant,
    ParticipantAccounts,
    ParticipantRefused,
    ParticipantsUnreadable,
)

logger = logging.getLogger(__name__)

Token = Annotated[str | None, Cookie(alias=COOKIE)]
Email = Annotated[str, Body(embed=True)]
Password = Annotated[str, Body(embed=True)]
NOT_SIGNED_IN = "Sign in to do this."


def participant_router(accounts: ParticipantAccounts) -> APIRouter:
    router = APIRouter(prefix="/api/participant")

    def signed_in(request: Request, token: str, email: str) -> JSONResponse:
        response = JSONResponse({"signed_in": True, "email": email})
        https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        # A trial site's own name and path are given it on the way out (R61a).
        response.set_cookie(
            COOKIE,
            token,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=https,
            path="/",
        )
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
    def session(token: Token = None) -> dict[str, object]:
        """Whether this browser is signed in as a participant of this site, and as whom."""
        found = accounts.participant(token)
        return {"signed_in": found is not None, "email": found and found.email}

    @router.post("/sign-up")
    def sign_up(request: Request, email: Email, password: Password) -> JSONResponse:
        return account(request, True, email, password)

    @router.post("/sign-in")
    def sign_in(request: Request, email: Email, password: Password) -> JSONResponse:
        return account(request, False, email, password)

    @router.post("/sign-out")
    def sign_out(token: Token = None) -> JSONResponse:
        try:
            accounts.sign_out(token)
        except ParticipantsUnreadable as e:
            return JSONResponse({"detail": str(e)}, status_code=503)
        response = JSONResponse({"signed_in": False})
        response.delete_cookie(COOKIE, path="/")
        return response

    def require(token: str | None) -> Participant:
        found = accounts.participant(token)
        if found is None:
            raise HTTPException(status_code=401, detail=NOT_SIGNED_IN)
        return found

    @router.get("/progress")
    def progress(token: Token = None) -> dict[str, Any]:
        """The signed-in participant's Teach me, Quiz me and assessment under way (R46)."""
        return accounts.progress(require(token))

    @router.put("/progress", response_model=None)
    def save_progress(kept: Annotated[dict[str, Any], Body()], token: Token = None) -> Response:
        try:
            accounts.save_progress(require(token), kept)
        except ParticipantRefused as e:
            return JSONResponse({"detail": str(e)}, status_code=400)
        return Response(status_code=204)

    return router
