"""Settings only for a signed-in host, or on a laptop listed in the admin laptops file (roadmap
R191, item 151), so the administrator can still open Settings and sign in there.

A listed laptop proves itself as at the admin sign-in (R163, R164): it signs a one-time challenge
and the server checks the key's ID is in `admin-laptops.toml`. The server then gives the browser
a pass in a cookie, kept in memory, so the Settings page's calls need no proof each. A pass holds
only while its laptop stays listed. With no laptops file no laptop is listed, unlike the admin
sign-in, which then lets any laptop in: only a signed-in host sees Settings.
"""

import logging
import secrets
import threading
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Cookie, HTTPException, Request, Response

from imageskin.admin_api import Laptop
from imageskin.admin_laptops import AdminLaptops, LaptopProof
from imageskin.host_api import COOKIE as HOST_COOKIE
from imageskin.hosts import HostAccounts

logger = logging.getLogger(__name__)

COOKIE = "imageskin_laptop"
# Passes kept at most: past this the oldest go, so asking for many can't use up the memory.
PASSES_KEPT = 1000

HostToken = Annotated[str | None, Cookie(alias=HOST_COOKIE)]
LaptopToken = Annotated[str | None, Cookie(alias=COOKIE)]
# Who may open Settings: a signed-in host, a listed laptop, or no one.
Who = Literal["host", "laptop"] | None


class SettingsAccess:
    """Who may open Settings, and the passes given to listed laptops."""

    def __init__(self, hosts: HostAccounts, laptops: AdminLaptops) -> None:
        self.hosts = hosts
        self.laptops = laptops
        self._lock = threading.Lock()
        # Each pass given, with its laptop's ID, oldest first.
        self._passes: dict[str, str] = {}

    def listed(self, proof: LaptopProof | None) -> str | None:
        """The laptop's ID when the proof is good and the laptop is in the file; else None."""
        if proof is None or self.laptops.allowed() is None:
            return None
        refused, laptop = self.laptops.check(proof)
        return laptop if refused is None else None

    def give_pass(self, laptop: str) -> str:
        with self._lock:
            while len(self._passes) >= PASSES_KEPT:
                del self._passes[next(iter(self._passes))]
            token = secrets.token_urlsafe(32)
            self._passes[token] = laptop
            return token

    def laptop(self, token: str | None) -> str | None:
        """The pass's laptop, while it is still listed."""
        with self._lock:
            laptop = self._passes.get(token) if token else None
        allowed = self.laptops.allowed()
        return laptop if laptop and allowed is not None and laptop in allowed else None

    def who(self, host_token: str | None, laptop_token: str | None) -> Who:
        if self.hosts.host(host_token) is not None:
            return "host"
        if self.laptop(laptop_token) is not None:
            return "laptop"
        return None


def settings_router(access: SettingsAccess) -> tuple[APIRouter, Callable[..., str]]:
    """The route that says whether Settings is shown, and the dependency that refuses the
    Settings page's calls to anyone else as if they weren't there."""
    router = APIRouter(prefix="/api/settings")

    def require_settings(
        request: Request, host_token: HostToken = None, laptop_token: LaptopToken = None
    ) -> str:
        who = access.who(host_token, laptop_token)
        if who is None:
            logger.info(
                "Settings call refused", extra={"method": request.method, "path": request.url.path}
            )
            raise HTTPException(status_code=404, detail="Not Found")
        return who

    @router.post("/access")
    def settings_access(
        request: Request,
        response: Response,
        laptop: Annotated[Laptop | None, Body(embed=True)] = None,
        host_token: HostToken = None,
        laptop_token: LaptopToken = None,
    ) -> dict[str, object]:
        """Whether this browser sees Settings: a signed-in host, or a laptop with a pass or a
        proof that it is listed. A listed laptop's proof gets it a pass for the Settings calls."""
        who = access.who(host_token, laptop_token)
        found = None
        if who is None:
            proof = LaptopProof(**laptop.model_dump()) if laptop else None
            found = access.listed(proof)
            if found is not None:
                https = (
                    request.url.scheme == "https"
                    or request.headers.get("x-forwarded-proto") == "https"
                )
                response.set_cookie(
                    COOKIE,
                    access.give_pass(found),
                    httponly=True,
                    samesite="strict",
                    secure=https,
                    path="/",
                )
                who = "laptop"
        logger.info(
            "Settings shown" if who else "Settings hidden",
            extra={
                "host": who == "host",
                "laptop": found or (access.laptop(laptop_token) if who == "laptop" else None),
            },
        )
        return {"shown": who is not None, "as": who}

    return router, require_settings
