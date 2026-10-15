"""Quiz me (roadmap R41i, item 54): the person asks the student questions on a topic.

A quiz has QUESTIONS questions on one topic (a main wiki entry, R41f), asked one at a time.
Each is written by the LLM from one of the topic's parts (its main ideas, then the entries under
it, spread over the quiz), from that part's wiki entry and what the PDFs say about it. Whatever
the student types next is their answer: the LLM judges it from the same material as right,
partly right or wrong, with the correct answer and a one-line reason, and the next question
follows in the same reply. The quiz ends with how many were right and what to go over again,
and can be stopped at any time. Where the quiz is, is kept by the browser, as a lesson is
(`Quiz`).

Each prompt is given to `Quizzer.step`, which says what to do with it: nothing (not a quiz
prompt), a reply made here (`Said`), or an answer for the LLM to judge (`Judge`).
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from imageskin.chat import LlmError, Teach
from imageskin.teach import Choice, Part, Teacher, lesson_topics, plain, what
from imageskin.topics import spoken_list

logger = logging.getLogger(__name__)

QUESTIONS = 5

# "Quiz me", "Can you quiz me on the zeta function?", "Test me about rain please".
_QUIZ = re.compile(
    r"(?:(?:please|ok|okay|so|now|can you|could you|will you|would you)\s+)*(?:quiz|test) me"
    r"(?:\s+(?:on|about)\s+(?P<about>.+?))?(?:\s+please)?"
)
_STOP = re.compile(r"stop(?: the quiz| quizzing(?: me)?)?|end the quiz|that'?s enough")
# What a question written by the LLM may start with, left out: "Question:", "Q1.", quotes.
_LEAD = re.compile(r"^(?:\**\s*(?:question|q)\s*\d*\s*[:.)-]\s*\**\s*)", re.IGNORECASE)

CHOOSE = "What would you like to be quizzed on?"
NO_QUIZ = "There's nothing to quiz you on yet: no material has been added."
STILL_READING_QUIZ = (
    "I'm still reading the material I was given, so there's nothing to quiz you on yet. Click"
    " Quiz me again in a little while."
)
STOPPED = "OK, we'll stop the quiz here."
NOTHING_TO_GO_OVER = "Well done: there's nothing to go over again!"

RIGHT, PARTLY, WRONG = "right", "partly right", "wrong"


@dataclass(frozen=True)
class Quiz:
    """Where a quiz is: its topic, the question being asked (from 1) and the part of the topic
    it was written from, the questions asked so far, the answers right and partly right so far,
    and the parts to go over again. `active` is false once it is over or stopped."""

    topic: str
    number: int
    question: str
    part: int
    asked: tuple[str, ...] = ()
    right: int = 0
    partly: int = 0
    review: tuple[str, ...] = ()
    active: bool = True


@dataclass(frozen=True)
class Said:
    """A reply made here, and the quiz after it (None when there is none going)."""

    sentences: list[str]
    quiz: Quiz | None
    choices: list[Choice] = field(default_factory=list)


@dataclass
class Judge:
    """An answer for the LLM to judge. `quiz` is the quiz before the answer until the reply is
    in; then `teach.then` sets it to the quiz after it (None once it is over)."""

    teach: Teach
    quiz: Quiz | None


QuizStep = Said | Judge | None


def part_for(number: int, parts: int) -> int:
    """The part question `number` (from 1) is written from: the parts spread over the quiz,
    main ideas first."""
    return (number - 1) * parts // QUESTIONS


def verdict(reply: str) -> str:
    """How the LLM judged an answer, from how its reply starts ("Right!", "Partly right.",
    "Not quite."); an answer it didn't clearly call right is counted wrong."""
    start = re.sub(r"[^a-z ]", "", reply.lower()).split()[:2]
    if start[:1] in (["partly"], ["partially"]) or start == ["half", "right"]:
        return PARTLY
    if start[:1] in (["right"], ["correct"], ["yes"], ["exactly"], ["spot"]):
        return RIGHT
    return WRONG


def score(quiz: Quiz, answered: int) -> str:
    """How many of the answers so far were right: "You got 3 of 5 right, and 1 partly right."""
    partly = f", and {quiz.partly} partly right" if quiz.partly else ""
    return f"You got {quiz.right} of {answered} right{partly}."


def asked_line(number: int, question: str) -> str:
    return f"Question {number} of {QUESTIONS}: {question}"


class Quizzer:
    """Decides what each prompt does to the quiz, from the wiki as it is now. `write` asks the
    LLM for a one-off answer from some material (`Conversation.write`)."""

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

    def step(self, prompt: str, quiz: Quiz | None) -> QuizStep:
        """What to do with the prompt, given the quiz the browser has (None when there is
        none)."""
        text = plain(prompt)
        asked = _QUIZ.fullmatch(text)
        if asked is None and (quiz is None or not quiz.active):
            return None
        topics = lesson_topics(self._contents())
        if asked is not None:
            return self._start(asked["about"], topics)
        assert quiz is not None
        if _STOP.fullmatch(text):
            logger.info("Quiz stopped", extra={"topic": quiz.topic, "question": quiz.number})
            done = [score(quiz, quiz.number - 1)] if quiz.number > 1 else []
            return Said([STOPPED, *done], None)
        parts = topics.get(quiz.topic)
        if parts is None:  # its topic is gone from the wiki: start again from the choices
            logger.info("Quiz topic gone", extra={"topic": quiz.topic})
            return self._choose(topics, f'"{quiz.topic}" is no longer in the material.')
        return self._judge(prompt, quiz, parts)

    def _start(self, about: str | None, topics: dict[str, list[Part]]) -> Said:
        if not topics:
            waiting = not self._complete()
            logger.info("No quiz to give", extra={"still_reading": waiting})
            return Said([STILL_READING_QUIZ if waiting else NO_QUIZ], None)
        if about is None:
            return self._choose(topics)
        topic = Teacher.topic_named(about, topics)
        if topic is None:
            return self._choose(topics, f"I don't have a topic called {about}.")
        parts = topics[topic]
        part = part_for(1, len(parts))
        question = self._question(topic, parts, part, ())
        logger.info("Quiz started", extra={"topic": topic, "parts": len(parts)})
        opening = (
            f"Let's see what you know about {topic}. I'll ask you {QUESTIONS} questions, one at"
            " a time; say stop to end the quiz."
        )
        quiz = Quiz(topic, 1, question, part, (question,))
        return Said([opening, asked_line(1, question)], quiz)

    def _choose(self, topics: dict[str, list[Part]], first: str | None = None) -> Said:
        choices = [Choice(t, f"Quiz me on {t}") for t in topics]
        logger.info("Quiz topic asked for", extra={"topics": len(topics)})
        return Said(([first] if first else []) + [CHOOSE], None, choices)

    def _question(self, topic: str, parts: list[Part], part: int, asked: tuple[str, ...]) -> str:
        """A question written by the LLM from the part's material, or a plain one when it
        can't."""
        instruction = (
            f"Write one short quiz question about {what(topic, parts, part)} that can be"
            " answered in a sentence from the reference text. Say only the question."
        )
        if asked:
            instruction += " Don't ask any of these again: " + " ".join(asked)
        try:
            written = self._write(instruction, self._teacher.material(topic, parts, part))
        except LlmError as e:
            logger.error("Could not write a quiz question", extra={"error": str(e)})
            written = ""
        lines = [ln.strip() for ln in written.splitlines() if ln.strip()]
        question = _LEAD.sub("", lines[0]).strip(" \"'*") if lines else ""
        if question.casefold() in {a.casefold() for a in asked}:  # a small LLM may ask again
            logger.info("Quiz question repeated", extra={"topic": topic, "part": part})
            question = ""
        if not question:
            question = f"What can you tell me about {parts[part].title}?"
        logger.info("Quiz question written", extra={"topic": topic, "part": part})
        return question

    def _judge(self, answer: str, quiz: Quiz, parts: list[Part]) -> Judge:
        part = min(quiz.part, len(parts) - 1)
        instruction = (
            f'The student was asked: "{quiz.question}" The student answered: "{answer}". Judge'
            ' the answer from the reference text, talking to the student as "you". Start with'
            ' exactly one of "Right!", "Partly right." or "Not quite." Then give the correct'
            " answer and a one-line reason, kindly, in at most two more sentences. Don't mention"
            " the reference text, and don't ask anything."
        )
        judged = Judge(Teach(instruction, self._teacher.material(quiz.topic, parts, part)), quiz)

        def then(reply: str) -> list[str]:
            found = verdict(reply)
            logger.info(
                "Quiz answer judged",
                extra={"topic": quiz.topic, "question": quiz.number, "verdict": found},
            )
            review = quiz.review
            title = parts[part].title
            if found != RIGHT and title not in review:
                review = (*review, title)
            after = replace(
                quiz,
                right=quiz.right + (found == RIGHT),
                partly=quiz.partly + (found == PARTLY),
                review=review,
            )
            if quiz.number >= QUESTIONS:
                judged.quiz = None
                logger.info(
                    "Quiz finished",
                    extra={"topic": quiz.topic, "right": after.right, "partly": after.partly},
                )
                again = f"Go over {spoken_list(list(review))} again." if review else None
                return [
                    f"That's the end of the quiz on {quiz.topic}.",
                    score(after, QUESTIONS),
                    again or NOTHING_TO_GO_OVER,
                ]
            number = quiz.number + 1
            nxt = part_for(number, len(parts))
            question = self._question(quiz.topic, parts, nxt, quiz.asked)
            judged.quiz = replace(
                after, number=number, question=question, part=nxt, asked=(*quiz.asked, question)
            )
            return [asked_line(number, question)]

        judged.teach = replace(judged.teach, then=then)
        return judged
