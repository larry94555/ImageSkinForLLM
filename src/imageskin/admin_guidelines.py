"""The administrator's own identity, goals and guidelines, as system requirements over the host's
(roadmap R243, items 197 and 198).

They are kept in `admin-guidelines.json` in the app's home folder, in the same shape as
`customization.json` (R92): the identity, the goals and each feature's guidelines, all empty when
the file is missing. Where the host's identity, goals or a feature's guidelines go to the LLM, the
administrator's go too, first, as requirements to follow first, with the host's followed only
where they don't conflict. Empty parts add nothing, so prompts, and llama-server's cache, are as
before until the administrator writes some. Only the administrator reads or changes them.
"""

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from imageskin.customization import (
    FEATURES,
    GUIDELINES_FIRST,
    IDENTITY_LABELS,
    MOST_GOAL_CHARS,
    MOST_GOALS,
    MOST_GUIDELINES_CHARS,
    MOST_PART_CHARS,
    Customization,
    CustomizationRefused,
    _checked,
    _sentence,
    guidelines_of,
)

logger = logging.getLogger(__name__)

ADMIN_FILE = "admin-guidelines.json"

# How the administrator's parts are put before the host's, word for word.
REQUIREMENTS = (
    "System requirements, set by the administrator: follow these first, and everything after"
    " them only where it doesn't conflict with them."
)
HOST_AFTER = "Then these, only where they don't conflict with them:"
ADMIN_IDENTITY = {
    "name": "Your name is {}",
    "speaks_as": "You speak as {}",
    "purpose": "Your purpose is {}",
    "audience": "You are here for {}",
    "helps_with": "You help with {}",
}


@dataclass(frozen=True)
class AdminGuidelines:
    identity: dict[str, str] = field(default_factory=dict)
    goals: tuple[str, ...] = ()
    guidelines: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "identity": {k: self.identity.get(k, "") for k in IDENTITY_LABELS},
            "goals": list(self.goals),
            "guidelines": {k: self.guidelines.get(k, "") for k in FEATURES},
        }

    def parts(self) -> list[str]:
        """The parts that have text: identity, goals and each feature's key."""
        used = []
        if any(self.identity.values()):
            used.append("identity")
        if self.goals:
            used.append("goals")
        return used + [k for k in FEATURES if self.guidelines.get(k)]


EMPTY = AdminGuidelines()


def checked(data: object) -> AdminGuidelines:
    """The administrator's guidelines in `data`, checked as an edit on the Customization page is
    (R94); empty text is no requirement."""
    if not isinstance(data, dict):
        raise CustomizationRefused("The admin guidelines must be a JSON object.")
    identity = data.get("identity", {})
    if not isinstance(identity, dict):
        raise CustomizationRefused("The identity must be a JSON object.")
    unknown = sorted(set(identity) - set(IDENTITY_LABELS))
    if unknown:
        raise CustomizationRefused(f"The identity has no {', '.join(unknown)}.")
    parts = {k: _checked(v, IDENTITY_LABELS[k], MOST_PART_CHARS) for k, v in identity.items()}
    goals = data.get("goals", [])
    if not isinstance(goals, list):
        raise CustomizationRefused("The goals must be a list.")
    kept = tuple(g for g in (_checked(g, "A goal", MOST_GOAL_CHARS) for g in goals) if g)
    if len(kept) > MOST_GOALS:
        raise CustomizationRefused(f"There can be at most {MOST_GOALS} goals.")
    guidelines = data.get("guidelines", {})
    if not isinstance(guidelines, dict):
        raise CustomizationRefused("The guidelines must be a JSON object.")
    unknown = sorted(set(guidelines) - set(FEATURES))
    if unknown:
        raise CustomizationRefused(f"There is no feature {', '.join(unknown)}.")
    texts = {
        k: _checked(v, f"{FEATURES[k].label}'s guidelines", MOST_GUIDELINES_CHARS)
        for k, v in guidelines.items()
    }
    return AdminGuidelines(
        {k: v for k, v in parts.items() if v}, kept, {k: v for k, v in texts.items() if v}
    )


def requirements(admin: AdminGuidelines) -> str:
    """The administrator's identity and goals as they go before the host's (empty if none)."""
    said = [
        _sentence(ADMIN_IDENTITY[k].format(admin.identity[k]))
        for k in IDENTITY_LABELS
        if admin.identity.get(k)
    ]
    if admin.goals:
        said.append("Your goals: " + " ".join(map(_sentence, admin.goals)))
    return f"{REQUIREMENTS} {' '.join(said)}" if said else ""


def combined(admin_text: str, host_text: str) -> str:
    """A feature's guidelines with the administrator's first."""
    return f"{GUIDELINES_FIRST} {admin_text} {HOST_AFTER} {host_text}"


def applied(host: Customization, admin: AdminGuidelines) -> Customization:
    """The customization as a prompt is asked with it: the administrator's identity and goals
    before the host's, and each feature's guidelines with the administrator's first. Never
    saved; with no admin guidelines, `host` itself."""
    if admin == EMPTY:
        return host
    guidelines = dict(host.guidelines)
    for key, text in admin.guidelines.items():
        guidelines[key] = combined(text, guidelines_of(host, key))
    return replace(
        host,
        guidelines=guidelines,
        requirements=requirements(admin),
        required=dict(admin.guidelines),
    )


def ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


class AdminGuidelinesFile:
    """`admin-guidelines.json` in `home`, read again only when it has changed since the last
    read, so a broken file is logged once, not with every prompt."""

    def __init__(self, home: Path) -> None:
        self.path = home / ADMIN_FILE
        self._lock = threading.Lock()
        self._seen: tuple[int, int] | None = None
        self._last = EMPTY

    def read(self) -> AdminGuidelines:
        with self._lock:
            try:
                stat = self.path.stat()
            except FileNotFoundError:
                self._seen, self._last = None, EMPTY
                return EMPTY
            except OSError as e:
                logger.error("Admin guidelines can't be read", extra={"error": str(e)})
                return EMPTY
            seen = (stat.st_mtime_ns, stat.st_size)
            if seen != self._seen:
                self._seen = seen
                self._last = self._load()
            return self._last

    def _load(self) -> AdminGuidelines:
        try:
            return checked(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as e:  # JSONDecodeError and CustomizationRefused too
            logger.error("Admin guidelines can't be read", extra={"error": str(e)})
            return EMPTY

    def save(self, admin: AdminGuidelines) -> list[str]:
        """Write them whole, as R92's saves are; the parts that changed."""
        start = time.perf_counter()
        before = self.read()
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(f"{self.path.stem}.saving.json")
            text = json.dumps(admin.as_dict(), ensure_ascii=False, indent=1)
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, self.path)
            stat = self.path.stat()
            self._seen, self._last = (stat.st_mtime_ns, stat.st_size), admin
        old, new = before.as_dict(), admin.as_dict()
        changed = [p for p in ("identity", "goals") if old[p] != new[p]]
        changed += [k for k in FEATURES if old["guidelines"][k] != new["guidelines"][k]]
        logger.info(
            "Admin guidelines changed",
            extra={"parts": changed, "duration_ms": ms_since(start)},
        )
        return changed
