"""The assessment (roadmap R41j, item 55): what the student knows across all the content.

An assessment asks at least AT_LEAST questions, or one per main topic when there are more, one
at a time. Each is on one main topic (a main wiki entry, R41f) and at one level: recalling a
fact, explaining an idea, or applying and connecting ideas. Every topic is asked about once
before any is asked about twice, and the levels take turns, so they are split as evenly as can
be. A recall question is written from the topic's main ideas, a deeper one from the entries
under it. Each answer is judged from the material its question was written from, as in Quiz me
(R41i), but the verdict and the correct answer are kept for the end, so the assessment doesn't
teach as it goes. It ends with an evaluation: the overall result, breadth (the topics answered
well), depth (each level), the answers missed, and what to go over again, with Teach me offered
on it. Where the assessment is, is kept by the browser (`Assessment`), as a quiz is.

Each prompt is given to `Assessor.step`, which returns nothing (not an assessment prompt) or a
reply made here (`Assessed`), with the assessment after it.
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from imageskin.chat import LlmError
from imageskin.quiz import (
    AGAIN,
    EXPLAIN,
    PARTLY,
    REVEAL,
    RIGHT,
    WRONG,
    asked_for,
    fingerprint,
    first_question,
    verdict,
)
from imageskin.teach import Choice, Part, Teacher, lesson_topics, plain, what
from imageskin.topics import spoken_list

logger = logging.getLogger(__name__)

AT_LEAST = 15
MOST_QUESTIONS = 200  # so a browser can't send an endless one; more topics than this is unlikely
RECALL, EXPLAIN_IT, APPLY = 0, 1, 2
LEVELS = ("recalling facts", "explaining ideas", "applying and connecting ideas")

# "Assess me", "Can you test me on everything?", "Assessment please".
_ASSESS = re.compile(
    r"(?:(?:please|ok|okay|so|now|can you|could you|will you|would you)\s+)*"
    r"(?:assess me|test me on everything|give me an assessment|assessment)(?:\s+please)?"
)
_STOP = re.compile(r"stop(?: the assessment)?|end the assessment|that'?s enough")

# What each level asks the LLM for, and the questions asked when it can't write one, in turn:
# as many as a level can have on one part (AT_LEAST / 3), each answerable from any material.
_ASK = (
    "asks the student to recall one fact from",
    "asks the student to explain one idea from, in their own words,",
    "asks the student to apply or connect ideas from",
)
_PLAIN = (
    (
        "What is one fact about {}?",
        "What can you tell me about {}?",
        "What is the main idea of {}?",
        "What is one thing you know about {}?",
        "In a sentence, what is {} about?",
    ),
    (
        "How would you explain {} in your own words?",
        "How would you describe {} to a friend?",
        "What does {} mean, in your own words?",
        "How would you sum up {} simply?",
        "In your own words, what is {} about?",
    ),
    (
        "How do the ideas in {} fit together?",
        "How does one idea in {} lead to another?",
        "How are the ideas in {} connected?",
        "What follows from the ideas in {}?",
        "How would you use the ideas in {}?",
    ),
)

CHOOSE_NOTHING = "There's nothing to assess you on yet: no material has been added."
STILL_READING = (
    "I'm still reading the material I was given, so there's nothing to assess you on yet. Ask"
    " again in a little while."
)
STOPPED = "OK, we'll stop the assessment here."
CHANGED = "The material has changed since this question was asked, so here's a new one."
GONE = "The material has changed, so the assessment can't go on."
NO_EXPLAINING = (
    "In an assessment I can't explain the questions, so answer as best you can, or say you"
    " don't know."
)
NOTHING_TO_GO_OVER = "Well done: there's nothing to go over again!"


@dataclass(frozen=True)
class Answer:
    """An answer given: its question, the question's topic and level, how it was judged, and
    the correct answer, kept for the end."""

    topic: str
    level: int
    question: str
    verdict: str
    correct: str


@dataclass(frozen=True)
class Assessment:
    """Where an assessment is: how many questions it has, the question being asked (from 1),
    its topic, level and the part of the topic it was written from, the fingerprint of that
    part's material, and the answers so far."""

    total: int
    number: int
    topic: str
    level: int
    part: int
    question: str
    source: str = ""
    answers: tuple[Answer, ...] = ()


@dataclass(frozen=True)
class Assessed:
    """A reply made here, the assessment after it (None once it is over or stopped), and any
    choices to show as buttons."""

    sentences: list[str]
    assessment: Assessment | None
    choices: list[Choice] = field(default_factory=list)


def size(topics: int) -> int:
    """How many questions an assessment has: AT_LEAST, or one per topic when there are more."""
    return min(max(AT_LEAST, topics), MOST_QUESTIONS)


def planned(index: int, topics: int) -> tuple[int, int]:
    """The topic and level of question `index` (from 0): the topics in turn, each round
    starting one topic later so a topic doesn't keep the same level, and the levels in turn."""
    return (index + index // topics) % topics, index % len(LEVELS)


def part_for(level: int, index: int, topics: int, parts: int) -> int:
    """The part a question is written from: the topic's main ideas for recall, the entries
    under it, in turn, for deeper questions (its main ideas when it has none)."""
    if level == RECALL or parts == 1:
        return 0
    return 1 + (index // topics) % (parts - 1)


def asked_line(assessment: Assessment) -> str:
    return f"Question {assessment.number} of {assessment.total}: {assessment.question}"


def evaluation(answers: tuple[Answer, ...], topics: int) -> tuple[list[str], list[str]]:
    """What the answers show: the overall result, breadth, depth and the answers missed; and
    the topics to go over again."""
    right = sum(a.verdict == RIGHT for a in answers)
    partly = sum(a.verdict == PARTLY for a in answers)
    partly_said = f", and {partly} partly right" if partly else ""
    asked = list(dict.fromkeys(a.topic for a in answers))
    well = [t for t in asked if all(a.verdict != WRONG for a in answers if a.topic == t)]
    depth = []
    for level, name in enumerate(LEVELS):
        at = [a for a in answers if a.level == level]
        if at:
            depth.append(f"{name}, {sum(a.verdict == RIGHT for a in at)} of {len(at)} right")
    sentences = [
        f"You got {right} of {len(answers)} right{partly_said}.",
        f"Breadth: you answered {len(well)} of {topics} topics well.",
    ]
    if depth:
        sentences.append(f"Depth: {spoken_list(depth)}.")
    review = []
    for n, a in enumerate(answers, 1):
        if a.verdict != RIGHT:
            if a.correct:
                sentences.append(f"Question {n}, on {a.topic}: {a.correct}")
            if a.topic not in review:
                review.append(a.topic)
    sentences.append(f"Go over {spoken_list(review)} again." if review else NOTHING_TO_GO_OVER)
    return sentences, review


def first_sentence(text: str) -> str:
    """The first sentence of the correct answer the LLM gave: a small one may say much more."""
    return re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]


class Assessor:
    """Decides what each prompt does to the assessment, from the wiki as it is now. `write` asks
    the LLM for a one-off answer from some material (`Conversation.write`)."""

    def __init__(
        self,
        contents: Callable[[], list[dict[str, Any]]],
        find: Callable[[str], list[str]],
        write: Callable[[str, list[str]], str],
        complete: Callable[[], bool] = lambda: True,
    ) -> None:
        self._contents = contents
        self._teacher = Teacher(contents, find, complete)  # for each part's material
        self._write = write
        self._complete = complete

    def step(self, prompt: str, assessment: Assessment | None) -> Assessed | None:
        """What to do with the prompt, given the assessment the browser has (None when there
        is none)."""
        text = plain(prompt)
        if _ASSESS.fullmatch(text):
            return self._start()
        if assessment is None:
            return None
        topics = lesson_topics(self._contents())
        if _STOP.fullmatch(text):
            logger.info("Assessment stopped", extra={"question": assessment.number})
            done = evaluation(assessment.answers, len(topics))[0] if assessment.answers else []
            return Assessed([STOPPED, *done], None)
        parts = topics.get(assessment.topic)
        if parts is None or size(len(topics)) != assessment.total:  # topics added or removed
            logger.info("Assessment topics changed", extra={"question": assessment.number})
            return Assessed([GONE], None)
        material = None
        if assessment.part < len(parts):
            material = self._teacher.material(assessment.topic, parts, assessment.part)
        if material is None or fingerprint(material) != assessment.source:
            logger.info("Assessment material changed", extra={"question": assessment.number})
            asked = self._asked(assessment.number, topics, assessment.answers)
            return Assessed([CHANGED, asked_line(asked)], asked)
        kind = asked_for(text)
        logger.info("Assessment reply sorted", extra={"kind": kind or "answer"})
        if kind == AGAIN:
            return Assessed([asked_line(assessment)], assessment)
        if kind == EXPLAIN:
            return Assessed([NO_EXPLAINING, asked_line(assessment)], assessment)
        return self._judge(prompt, assessment, material, topics, gave_up=kind == REVEAL)

    def _start(self) -> Assessed:
        topics = lesson_topics(self._contents())
        if not topics:
            waiting = not self._complete()
            logger.info("No assessment to give", extra={"still_reading": waiting})
            return Assessed([STILL_READING if waiting else CHOOSE_NOTHING], None)
        assessment = self._asked(1, topics, ())
        logger.info(
            "Assessment started", extra={"topics": len(topics), "questions": assessment.total}
        )
        opening = (
            f"Let's see what you know across all {len(topics)} topics. I'll ask you"
            f" {assessment.total} questions, one at a time, and tell you how you did at the end;"
            " say stop to end the assessment."
        )
        return Assessed([opening, asked_line(assessment)], assessment)

    def _asked(
        self, number: int, topics: dict[str, list[Part]], answers: tuple[Answer, ...]
    ) -> Assessment:
        """Question `number` (from 1) as the plan has it, written from its part's material."""
        names = list(topics)
        index = number - 1
        t, level = planned(index, len(names))
        topic, parts = names[t], topics[names[t]]
        part = part_for(level, index, len(names), len(parts))
        material = self._teacher.material(topic, parts, part)
        asked = tuple(a.question for a in answers)
        question = self._question(topic, parts, part, level, material, asked)
        return Assessment(
            size(len(names)), number, topic, level, part, question, fingerprint(material), answers
        )

    def _question(
        self,
        topic: str,
        parts: list[Part],
        part: int,
        level: int,
        material: list[str],
        asked: tuple[str, ...],
    ) -> str:
        """A question at the level written by the LLM from the material, or a plain one, not
        asked already, when it can't."""
        instruction = (
            f"Write one short quiz question that {_ASK[level]} {what(topic, parts, part)}, and"
            " that can be answered in a sentence or two from the reference text. Say only the"
            " question, ending with a question mark, and don't mention the reference text."
        )
        if asked:
            instruction += " Don't ask any of these again: " + " ".join(asked)
        try:
            written = self._write(instruction, material)
        except LlmError as e:
            logger.error("Could not write an assessment question", extra={"error": str(e)})
            written = ""
        keys = {plain(a) for a in asked}
        question = first_question(written)
        if not question or plain(question) in keys:
            logger.info("Assessment question asked plainly", extra={"topic": topic})
            title = parts[part].title
            question = next(
                q for q in (p.format(title) for p in _PLAIN[level]) if plain(q) not in keys
            )
        logger.info("Assessment question written", extra={"topic": topic, "level": level})
        return question

    def _judge(
        self,
        answer: str,
        assessment: Assessment,
        material: list[str],
        topics: dict[str, list[Part]],
        gave_up: bool,
    ) -> Assessed:
        """The answer judged, kept with the correct answer for the end, and the next question
        or the evaluation. Nothing is said about the answer now, so nothing is taught."""
        instruction = (
            f'The student was asked: "{assessment.question}" The student answered: "{answer}".'
            ' Judge the answer from the reference text. Reply in exactly two lines: "Verdict:"'
            ' followed by Right, Partly right or Not quite; then "Answer:" followed by the'
            " correct answer in one short sentence."
        )
        said = self._write(instruction, material)
        found = re.search(r"verdict\W*(.+)", said, re.IGNORECASE)
        judged = WRONG if gave_up else verdict(found[1] if found else said)
        correct = re.search(r"answer\W*(.+)", said, re.IGNORECASE)
        logger.info(
            "Assessment answer judged",
            extra={
                "question": assessment.number,
                "topic": assessment.topic,
                "level": assessment.level,
                "verdict": "don't know" if gave_up else judged,
            },
        )
        answers = (
            *assessment.answers,
            Answer(
                assessment.topic,
                assessment.level,
                assessment.question,
                judged,
                first_sentence(correct[1]) if correct else "",
            ),
        )
        if assessment.number < assessment.total:
            nxt = self._asked(assessment.number + 1, topics, answers)
            return Assessed(["Thanks.", asked_line(nxt)], nxt)
        sentences, review = evaluation(answers, len(topics))
        logger.info(
            "Assessment finished",
            extra={"right": sum(a.verdict == RIGHT for a in answers), "questions": len(answers)},
        )
        choices = [Choice(f"Teach me about {t}", f"Teach me about {t}") for t in review]
        return Assessed(["That's the end of the assessment.", *sentences], None, choices)
