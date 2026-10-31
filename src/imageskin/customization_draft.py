"""The identity, goals and guidelines drafted by the LLM (roadmap R93, item 86).

The first time the identity is needed and there is no `customization.json` yet, the chosen LLM
drafts the identity and goals from what the app knows (the default person's role, R24c; the
topics in the content, R41f), and new guidelines for each feature whose guidelines are still as
shipped; guidelines the host changed are left alone. It runs in the background, so the shipped
defaults answer until it finishes, within a time limit; a save made meanwhile drops its result.
It runs once; after that, only **Generate again** on the Customization page runs it, and its
result is a draft the host saves or discards.
"""

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from imageskin.chat import Message
from imageskin.customization import (
    FEATURES,
    MOST_GOAL_CHARS,
    MOST_GOALS,
    MOST_GUIDELINES_CHARS,
    MOST_PART_CHARS,
    Customization,
    CustomizationFile,
    CustomizationRefused,
    as_generated,
    fingerprint,
    is_edited,
    with_goals,
    with_guidelines,
    with_identity,
)

logger = logging.getLogger(__name__)

# How long a draft may take before the shipped defaults are kept *(default)*.
GENERATION_TIMEOUT_S = 120.0
# Written once the first draft has run, whatever came of it, so it runs only once.
GENERATED_FILE = "customization.generated"
# The most a draft's reply may take: the identity, a few goals and about a dozen guidelines.
DRAFT_TOKENS = 2400
# The parts of the identity drafted; who it speaks as stays as it is, told to the LLM only.
DRAFTED_IDENTITY = ("name", "purpose", "audience", "helps_with")

AskForJson = Callable[[list[Message], dict[str, Any]], str]


class GenerationFailed(Exception):
    """A draft that couldn't be made, saying why for the log and the page."""


def drafted_features(customization: Customization) -> list[str]:
    """The features whose guidelines are drafted: those still as shipped, or as the LLM drafted
    them before; never those the host changed."""
    return [
        key
        for key in FEATURES
        if not is_edited(customization, key) or key in customization.generated
    ]


def draft_schema(keys: list[str]) -> dict[str, Any]:
    """The JSON the LLM replies with, so a local LLM's reply is held to it by a grammar."""
    text = {"type": "string"}
    return {
        "type": "object",
        "properties": {
            "identity": {
                "type": "object",
                "properties": {part: text for part in DRAFTED_IDENTITY},
                "required": list(DRAFTED_IDENTITY),
            },
            "goals": {"type": "array", "items": text, "minItems": 1, "maxItems": 3},
            "guidelines": {
                "type": "object",
                "properties": {key: text for key in keys},
                "required": keys,
            },
        },
        "required": ["identity", "goals", "guidelines"],
    }


def draft_asked(customization: Customization, person: str | None, topics: list[str]) -> str:
    """What the LLM is asked to draft, with what the app knows and each feature's guidelines as
    shipped to rewrite."""
    keys = drafted_features(customization)
    who = person or "a person whose name and role weren't given"
    about = "; ".join(topics[:20]) if topics else "not read yet"
    features = "\n".join(
        f'- "{key}" ({FEATURES[key].label}): {FEATURES[key].changes} As shipped: '
        f'"{FEATURES[key].shipped}"'
        for key in keys
    )
    return (
        "You are setting up an AI tutor that talks with people face to face, as a person seen"
        f" in a video, about some reference material. The person in the video is {who}. The"
        f" material's topics are: {about}.\n"
        "Write, in JSON:\n"
        '- "identity": a short "name" for the tutor (or an empty string), its "purpose" to follow'
        ' "My purpose is", its "audience" to follow "I\'m here for", and what it "helps_with" to'
        f' follow "I can help with", each at most {MOST_PART_CHARS} characters;\n'
        f'- "goals": one to three goals for the people it talks with, each a sentence of at most'
        f" {MOST_GOAL_CHARS} characters;\n"
        '- "guidelines": for each feature below, guidelines that fit this person and material,'
        " in the same style as the shipped text and no longer than needed, each at most"
        f" {MOST_GUIDELINES_CHARS} characters.\n"
        f"{features}"
    )


def _json_in(reply: str) -> dict[str, Any]:
    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end < start:
        raise GenerationFailed("the reply has no JSON object")
    try:
        data = json.loads(reply[start : end + 1])
    except json.JSONDecodeError as e:
        raise GenerationFailed(f"the reply is not valid JSON: {e.msg}") from e
    if not isinstance(data, dict):
        raise GenerationFailed("the reply is not a JSON object")
    return data


def drafted(customization: Customization, reply: str) -> Customization:
    """`customization` with the identity, goals and the guidelines still as shipped taken from
    the LLM's `reply`, checked as an edit on the page is."""
    data = _json_in(reply)
    identity, goals, guidelines = (data.get(k) for k in ("identity", "goals", "guidelines"))
    if not isinstance(identity, dict) or not isinstance(guidelines, dict):
        raise GenerationFailed("the reply has no identity or guidelines")
    try:
        draft = with_identity(customization, {k: identity.get(k, "") for k in DRAFTED_IDENTITY})
        draft = with_goals(draft, goals[:MOST_GOALS] if isinstance(goals, list) else goals)
        drafted = []
        for key in drafted_features(customization):
            text = guidelines.get(key)
            if isinstance(text, str) and text.strip():
                draft = with_guidelines(draft, key, text)
                drafted.append(key)
    except CustomizationRefused as e:
        raise GenerationFailed(str(e)) from e
    draft = as_generated(draft, drafted)
    if not draft.goals:
        draft = replace(draft, goals=customization.goals)
    return draft


def generate(
    customization: Customization,
    ask: AskForJson,
    person: str | None,
    topics: list[str],
    timeout_s: float = GENERATION_TIMEOUT_S,
) -> Customization:
    """A draft of `customization` by the LLM, within `timeout_s`. The ask is left to finish on
    its own after the time limit, as a request can't be taken back."""
    messages: list[Message] = [
        {"role": "user", "content": draft_asked(customization, person, topics)}
    ]
    schema = draft_schema(drafted_features(customization))
    result: dict[str, Any] = {}

    def run() -> None:
        try:
            result["reply"] = ask(messages, schema)
        except Exception as e:  # noqa: BLE001 (any failure keeps the defaults)
            result["error"] = e

    worker = threading.Thread(target=run, name="customization-draft", daemon=True)
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        raise GenerationFailed(f"no reply within {timeout_s:g} s")
    if "error" in result:
        raise GenerationFailed(f"the LLM failed: {result['error']}")
    return drafted(customization, str(result["reply"]))


def ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


class Generator:
    """Drafts the customization once, in the background, the first time it is needed with no
    `customization.json`, and again as a draft when the host asks."""

    def __init__(
        self,
        file: CustomizationFile,
        ask: AskForJson,
        person: Callable[[], str | None],
        topics: Callable[[], list[str]],
        timeout_s: float = GENERATION_TIMEOUT_S,
    ) -> None:
        self._file = file
        self._ask = ask
        self._person = person
        self._topics = topics
        self._timeout_s = timeout_s
        self._marker: Path = file.path.with_name(GENERATED_FILE)
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None

    def needed(self) -> None:
        """Start the first draft if it hasn't run and nothing was saved yet; never waits."""
        with self._lock:
            if self._worker is not None or self._marker.exists() or self._file.path.exists():
                return
            self._worker = threading.Thread(
                target=self._first, name="customization-generation", daemon=True
            )
            self._worker.start()

    def wait(self, timeout_s: float | None = None) -> None:
        """Wait for the first draft, if it is running (tests and shutdown)."""
        worker = self._worker
        if worker is not None:
            worker.join(timeout_s)

    def _inputs(self) -> tuple[str | None, list[str]]:
        try:
            return self._person(), self._topics()
        except Exception:
            logger.exception("Could not read what the customization is drafted from")
            return None, []

    def _first(self) -> None:
        start = time.perf_counter()
        read = self._file.read()
        changes = self._file.changes
        person, topics = self._inputs()
        try:
            draft = generate(read.customization, self._ask, person, topics, self._timeout_s)
        except GenerationFailed as e:
            logger.warning(
                "Customization generation failed",
                extra={"reason": str(e), "duration_ms": ms_since(start)},
            )
            self._ran()
            return
        try:
            saved = self._file.change_if(
                changes, lambda now: draft, made_by="generated", part="draft"
            )
        except OSError as e:
            logger.error(
                "Customization generation failed",
                extra={"reason": f"it could not be saved: {e}", "duration_ms": ms_since(start)},
            )
            self._ran()
            return
        if saved is None:
            logger.info("Customization generation dropped", extra={"duration_ms": ms_since(start)})
        else:
            logger.info(
                "Customization generated",
                extra={
                    "duration_ms": ms_since(start),
                    "features": len(drafted_features(read.customization)),
                    "topics": len(topics),
                    "person": person is not None,
                },
            )
        self._ran()

    def _ran(self) -> None:
        try:
            self._marker.parent.mkdir(parents=True, exist_ok=True)
            self._marker.write_text("1", encoding="utf-8")
        except OSError as e:
            logger.error("Customization generation not noted", extra={"error": str(e)})

    def again(self) -> tuple[Customization, list[str], str]:
        """A new draft of the customization as it is now, not saved, with the features whose
        guidelines it drafted and the `fingerprint` of what it was drafted from, so saving it
        can tell whether anything was saved since; raises GenerationFailed."""
        start = time.perf_counter()
        current = self._file.read().customization
        person, topics = self._inputs()
        try:
            draft = generate(current, self._ask, person, topics, self._timeout_s)
        except GenerationFailed as e:
            logger.warning(
                "Customization generation failed",
                extra={"reason": str(e), "duration_ms": ms_since(start), "draft": True},
            )
            raise
        logger.info(
            "Customization generated",
            extra={"duration_ms": ms_since(start), "draft": True, "topics": len(topics)},
        )
        return draft, drafted_features(current), fingerprint(current)
