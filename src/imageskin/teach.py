"""Teach me (roadmap R41h, item 54): the person teaches the content a part at a time.

A lesson goes through the topics (the wiki's main entries, R41f) in order, from the one the
participant picks. Each topic is taught in parts: first its main ideas (the topic's own wiki entry),
then each entry under it, in the order the wiki has them, then a one-line summary, and on to the
next topic. After each part the participant can say "next", ask for it again more simply, or ask a
question about it. Where the lesson is kept is up to the caller: the browser keeps it, so a
participant who stops picks up where they left off (`Lesson`).

Each prompt is given to `Tutor.step`, which says what to do with it: nothing (an ordinary
prompt), a reply made here (`Say`), or a part for the LLM to teach (`Explain`).
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from imageskin.chat import Teach
from imageskin.customization import TEACHING
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
# While a PDF is still being read, everything is only what there is so far (review on PR #87).
EVERYTHING_SO_FAR = "Everything so far, from the start"
MORE_COMING = "More material is still being read, so more topics will come."
CHOOSE = "What would you like to learn about?"
# Said when a lesson goes past the last topic.
ALL_DONE = "That's everything in the material I was given. Well done for getting through it all!"
STOPPED = "OK, we'll stop here. Click Teach me any time to carry on where we left off."
NO_LESSON = "There's nothing to teach yet: no material has been added."
# Said when the PDFs added are still being read and none has a topic yet (review on PR #87).
STILL_READING_LESSON = (
    "I'm still reading the material I was given, so there's nothing to teach yet. Click Teach"
    " me again in a little while."
)
# Said when a lesson reaches the last topic so far while more material is still being read.
NOT_YET = (
    "That's all I have so far: more material is still being read. Say next again in a moment"
    " to carry on."
)


@dataclass(frozen=True)
class Lesson:
    """Where a lesson is: the topic (its title) and the part being taught, from 0. The part
    after a topic's last is its summary. `active` is false once the participant stops."""

    topic: str
    part: int
    active: bool = True


@dataclass(frozen=True)
class Part:
    title: str
    summary: str


@dataclass(frozen=True)
class Choice:
    """A choice offered when the participant hasn't said what to learn: shown as a button that
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


def asks_simpler(prompt: str) -> bool:
    """Whether the prompt asks for what was just said, said more simply (R41h, R157)."""
    return _SIMPLER.fullmatch(plain(prompt)) is not None


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


def summed_up(parts: list[Part]) -> list[str]:
    """The material a topic's summary is made from: every part's wiki entry."""
    return [f"{p.title}: {p.summary}" for p in parts]


def same_entry(found: str, part: Part) -> bool:
    """Whether a passage found ("Title (book.pdf, page 2): text") is the part's own wiki entry,
    or one with the same title whose summary the part already has."""
    found = " ".join(found.split())
    if not found.casefold().startswith(f"{part.title} (".casefold()) or "): " not in found:
        return False
    text = found.split("): ", 1)[1].removesuffix(" …")
    return text in " ".join(part.summary.split())


def what(topic: str, parts: list[Part], part: int) -> str:
    """The part named for the LLM."""
    if part == 0:
        return f'the main ideas of "{topic}"'
    return f'"{parts[part].title}", part of "{topic}"'


# What edited Teach me guidelines (R196) are said after, in what a lesson part asks.
TEACH_GUIDELINES = "Guidelines for teaching:"


def explain(
    topic: str, parts: list[Part], part: int, simpler: bool = False, guidelines: str = TEACHING
) -> str:
    """What the LLM is asked to teach one part, with the Teach me guidelines (R196). As shipped,
    they are what it was asked before them, word for word, so a part written ahead (R98a) is
    still used; edited, they take the place of how to teach."""
    shipped = guidelines == TEACHING
    if part >= len(parts):
        summary = (
            f'Sum up in one sentence what we have just learned about "{topic}". Say only that'
            " sentence."
        )
        return summary if shipped else f"{summary} {TEACH_GUIDELINES} {guidelines}"
    if simpler:  # Say it simpler's own guidelines come with R200
        return (
            f"Explain {what(topic, parts, part)} again, more simply: in two or three short"
            " sentences, with everyday words and an everyday example. Don't ask me anything."
        )
    if not shipped:
        return f"Teach me {what(topic, parts, part)}. {TEACH_GUIDELINES} {guidelines}"
    return (
        f"Teach me {what(topic, parts, part)}, as a tutor talking to someone new to it, in"
        " two to four short sentences. Don't ask me anything."
    )


class Tutor:
    """Decides what each prompt does to the lesson, from the wiki as it is now."""

    def __init__(
        self,
        contents: Callable[[], list[dict[str, Any]]],
        find: Callable[[str], list[str]],
        complete: Callable[[], bool] = lambda: True,
        # Teach me's guidelines as they are now (R196), read for each part asked for.
        guidelines: Callable[[], str] = lambda: TEACHING,
    ) -> None:
        self._guidelines = guidelines
        self._contents = contents
        self._find = find
        # Whether every PDF has been read and its wiki built, so the topics are all of them.
        self._complete = complete

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
        if asks_simpler(text):
            return self._explain(here, parts, "simpler")
        if _NEXT.fullmatch(text):
            if part < len(parts):
                return self._explain(Lesson(lesson.topic, part + 1), parts, "next")
            names = list(topics)
            after = names[names.index(lesson.topic) + 1 :]
            if not after and not self._complete():  # stays on the summary until there is more
                logger.info("Lesson waiting for material", extra={"topic": lesson.topic})
                return Say([NOT_YET], here, [])
            if not after:
                logger.info("Lesson finished", extra={"topic": lesson.topic})
                return Say([ALL_DONE], None, [])
            return self._explain(Lesson(after[0], 0), topics[after[0]], "next")
        # A question about the part being taught ("Why is that?" names nothing to look up),
        # answered from that part's material (on the summary, the whole topic's, as the summary
        # was made from); the lesson stays where it is.
        logger.info("Lesson question", extra={"topic": lesson.topic, "part": part})
        if part >= len(parts):
            material = summed_up(parts)
        else:
            material = self.material(lesson.topic, parts, part)
        material += self.found(prompt)
        return Explain(Teach(prompt, material), here, "question")

    def _topics(self) -> dict[str, list[Part]]:
        return lesson_topics(self._contents())

    def first_parts(self) -> dict[str, Teach]:
        """Each topic's first part, its main ideas, as a lesson starting there asks the LLM
        for it, so it can be written ahead (R98a)."""
        guidelines = self._teaching()
        return {
            topic: Teach(
                explain(topic, parts, 0, guidelines=guidelines), self.material(topic, parts, 0)
            )
            for topic, parts in self._topics().items()
        }

    def _start(
        self, asked: re.Match[str], topics: dict[str, list[Part]], lesson: Lesson | None
    ) -> Step:
        if not topics:
            waiting = not self._complete()
            logger.info("No lesson to give", extra={"still_reading": waiting})
            return Say([STILL_READING_LESSON if waiting else NO_LESSON], lesson, [])
        if asked["all"]:
            first = next(iter(topics))
            return self._explain(Lesson(first, 0), topics[first], "start")
        if asked["about"] is None:
            return self._choose(topics, lesson)
        topic = self.topic_named(asked["about"], topics)
        if topic is None:
            return self._choose(topics, lesson, f"I don't have a topic called {asked['about']}.")
        if lesson is not None and lesson.topic == topic:  # carry on where they left off
            part = min(lesson.part, len(topics[topic]))
            return self._explain(Lesson(topic, part), topics[topic], "resume")
        return self._explain(Lesson(topic, 0), topics[topic], "start")

    @staticmethod
    def topic_named(about: str, topics: dict[str, list[Part]]) -> str | None:
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
        complete = self._complete()
        choices = [Choice(t, f"Teach me about {t}") for t in topics]
        everything = EVERYTHING if complete else EVERYTHING_SO_FAR
        choices.append(Choice(everything, "Teach me everything from the start"))
        if lesson is not None and lesson.topic in topics:
            carry_on = Choice(f"Carry on with {lesson.topic}", f"Teach me about {lesson.topic}")
            choices.insert(0, carry_on)
        sentences = [first] if first else []
        sentences += [CHOOSE, "Pick one of the topics, or everything from the start."]
        if not complete:
            sentences.append(MORE_COMING)
        logger.info("Lesson topic asked for", extra={"topics": len(topics)})
        return Say(sentences, lesson, choices)

    def _explain(self, lesson: Lesson, parts: list[Part], kind: str) -> Explain:
        part = lesson.part
        logger.info(
            "Lesson part",
            extra={"topic": lesson.topic, "part": part, "parts": len(parts), "kind": kind},
        )
        simpler = kind == "simpler"
        guidelines = TEACHING if simpler else self._teaching()
        if not simpler:
            logger.info(
                "Guidelines used",
                extra={"feature": "teach me", "edited": guidelines != TEACHING},
            )
        if part >= len(parts):
            teach = Teach(
                explain(lesson.topic, parts, part, guidelines=guidelines), summed_up(parts)
            )
            return Explain(teach, lesson, "summary")
        material = self.material(lesson.topic, parts, part)
        teach = Teach(explain(lesson.topic, parts, part, simpler, guidelines), material)
        return Explain(teach, lesson, kind)

    def _teaching(self) -> str:
        """Teach me's guidelines now, or as shipped when they can't be read."""
        try:
            return self._guidelines()
        except Exception:
            logger.exception("Could not read the Teach me guidelines")
            return TEACHING

    def material(self, topic: str, parts: list[Part], part: int) -> list[str]:
        """The part's own wiki entry, then what else the content has on it: the lookup finds
        that entry too, so it is left out there, not given twice (review on PR #87)."""
        p = parts[part]
        found = self.found(p.title if part else topic)
        return [f"{p.title}: {p.summary}", *[f for f in found if not same_entry(f, p)]]

    def found(self, question: str) -> list[str]:
        try:
            return self._find(question)
        except Exception:
            logger.exception("Could not look the lesson part up in the content")
            return []
