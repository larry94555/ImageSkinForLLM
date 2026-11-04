"""Where each participant may go (roadmap R261, item 211): in the host's settings, a policy for
every participant, and for any one participant in its place, saying which of the host's sites
they may open directly and the site they are sent to after signing in.

Kept in `participant_policy.json` in the host's folder (R258), beside their participants (R260).
Until the host sets one, every site is open to every participant and they are sent to the host's
first site *(default)*. A site named in the policy that the host no longer has is left out when
it is read, so a deleted site never counts."""

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse

from imageskin.hosts import Host, normal_email

logger = logging.getLogger(__name__)

FILENAME = "participant_policy.json"
EVERY = "every"
PARTICIPANTS = "participants"
NONE_ALLOWED = "Allow at least one site."
LANDING_NOT_ALLOWED = "Participants can only be sent to a site they may open."
NOT_YOUR_SITE = "That site isn't one of yours."
NOT_A_PARTICIPANT = "That email has no participant account with you."
BAD_POLICY = "Those participant settings can't be kept."
UNREADABLE = "The participant settings can't be read right now. Please try again later."

_locks: dict[Path, threading.Lock] = {}
_locks_lock = threading.Lock()


class PolicyRefused(Exception):
    """A policy that can't be kept: the words for the page."""


class PolicyUnreadable(Exception):
    def __init__(self) -> None:
        super().__init__(UNREADABLE)


@dataclass(frozen=True)
class Rule:
    """Which sites may be opened (None: all of the host's), and where a sign-in sends them
    (None: the first site they may open)."""

    sites: tuple[str, ...] | None = None
    landing: str | None = None

    def as_json(self) -> dict[str, Any]:
        return {"sites": None if self.sites is None else list(self.sites), "landing": self.landing}


@dataclass(frozen=True)
class Policy:
    every: Rule = Rule()
    participants: tuple[tuple[str, Rule], ...] = ()

    def rule_for(self, email: str) -> Rule:
        return dict(self.participants).get(normal_email(email), self.every)

    def pruned(self, host_sites: list[str], participants: set[str]) -> "Policy":
        """The policy without the sites the host no longer has and the participants no longer
        theirs, so the host can edit and save it again (Codex's review of PR #311). A rule left
        with no site keeps none, so the host sees it and picks one; a landing site gone is the
        first one allowed again."""

        def kept(rule: Rule) -> Rule:
            sites = None if rule.sites is None else tuple(s for s in rule.sites if s in host_sites)
            allowed = host_sites if sites is None else sites
            return Rule(sites, rule.landing if rule.landing in allowed else None)

        return Policy(
            kept(self.every),
            tuple((e, kept(r)) for e, r in self.participants if e in participants),
        )

    def as_json(self) -> dict[str, Any]:
        return {
            EVERY: self.every.as_json(),
            PARTICIPANTS: {email: rule.as_json() for email, rule in self.participants},
        }


def allowed_sites(rule: Rule, host_sites: list[str]) -> list[str]:
    """The host's sites the rule lets them open, in the host's order."""
    return list(host_sites) if rule.sites is None else [s for s in host_sites if s in rule.sites]


def landing_site(rule: Rule, host_sites: list[str]) -> str | None:
    """Where a sign-in sends them: the rule's landing site while they may open it, or else the
    first site they may; None when the host has no site they may open."""
    allowed = allowed_sites(rule, host_sites)
    if rule.landing in allowed:
        return rule.landing
    return allowed[0] if allowed else None


def _rule(raw: object) -> Rule:
    if not isinstance(raw, dict):
        raise ValueError("a rule must be an object")
    sites = raw.get("sites")
    landing = raw.get("landing")
    if sites is not None and not (
        isinstance(sites, list) and all(isinstance(s, str) for s in sites)
    ):
        raise ValueError("sites must be a list of names")
    if landing is not None and not isinstance(landing, str):
        raise ValueError("landing must be a name")
    return Rule(None if sites is None else tuple(sites), landing)


def policy_from(raw: object) -> Policy:
    """The policy in `raw`, as kept or as sent; ValueError when its shape is wrong."""
    if not isinstance(raw, dict):
        raise ValueError("the policy must be an object")
    people = raw.get(PARTICIPANTS) or {}
    if not isinstance(people, dict):
        raise ValueError("participants must be an object")
    return Policy(
        _rule(raw.get(EVERY) or {}),
        tuple(sorted((normal_email(str(e)), _rule(r)) for e, r in people.items())),
    )


class ParticipantPolicies:
    """The host's policy, in `folder`, the host's own (R258)."""

    def __init__(self, folder: Path) -> None:
        self.path = folder / FILENAME
        with _locks_lock:
            self._lock = _locks.setdefault(self.path.resolve(), threading.Lock())

    def read(self) -> Policy:
        """The policy kept, or the default one when none is; PolicyUnreadable (logged) when the
        file is there but can't be used."""
        with self._lock:
            try:
                text = self.path.read_text(encoding="utf-8")
            except FileNotFoundError:
                return Policy()
            except OSError as e:
                logger.error("Could not read the participant policy", extra={"error": str(e)})
                raise PolicyUnreadable() from e
        try:
            return policy_from(json.loads(text))
        except ValueError as e:
            logger.error("Could not read the participant policy", extra={"error": str(e)})
            raise PolicyUnreadable() from e

    def save(self, policy: Policy, host_sites: list[str], participants: set[str]) -> None:
        """Keep the policy, once each rule names only the host's sites and the host's
        participants, allows at least one site and sends them to one they may open."""
        named = [("", policy.every), *policy.participants]
        for email, rule in named:
            if email and email not in participants:
                raise PolicyRefused(NOT_A_PARTICIPANT)
            mentioned = [*(rule.sites or ()), *([rule.landing] if rule.landing else [])]
            if any(s not in host_sites for s in mentioned):
                raise PolicyRefused(NOT_YOUR_SITE)
            if rule.sites is not None and not rule.sites:
                raise PolicyRefused(NONE_ALLOWED)
            if rule.landing is not None and rule.landing not in allowed_sites(rule, host_sites):
                raise PolicyRefused(LANDING_NOT_ALLOWED)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            part = self.path.with_suffix(".part")
            part.write_text(json.dumps(policy.as_json(), indent=1), encoding="utf-8")
            os.replace(part, self.path)


def participant_policy_router(
    require_host: Callable[..., Host],
    policies_of: Callable[[str], ParticipantPolicies | None],
    sites_of: Callable[[str], list[str]],
    participants_of: Callable[[str], set[str]],
    address_of: Callable[[Request, str], str],
) -> APIRouter:
    """The host's routes for the policy, `/api/host/participant-policy`: the host's sites in
    order with their addresses, their participants' emails, and the policy. `policies_of` gives
    the host's policies by their email, or None for a host with no folder yet."""
    router = APIRouter(prefix="/api/host/participant-policy")

    def answer(request: Request, email: str, policy: Policy) -> dict[str, Any]:
        sites = sites_of(email)
        people = participants_of(email)
        shown = policy.pruned(sites, people)
        if shown != policy:
            logger.info(
                "Participant policy shown without sites or participants now gone",
                extra={"email": email},
            )
        return {
            "sites": [{"site": s, "address": address_of(request, s)} for s in sites],
            "participants": sorted(people),
            "policy": shown.as_json(),
        }

    @router.get("")
    def read(request: Request, host: Annotated[Host, Depends(require_host)]) -> JSONResponse:
        policies = policies_of(host.email)
        try:
            policy = policies.read() if policies else Policy()
        except PolicyUnreadable as e:
            return JSONResponse({"detail": str(e)}, status_code=503)
        return JSONResponse(answer(request, host.email, policy))

    @router.put("")
    def save(
        request: Request,
        host: Annotated[Host, Depends(require_host)],
        sent: Annotated[dict[str, Any], Body()],
    ) -> JSONResponse:
        start = time.perf_counter()
        policies = policies_of(host.email)
        if policies is None:
            return JSONResponse({"detail": UNREADABLE}, status_code=503)
        try:
            policy = policy_from(sent)
        except ValueError as e:
            logger.warning("Participant policy refused", extra={"email": host.email, "why": str(e)})
            return JSONResponse({"detail": BAD_POLICY}, status_code=400)
        try:
            policies.save(policy, sites_of(host.email), participants_of(host.email))
        except PolicyRefused as e:
            logger.warning("Participant policy refused", extra={"email": host.email, "why": str(e)})
            return JSONResponse({"detail": str(e)}, status_code=400)
        logger.info(
            "Participant policy changed",
            extra={
                "email": host.email,
                "every_sites": policy.every.as_json()["sites"],
                "every_landing": policy.every.landing,
                "own_rules": len(policy.participants),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return JSONResponse(answer(request, host.email, policy))

    return router
