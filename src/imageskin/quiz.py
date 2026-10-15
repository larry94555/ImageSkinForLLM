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

import hashlib
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
# A reply to a quiz question that isn't an answer to it (Larry, 2026-10-15: "What's the
# question?" was judged as a wrong answer). Said plainly and briefly, these are clear enough to
# go by their words; anything else that may be one is sorted by the LLM (`Quizzer._kind`). The
# phrases are found anywhere in a short reply; a bare word ("pass", "repeat", "hint") only counts
# as the whole reply, as an answer may have it ("Water can pass through soil", review on PR #88).
_REVEAL = re.compile(
    r"\b(?:(?:don'?t|do not|dont) know|no idea|(?:not a|no) clue|i give up|i'?ll pass"
    r"|pass on (?:this|that|it)|skip (?:this|that|the) (?:one|question)|skip the question"
    r"|(?:give|tell|show) me the answer|what'?s the answer|what is the answer"
    r"|just (?:give|tell) me(?: it)?)\b"
)
_EXPLAIN = re.compile(
    r"\b(?:(?:explain|clarify) (?:the question|that question|this question|your question|it"
    r"|that|this|what you mean)|what does (?:the|that|this|it) (?:question )?mean"
    r"|what do you mean|(?:don'?t|do not) (?:understand|get) (?:the|that|this|your) question"
    r"|what is (?:the|that) question asking|i'?m confused|in other words"
    r"|(?:put|say|ask) (?:it|that|the question) (?:differently|another way)"
    r"|(?:give me|can i (?:have|get)|i need|any) (?:a |some )?(?:hint|clue)s?)\b"
)
_AGAIN = re.compile(
    r"\b(?:what(?:'s| is| was) (?:the|that) question"
    r"|(?:repeat|restate|rephrase|reread|reask) (?:(?:the|that|this|your) )?(?:question|it|that)"
    r"|(?:say|ask|read) (?:the question|that|it|this)(?: once more| again)|again please"
    r"|pardon|(?:didn'?t|did not) (?:get|catch|hear) (?:the question|that|it))\b"
)
# Bare words that are a request only when they are the whole reply, give or take a "please".
_ALONE = {
    "reveal": re.compile(r"pass|i pass|skip(?: it| this(?: one)?)?|dunno|next question"),
    "explain": re.compile(r"explain|clarify|(?:a )?hint|(?:a )?clue"),
    "again": re.compile(r"repeat|restate|rephrase|again|what|huh|come again|say again"),
}
_POLITE = re.compile(
    r"^(?:(?:um+|uh+|hmm+|er+|ok|okay|sorry|so|well|please|can you|could you|would you"
    r"|will you)\s+)*|(?:\s+(?:please|again|then|sorry|thanks|thank you))*$"
)
# Words that may mean a reply is about the quiz rather than an answer; such a reply is sorted by
# the LLM when the patterns above don't settle it.
_ABOUT_THE_QUIZ = re.compile(
    r"\b(?:question|answer|know|sure|explain|mean|repeat|again|skip|understand|help"
    r"|idea|confus\w*|tell me|give me)\b"
)
# A reply this long is an answer, whatever words it has.
LONGEST_REQUEST = 25
ANSWER, AGAIN, EXPLAIN, REVEAL = "answer", "again", "explain", "reveal"

# A question: the words up to a question mark, after any sentence before it.
_QUESTION = re.compile(r"[^.!?]*\?")
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
CHANGED = "The material for this question has changed since it was asked, so here's a new one."

# The questions asked when the LLM can't write one, in turn: one per question a quiz has. Each
# only asks what the part says, so any part's material answers it, however little it has (review
# on PR #88: "Why does it matter?" asked for what the material may not say).
_PLAIN = (
    "What can you tell me about {}?",
    "What is the main idea of {}?",
    "How would you describe {} in your own words?",
    "What is one thing you have learned about {}?",
    "In a sentence, what do you know about {}?",
)


@dataclass(frozen=True)
class Quiz:
    """Where a quiz is: its topic, the question being asked (from 1) and the part of the topic
    it was written from, the questions asked so far, the answers right and partly right so far,
    and the parts to go over again. A quiz over or stopped is None. `source` is the
    fingerprint of the material the question was written from."""

    topic: str
    number: int
    question: str
    part: int
    asked: tuple[str, ...] = ()
    right: int = 0
    partly: int = 0
    review: tuple[str, ...] = ()
    source: str = ""


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


def _alone(text: str) -> str | None:
    """The request a reply is when it is only a bare word for one ("Repeat, please")."""
    bare = _POLITE.sub("", text).strip(" ,")
    return next((kind for kind, word in _ALONE.items() if word.fullmatch(bare)), None)


def fingerprint(material: list[str]) -> str:
    """A short key for the material a question was written from, kept with the quiz, so the
    answer is judged from the same material (review on PR #88)."""
    return hashlib.sha256("\n".join(material).encode()).hexdigest()[:16]


def plain_question(title: str, asked: tuple[str, ...]) -> str:
    """A plain question on the part, one not asked yet: there are as many as a quiz has
    questions, so one is always left (review on PR #88)."""
    keys = {plain(a) for a in asked}
    return next(q for q in (p.format(title) for p in _PLAIN) if plain(q) not in keys)


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
        if asked is None and quiz is None:
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
        material = self._material(quiz.topic, parts, quiz.part)
        if material is None or fingerprint(material) != quiz.source:
            return self._rewritten(quiz, parts)
        kind = self._kind(prompt, text, quiz)
        if kind == AGAIN:
            logger.info("Quiz question asked again", extra={"question": quiz.number})
            return Said([asked_line(quiz.number, quiz.question)], quiz)
        if kind == EXPLAIN:
            return self._explain(prompt, quiz, parts)
        return self._judge(prompt, quiz, parts, material, gave_up=kind == REVEAL)

    def _material(self, topic: str, parts: list[Part], part: int) -> list[str] | None:
        """What the part is taught from now; None when the topic no longer has the part."""
        return self._teacher.material(topic, parts, part) if part < len(parts) else None

    def _rewritten(self, quiz: Quiz, parts: list[Part]) -> Said:
        """A new question in place of one whose material has changed since it was asked (the
        wiki rebuilt, or a PDF replaced): it can't be judged from what it was written from."""
        logger.info("Quiz material changed", extra={"topic": quiz.topic, "question": quiz.number})
        part = part_for(quiz.number, len(parts))
        before = quiz.asked[: quiz.number - 1]
        question, source = self._question(quiz.topic, parts, part, before)
        changed = replace(
            quiz, question=question, part=part, asked=(*before, question), source=source
        )
        return Said([CHANGED, asked_line(quiz.number, question)], changed)

    def _kind(self, prompt: str, text: str, quiz: Quiz) -> str:
        """What a reply to the question is: an answer, or asking for the question again, for
        what it means, or for the answer (Larry, 2026-10-15). A short reply is sorted by its
        words, or by the LLM when its words may be about the quiz but don't settle it."""
        how = "words"
        if len(text.split()) > LONGEST_REQUEST:
            kind = ANSWER
        elif (alone := _alone(text)) is not None:
            kind = alone
        elif _EXPLAIN.search(text):
            kind = EXPLAIN
        elif _REVEAL.search(text):
            kind = REVEAL
        elif _AGAIN.search(text):
            kind = AGAIN
        elif _ABOUT_THE_QUIZ.search(text):
            kind, how = self._sorted(prompt, quiz), "llm"
        else:
            kind = ANSWER
        logger.info(
            "Quiz reply sorted",
            extra={"topic": quiz.topic, "question": quiz.number, "kind": kind, "by": how},
        )
        return kind

    def _sorted(self, reply: str, quiz: Quiz) -> str:
        """What the LLM takes the reply to be; an answer when it can't say."""
        instruction = (
            f'In a quiz, a student was asked: "{quiz.question}" The student replied: "{reply}".'
            ' Which is the reply? A: an answer, even a guess ("Clouds form", "Is it the sun?").'
            ' B: wants to hear the question again ("Say it again"). C: wants the question'
            ' explained or put another way ("What do you mean?"). D: doesn\'t know, or wants to'
            ' be told the answer ("No idea, tell me"). Say only the letter.'
        )
        try:
            said = self._write(instruction, [])
        except LlmError as e:
            logger.error("Could not sort a quiz reply", extra={"error": str(e)})
            return ANSWER
        letter = re.search(r"\b([ABCD])\b", said.upper())
        return {"B": AGAIN, "C": EXPLAIN, "D": REVEAL}.get(letter[1] if letter else "", ANSWER)

    def _explain(self, asked: str, quiz: Quiz, parts: list[Part]) -> Judge:
        """What the question is asking, in other words, then the question again; the quiz stays
        where it is. The LLM isn't given the material, so it can't give the answer away (with
        it, the small local model did)."""
        instruction = (
            f'The student was asked: "{quiz.question}" and said: "{asked}". In one or two short'
            ' sentences, talking to the student as "you", explain what the question is asking'
            " for, in simpler words, without answering it. Don't say the question again, and"
            " don't ask anything."
        )
        logger.info("Quiz question explained", extra={"question": quiz.number})
        teach = Teach(instruction, [], lambda reply: [asked_line(quiz.number, quiz.question)])
        return Judge(teach, quiz)

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
        question, source = self._question(topic, parts, part, ())
        logger.info("Quiz started", extra={"topic": topic, "parts": len(parts)})
        opening = (
            f"Let's see what you know about {topic}. I'll ask you {QUESTIONS} questions, one at"
            " a time; say stop to end the quiz."
        )
        quiz = Quiz(topic, 1, question, part, (question,), source=source)
        return Said([opening, asked_line(1, question)], quiz)

    def _choose(self, topics: dict[str, list[Part]], first: str | None = None) -> Said:
        choices = [Choice(t, f"Quiz me on {t}") for t in topics]
        logger.info("Quiz topic asked for", extra={"topics": len(topics)})
        return Said(([first] if first else []) + [CHOOSE], None, choices)

    def _question(
        self, topic: str, parts: list[Part], part: int, asked: tuple[str, ...]
    ) -> tuple[str, str]:
        """A question written by the LLM from the part's material, or a plain one when it
        can't; and the material's fingerprint."""
        instruction = (
            f"Write one short quiz question about {what(topic, parts, part)} that can be"
            " answered in a sentence from the reference text. Say only the question, ending with a"
            " question mark, and don't mention the reference text."
        )
        if asked:
            instruction += " Don't ask any of these again: " + " ".join(asked)
        material = self._teacher.material(topic, parts, part)
        try:
            written = self._write(instruction, material)
        except LlmError as e:
            logger.error("Could not write a quiz question", extra={"error": str(e)})
            written = ""
        question = ""
        for line in written.splitlines():  # the first one the LLM wrote, without "Question 1:"
            found = _QUESTION.search(_LEAD.sub("", line.strip()).replace("**", ""))
            if found:
                question = found.group().strip(" \"'*")
                break
        if not question and written.strip():  # a statement isn't a question (Larry, 2026-10-15)
            logger.info("Quiz question was not a question", extra={"topic": topic, "part": part})
        if plain(question) in {plain(a) for a in asked}:  # a small LLM may ask again
            logger.info("Quiz question repeated", extra={"topic": topic, "part": part})
            question = ""
        if not question:
            question = plain_question(parts[part].title, asked)
        logger.info("Quiz question written", extra={"topic": topic, "part": part})
        return question, fingerprint(material)

    def _judge(
        self, answer: str, quiz: Quiz, parts: list[Part], material: list[str], gave_up: bool
    ) -> Judge:
        """The answer judged from the material the question was written from, or, when the
        student doesn't know, the answer given; then the next question, or the end."""
        part = quiz.part
        instruction = (
            f'The student was asked: "{quiz.question}" The student answered: "{answer}". Judge'
            ' the answer from the reference text, talking to the student as "you". Start with'
            ' exactly one of "Right!", "Partly right." or "Not quite." Then give the correct'
            " answer and a one-line reason, kindly, in at most two more sentences. Don't mention"
            " the reference text, and don't ask anything."
        )
        if gave_up:
            instruction = (
                f'The student was asked: "{quiz.question}" and doesn\'t know the answer. Talking'
                ' to the student as "you", kindly give the correct answer and a one-line reason,'
                " in at most two sentences. Don't mention the reference text, and don't ask"
                " anything."
            )
        judged = Judge(Teach(instruction, material), quiz)

        def then(reply: str) -> list[str]:
            found = WRONG if gave_up else verdict(reply)
            logger.info(
                "Quiz answer judged",
                extra={
                    "topic": quiz.topic,
                    "question": quiz.number,
                    "verdict": "answer given" if gave_up else found,
                },
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
            question, source = self._question(quiz.topic, parts, nxt, quiz.asked)
            judged.quiz = replace(
                after,
                number=number,
                question=question,
                part=nxt,
                asked=(*quiz.asked, question),
                source=source,
            )
            return [asked_line(number, question)]

        judged.teach = replace(judged.teach, then=then)
        return judged
