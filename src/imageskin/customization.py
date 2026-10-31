"""The AI's identity, its goals and each feature's guidelines (roadmap R92, items 84 and 85).

They are kept together in `customization.json` in the app's home folder, the only copy, with a
fixed default shipped for when the file is missing or can't be read. The identity and goals are
given to the LLM with every prompt, and "Who are you?", "What is your purpose?" and the like are
recognized as "What can you talk about?" is (R41f) and answered from the identity here, so they
cost no LLM call and are answered with general prompts off. Each feature's guidelines are added by
its own PR (R194 to R200), as an entry in FEATURES; until then there are none. A signed-in host
edits all of them on the Customization page (R94).
"""

import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
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


@dataclass(frozen=True)
class Feature:
    """A feature whose guidelines the host can edit (R194 to R200): its name on the Customization
    page, what its guidelines change and what stays as the code makes it, and the text they ship
    with, which describes what the feature does today."""

    label: str
    changes: str
    stays: str
    shipped: str


# Answering questions' guidelines as shipped (R194): how every answer was asked to be written
# before they could be edited, word for word, so nothing changes until the host edits them.
ANSWERING = (
    "Answer from the reference text when it covers the question, in your own words, without"
    " mentioning documents or pages."
)

# Topics' guidelines as shipped (R195): what a reply about a topic as a whole is today, one
# answered as any question is. Only edited ones are sent, so until then the prompt is as before.
TOPICS = (
    "Talk about the topic as you answer any question: from the reference text, in your own words."
)

# Teach me's guidelines as shipped (R196): how each part of a lesson is asked for today. As
# shipped, the parts are asked for word for word as before; edited, they say how to teach.
TEACHING = (
    "Teach each part as a tutor talking to someone new to it, in two to four short sentences,"
    " and sum up each topic in one sentence. Don't ask me anything."
)

# Quiz me's guidelines as shipped (R197), in two parts: how a question is written and how an
# answer is judged, each what it was asked with before, so as shipped nothing changes.
QUIZ_QUESTIONS = (
    "Ask something that can be answered in a sentence from the reference text, without"
    " mentioning the reference text."
)
QUIZ_JUDGING = (
    "Then give the correct answer and a one-line reason, kindly, in at most two more sentences."
    " Don't mention the reference text, and don't ask anything."
)

# The assessment's guidelines as shipped (R198), in the same two parts as Quiz me's, each what
# it was asked with before, so as shipped nothing changes.
ASSESSMENT_QUESTIONS = (
    "Ask something that can be answered in a sentence or two from the reference text, without"
    " mentioning the reference text."
)
ASSESSMENT_JUDGING = "Judge the answer from the reference text."

# Each feature's guidelines, by the key they are kept under in `guidelines`, in the order the page
# shows them. Each guideline PR adds its feature here (R194 to R200).
FEATURES: dict[str, Feature] = {
    "questions": Feature(
        "Answering questions",
        "They are given to the LLM with every question it answers, from the PDFs or not, typed"
        " or said with Hold to talk.",
        "Which questions are declined with general prompts off stays as the code decides, and"
        " what is quoted from the PDFs stays as it is found.",
        ANSWERING,
    ),
    "topics": Feature(
        "Topics",
        "They are given to the LLM with every reply about a topic as a whole: a topic or example"
        ' question picked under the prompt box, "Tell me about" a topic, or "Tell me about the'
        ' first one" after the topics were named.',
        'The topic list, the reply to "What can you talk about?" and the hints under the prompt'
        " box stay as the code makes them.",
        TOPICS,
    ),
    "teach me": Feature(
        "Teach me",
        "They are given to the LLM with every part of a lesson it writes: a topic's main ideas,"
        " each entry under it and the one-line summary.",
        "The order of the topics and parts, what was covered, Next and Stop stay as the code"
        " makes them, and Say it simpler has its own guidelines.",
        TEACHING,
    ),
    "quiz questions": Feature(
        "Quiz me: questions",
        "They are given to the LLM with each quiz question it writes.",
        'The number of questions, "How many are left?", the score and the summary at the end'
        " stay as the code makes them, and each question is still one, ending with a question"
        " mark.",
        QUIZ_QUESTIONS,
    ),
    "quiz judging": Feature(
        "Quiz me: judging",
        "They are given to the LLM with each answer it judges.",
        'Each judgment still starts with "Right!", "Partly right." or "Not quite.", which the'
        " score is counted from, and an answer the participant doesn't know is given as before.",
        QUIZ_JUDGING,
    ),
    "assessment questions": Feature(
        "Assessment: questions",
        "They are given to the LLM with each assessment question it writes, at each level:"
        " recalling facts, explaining ideas, and applying and connecting ideas.",
        "The number of questions, which topics and levels are asked, the scores and the"
        " evaluation stay as the code makes them, and each question is still one, ending with a"
        " question mark.",
        ASSESSMENT_QUESTIONS,
    ),
    "assessment judging": Feature(
        "Assessment: judging",
        "They are given to the LLM with each answer it judges.",
        "Each judgment is still a verdict (Right, Partly right or Not quite) and the correct"
        " answer, kept for the evaluation, which is worked out the same way.",
        ASSESSMENT_JUDGING,
    ),
}


def guidelines_of(customization: Customization, key: str) -> str:
    """A feature's guidelines: as the host edited them, or as shipped."""
    edited = customization.guidelines.get(key)
    return edited if isinstance(edited, str) else FEATURES[key].shipped


def is_edited(customization: Customization, key: str) -> bool:
    """Whether the host edited a feature's guidelines."""
    return isinstance(customization.guidelines.get(key), str)


# The most an edit may hold, so the instructions sent with every prompt stay short *(default)*.
MOST_PART_CHARS = 500
MOST_GOALS = 10
MOST_GOAL_CHARS = 300
MOST_GUIDELINES_CHARS = 2000


class CustomizationRefused(ValueError):
    """An edit that can't be saved, saying why in words for the page."""


class NoSuchFeature(KeyError):
    pass


def _checked(text: object, what: str, most: int) -> str:
    if not isinstance(text, str):
        raise CustomizationRefused(f"{what} must be text.")
    text = text.strip()
    if len(text) > most:
        raise CustomizationRefused(f"{what} is too long: at most {most} characters.")
    return text


IDENTITY_LABELS = {
    "name": "The name",
    "speaks_as": "Speaks as",
    "purpose": "The purpose",
    "audience": "Who it is for",
    "helps_with": "What it can help with",
}


def with_identity(customization: Customization, parts: dict[str, object]) -> Customization:
    """The customization with these parts of the identity changed."""
    unknown = sorted(set(parts) - set(IDENTITY_LABELS))
    if unknown:
        raise CustomizationRefused(f"The identity has no {', '.join(unknown)}.")
    changed = {k: _checked(v, IDENTITY_LABELS[k], MOST_PART_CHARS) for k, v in parts.items()}
    return replace(customization, identity=replace(customization.identity, **changed))


def with_goals(customization: Customization, goals: object) -> Customization:
    """The customization with these goals; empty ones are left out."""
    if not isinstance(goals, list):
        raise CustomizationRefused("The goals must be a list.")
    kept = [g for g in (_checked(g, "A goal", MOST_GOAL_CHARS) for g in goals) if g]
    if len(kept) > MOST_GOALS:
        raise CustomizationRefused(f"There can be at most {MOST_GOALS} goals.")
    return replace(customization, goals=tuple(kept))


def with_guidelines(customization: Customization, key: str, text: object) -> Customization:
    """The customization with a feature's guidelines changed, or, with `text` None, set back to
    how they shipped."""
    if key not in FEATURES:
        raise NoSuchFeature(key)
    guidelines = dict(customization.guidelines)
    if text is None:
        guidelines.pop(key, None)
    else:
        label = f"{FEATURES[key].label}'s guidelines"
        guidelines[key] = _checked(text, label, MOST_GUIDELINES_CHARS)
    return replace(customization, guidelines=guidelines)


def features(customization: Customization) -> list[dict[str, Any]]:
    """Each feature's guidelines as the Customization page shows them."""
    return [
        {
            "key": key,
            **asdict(feature),
            "text": guidelines_of(customization, key),
            "edited": is_edited(customization, key),
        }
        for key, feature in FEATURES.items()
    ]


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
            return self._read(start)

    def change(self, edit: Callable[[Customization], Customization]) -> Customization:
        """Save `edit` of the customization as it is now, one change at a time, so two saves
        made at once both count. A broken file is replaced by the shipped default, edited."""
        with self._lock:
            edited = edit(self._read(time.perf_counter()).customization)
            save(self.path.parent, edited)
            stat = self.path.stat()
            self._seen = (stat.st_mtime_ns, stat.st_size)
            self._last = Read(edited, False, 0.0)
            return edited

    def _read(self, start: float) -> Read:
        """`read`, holding the lock."""
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
