"""Teach me (roadmap R41h, item 54): the person teaches the content a part at a time.

A lesson goes through the topics (the wiki's main entries, R41f) in order, from the one the
student picks. Each topic is taught in parts: first its main ideas (the topic's own wiki entry),
then each entry under it, in the order the wiki has them, then a one-line summary, and on to the
next topic. After each part the student can say "next", ask for it again more simply, or ask a
question about it. Where the lesson is kept is up to the caller: the browser keeps it, so a
student who stops picks up where they left off (`Lesson`).

Each prompt is given to `Teacher.step`, which says what to do with it: nothing (an ordinary
prompt), a reply made here (`Say`), or a part for the LLM to teach (`Explain`).
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from imageskin.chat import Teach
from imageskin.lookup import named_topic

logger = logging.getLogger(__name__)

# "Teach me", "Can you teach me about the zeta function?", "Please teach me everything".
_TEACH = re.compile(
    r"(?:(?:please|ok|okay|so|now|can you|could you|will you|would you)\s+)*teach me"
    r"(?:\s+(?:about|on)\s+(?P<about>.+?)|\s+(?P<all>everything(?:,? from the start)?))?"
    r"(?:\s+please)?"
)
_NEXT = re.compile(
    r"(?:ok(?:ay)?,? )?(?:next(?: part| one)?|go on|continue|carry on|keep going|what'?s next)"
    r"(?: please)?"
)
_SIMPLER = re.compile(
    r"(?:(?:can you |please )?(?:say|explain|tell me) (?:it|that)(?: again)?,? )?"
    r"(?:more simply|simpler|in simpler words)(?: please)?"
    r"|i don'?t (?:get|understand) (?:it|that)"
)
_STOP = re.compile(r"stop(?: the lesson| teaching(?: me)?)?|end the lesson|that'?s enough")
_PUNCTUATION = re.compile(r"[^\w\s',]+")

EVERYTHING = "Everything, from the start"
CHOOSE = "What would you like to learn about?"
# Said when a lesson goes past the last topic.
ALL_DONE = "That's everything in the material I was given. Well done for getting through it all!"
STOPPED = "OK, we'll stop here. Click Teach me any time to carry on where we left off."
NO_LESSON = "There's nothing to teach yet: no material has been added."


@dataclass(frozen=True)
class Lesson:
    """Where a lesson is: the topic (its title) and the part being taught, from 0. The part
    after a topic's last is its summary. `active` is false once the student stops."""

    topic: str
    part: int
    active: bool = True


@dataclass(frozen=True)
class Part:
    title: str
    summary: str


@dataclass(frozen=True)
class Choice:
    """A choice offered when the student hasn't said what to learn: shown as a button that
    sends `prompt`."""

    label: str
    prompt: str


@dataclass(frozen=True)
class Say:
    """A reply made here, and the lesson after it (None when it is over)."""

    sentences: list[str]
    lesson: Lesson | None
    choices: list[Choice]


@dataclass(frozen=True)
class Explain:
    """A part for the LLM to teach, and the lesson after it."""

    teach: Teach
    lesson: Lesson
    kind: str  # for the log: "start", "resume", "next", "simpler", "summary" or "question"


Step = Say | Explain | None


def plain(prompt: str) -> str:
    text = _PUNCTUATION.sub(" ", prompt.lower().replace("’", "'"))
    return " ".join(text.split()).strip(" ,")


def lesson_topics(contents: list[dict[str, Any]]) -> dict[str, list[Part]]:
    """Each topic's parts, in the order the wiki has them: the topic's own entry (its main
    ideas), then every entry under it, depth first. A topic several PDFs have (the same title,
    shown once, R41f) is taught from all of them: an entry already taught takes the later PDF's
    summary as well, and every other entry under it follows (review on PR #87)."""

    def walk(entries: list[dict[str, Any]]) -> list[Part]:
        found = []
        for e in entries:
            found.append(Part(" ".join(str(e["title"]).split()), str(e.get("summary", ""))))
            found += walk(e.get("entries") or [])
        return found

    topics: dict[str, list[Part]] = {}
    named: dict[str, str] = {}  # each topic's title, by its casefolded title
    for pdf in contents:
        for entry in pdf["entries"]:
            parts = walk([entry])
            key = parts[0].title.casefold()
            if not key:
                continue
            if key not in named:
                named[key] = parts[0].title
                topics[parts[0].title] = parts
                continue
            have = topics[named[key]]
            places = {p.title.casefold(): i for i, p in reversed(list(enumerate(have)))}
            for part in parts:
                i = places.get(part.title.casefold())
                if i is None:
                    places[part.title.casefold()] = len(have)
                    have.append(part)
                elif part.summary and part.summary not in have[i].summary:
                    have[i] = replace(have[i], summary=f"{have[i].summary} {part.summary}".strip())
    return topics


def what(topic: str, parts: list[Part], part: int) -> str:
    """The part named for the LLM."""
    if part == 0:
        return f'the main ideas of "{topic}"'
    return f'"{parts[part].title}", part of "{topic}"'


def explain(topic: str, parts: list[Part], part: int, simpler: bool = False) -> str:
    """What the LLM is asked to teach one part."""
    if part >= len(parts):
        return (
            f'Sum up in one sentence what we have just learned about "{topic}". Say only that'
            " sentence."
        )
    if simpler:
        return (
            f"Explain {what(topic, parts, part)} again, more simply: in two or three short"
            " sentences, with everyday words and an everyday example. Don't ask me anything."
        )
    return (
        f"Teach me {what(topic, parts, part)}, as a teacher talking to a student new to it, in"
        " two to four short sentences. Don't ask me anything."
    )


class Teacher:
    """Decides what each prompt does to the lesson, from the wiki as it is now."""

    def __init__(
        self,
        contents: Callable[[], list[dict[str, Any]]],
        find: Callable[[str], list[str]],
    ) -> None:
        self._contents = contents
        self._find = find

    def step(self, prompt: str, lesson: Lesson | None) -> Step:
        """What to do with the prompt, given the lesson the browser has (None when there was
        never one, or it was finished)."""
        text = plain(prompt)
        asked = _TEACH.fullmatch(text)
        active = lesson is not None and lesson.active
        if asked is None and not active:
            return None
        topics = self._topics()
        if asked is not None:
            return self._start(asked, topics, lesson)
        assert lesson is not None
        parts = topics.get(lesson.topic)
        if parts is None:  # its topic is gone from the wiki: start again from the choices
            logger.info("Lesson topic gone", extra={"topic": lesson.topic})
            return self._choose(topics, None, f'"{lesson.topic}" is no longer in the material.')
        part = min(lesson.part, len(parts))
        here = Lesson(lesson.topic, part)
        if _STOP.fullmatch(text):
            logger.info("Lesson stopped", extra={"topic": lesson.topic, "part": part})
            return Say([STOPPED], replace(here, active=False), [])
        if _SIMPLER.fullmatch(text):
            return self._explain(here, parts, "simpler")
        if _NEXT.fullmatch(text):
            if part < len(parts):
                return self._explain(Lesson(lesson.topic, part + 1), parts, "next")
            names = list(topics)
            after = names[names.index(lesson.topic) + 1 :]
            if not after:
                logger.info("Lesson finished", extra={"topic": lesson.topic})
                return Say([ALL_DONE], None, [])
            return self._explain(Lesson(after[0], 0), topics[after[0]], "next")
        # A question about the part being taught ("Why is that?" names nothing to look up),
        # answered from that part's material; the lesson stays where it is.
        logger.info("Lesson question", extra={"topic": lesson.topic, "part": part})
        material = self._material(lesson.topic, parts, min(part, len(parts) - 1))
        material += self._found(prompt)
        return Explain(Teach(prompt, material), here, "question")

    def _topics(self) -> dict[str, list[Part]]:
        return lesson_topics(self._contents())

    def _start(
        self, asked: re.Match[str], topics: dict[str, list[Part]], lesson: Lesson | None
    ) -> Step:
        if not topics:
            return Say([NO_LESSON], lesson, [])
        if asked["all"]:
            first = next(iter(topics))
            return self._explain(Lesson(first, 0), topics[first], "start")
        if asked["about"] is None:
            return self._choose(topics, lesson)
        topic = self._topic(asked["about"], topics)
        if topic is None:
            return self._choose(topics, lesson, f"I don't have a topic called {asked['about']}.")
        if lesson is not None and lesson.topic == topic:  # carry on where they left off
            part = min(lesson.part, len(topics[topic]))
            return self._explain(Lesson(topic, part), topics[topic], "resume")
        return self._explain(Lesson(topic, 0), topics[topic], "start")

    @staticmethod
    def _topic(about: str, topics: dict[str, list[Part]]) -> str | None:
        """The topic `about` names: one whose title it is, or names (R41f)."""
        about = about.strip(" ,").removeprefix("the ")
        for title in topics:
            if plain(title).removeprefix("the ") == about:
                return title
        contents = [{"entries": [{"title": t} for t in topics]}]
        return named_topic(about, contents)

    def _choose(
        self, topics: dict[str, list[Part]], lesson: Lesson | None, first: str | None = None
    ) -> Say:
        """Ask which topic to learn: the topics, everything from the start, and carrying on
        with the one left off, if any."""
        choices = [Choice(t, f"Teach me about {t}") for t in topics]
        choices.append(Choice(EVERYTHING, "Teach me everything from the start"))
        if lesson is not None and lesson.topic in topics:
            carry_on = Choice(f"Carry on with {lesson.topic}", f"Teach me about {lesson.topic}")
            choices.insert(0, carry_on)
        sentences = [first] if first else []
        sentences += [CHOOSE, "Pick one of the topics, or everything from the start."]
        logger.info("Lesson topic asked for", extra={"topics": len(topics)})
        return Say(sentences, lesson, choices)

    def _explain(self, lesson: Lesson, parts: list[Part], kind: str) -> Explain:
        part = lesson.part
        logger.info(
            "Lesson part",
            extra={"topic": lesson.topic, "part": part, "parts": len(parts), "kind": kind},
        )
        if part >= len(parts):
            material = [f"{p.title}: {p.summary}" for p in parts]
            return Explain(Teach(explain(lesson.topic, parts, part), material), lesson, "summary")
        material = self._material(lesson.topic, parts, part)
        teach = Teach(explain(lesson.topic, parts, part, kind == "simpler"), material)
        return Explain(teach, lesson, kind)

    def _material(self, topic: str, parts: list[Part], part: int) -> list[str]:
        """The part's own wiki entry, then what the PDFs say about it."""
        p = parts[part]
        return [f"{p.title}: {p.summary}", *self._found(p.title if part else topic)]

    def _found(self, question: str) -> list[str]:
        try:
            return self._find(question)
        except Exception:
            logger.exception("Could not look the lesson part up in the content")
            return []
