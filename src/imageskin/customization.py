"""The AI's identity, its goals and each feature's guidelines (roadmap R92, items 84 and 85).

They are kept together in `customization.json` in the app's home folder, the only copy, with a
fixed default shipped for when the file is missing or can't be read. The identity and goals are
given to the LLM with every prompt, and "Who are you?", "What is your purpose?" and the like are
recognized as "What can you talk about?" is (R41f) and answered from the identity here, so they
cost no LLM call and are answered with general prompts off. Each feature's guidelines are added by
its own PR (R194 to R200); until then there are none.
"""

import json
import logging
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from imageskin.topics import normalized

logger = logging.getLogger(__name__)

CUSTOMIZATION_FILE = "customization.json"


@dataclass(frozen=True)
class Identity:
    """Who the AI is. Each part but `speaks_as` is said in the first person when it is asked
    about, so it is written to follow "I'm", "My purpose is", "I'm here for" and "I can help
    with"; an empty part is left out."""

    name: str = ""
    # Who it speaks as, told to the LLM only.
    speaks_as: str = "the person seen in the video, in the first person"
    purpose: str = "to help you understand the material I was given"
    audience: str = "anyone who wants to learn about it"
    helps_with: str = (
        "answering your questions about it, teaching it in short parts, quizzing you on it"
        " and assessing what you know"
    )


SHIPPED_GOALS = (
    "Help participants understand the material well enough to explain it in their own words.",
)


@dataclass(frozen=True)
class Customization:
    identity: Identity = field(default_factory=Identity)
    goals: tuple[str, ...] = SHIPPED_GOALS
    # Each feature's guidelines, by feature, as R194 to R200 add them.
    guidelines: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "identity": asdict(self.identity),
            "goals": list(self.goals),
            "guidelines": self.guidelines,
        }


SHIPPED = Customization()


class CustomizationUnreadable(ValueError):
    pass


def _text(data: dict[str, Any], key: str, default: str, where: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise CustomizationUnreadable(f"{where}{key} is not text")
    return value.strip()


def from_dict(data: object) -> Customization:
    """The customization in `data`, as read from the file. A part left out is as shipped."""
    if not isinstance(data, dict):
        raise CustomizationUnreadable("the file is not a JSON object")
    identity = data.get("identity", {})
    if not isinstance(identity, dict):
        raise CustomizationUnreadable("identity is not a JSON object")
    shipped = asdict(SHIPPED.identity)
    parts = {k: _text(identity, k, v, "identity.") for k, v in shipped.items()}
    goals = data.get("goals", list(SHIPPED.goals))
    if not isinstance(goals, list) or not all(isinstance(g, str) for g in goals):
        raise CustomizationUnreadable("goals is not a list of text")
    guidelines = data.get("guidelines", {})
    if not isinstance(guidelines, dict):
        raise CustomizationUnreadable("guidelines is not a JSON object")
    kept = tuple(g.strip() for g in goals if g.strip())
    return Customization(Identity(**parts), kept, guidelines)


def save(home: Path, customization: Customization) -> None:
    """Write the whole file to a temporary file and rename it over the old one, so a reader
    never sees half a save."""
    path = home / CUSTOMIZATION_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.stem}.saving.json")
    text = json.dumps(customization.as_dict(), ensure_ascii=False, indent=1)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


@dataclass(frozen=True)
class Read:
    customization: Customization
    shipped: bool  # the shipped default, because the file is missing or can't be read
    duration_ms: float


class CustomizationFile:
    """`customization.json` in `home`, read again only when it has changed since the last read,
    so a broken file is logged once, not with every prompt."""

    def __init__(self, home: Path) -> None:
        self.path = home / CUSTOMIZATION_FILE
        self._lock = threading.Lock()
        self._seen: tuple[int, int] | None = None  # the file's mtime and size when last read
        self._last = Read(SHIPPED, True, 0.0)

    def read(self) -> Read:
        start = time.perf_counter()
        with self._lock:
            try:
                stat = self.path.stat()
                seen: tuple[int, int] | None = (stat.st_mtime_ns, stat.st_size)
            except FileNotFoundError:
                seen = None
            except OSError as e:
                logger.error(
                    "Customization can't be read", extra={"path": str(self.path), "error": str(e)}
                )
                return Read(SHIPPED, True, ms_since(start))
            if seen is None:
                self._seen, self._last = None, Read(SHIPPED, True, 0.0)
            elif seen != self._seen:
                self._seen = seen
                self._last = Read(*self._load(), 0.0)
            return Read(self._last.customization, self._last.shipped, ms_since(start))

    def _load(self) -> tuple[Customization, bool]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return from_dict(data), False
        except (OSError, ValueError) as e:  # JSONDecodeError and CustomizationUnreadable too
            logger.error(
                "Customization can't be read", extra={"path": str(self.path), "error": str(e)}
            )
            return SHIPPED, True


def ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def _sentence(text: str) -> str:
    return text if text[-1:] in ".!?" else f"{text}."


def about_me(identity: Identity) -> list[str]:
    """The identity in the first person, as said to "Who are you?"."""
    said = [
        (identity.name, "I'm {}"),
        (identity.purpose, "My purpose is {}"),
        (identity.audience, "I'm here for {}"),
        (identity.helps_with, "I can help with {}"),
    ]
    return [_sentence(form.format(part)) for part, form in said if part]


def instructions(customization: Customization) -> str:
    """The identity and goals as they are given to the LLM, before the chat's instructions."""
    identity = customization.identity
    parts = []
    mine = about_me(identity)
    if mine:
        parts.append(f'This is who you are, in your own words: "{" ".join(mine)}"')
    if identity.speaks_as:
        parts.append(_sentence(f"You speak as {identity.speaks_as}"))
    if customization.goals:
        parts.append("Your goals: " + " ".join(map(_sentence, customization.goals)))
    return " ".join(parts)


# Questions about the AI itself, matched against the whole prompt as "What can you talk about?"
# is (R41f), so "Who are you talking about?" is not one.
IDENTITY_QUESTIONS = [
    re.compile(p)
    for p in (
        r"who (are|r) you|what are you",
        r"who am i (talking|speaking|chatting) (to|with)",
        r"what('s| is) your (name|purpose|goal|aim|job|role)",
        r"what are your (goals|aims)",
        # "Why are you here?" is "why are you" once its closing "here" is taken off.
        r"what are you (for|here for|meant to do|trying to do)|why are you( here)?",
        r"((can you )?(tell me|talk) about|introduce|describe) yourself",
    )
]


def asks_about_identity(prompt: str) -> bool:
    """Whether the prompt asks who the AI is or what it is for."""
    text = normalized(prompt)
    return any(p.fullmatch(text) for p in IDENTITY_QUESTIONS)
