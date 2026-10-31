"""Guidelines for Quiz me (roadmap R197)."""

import logging
from pathlib import Path
from typing import Any

import pytest
from test_question_scope import Llm
from test_quiz import QuizLlm, Writer, chat, judged, kept, said, started
from test_teach import CONTENTS
from test_topics import riemann_app

from imageskin.chat import Conversation
from imageskin.customization import (
    FEATURES,
    QUIZ_JUDGING,
    QUIZ_QUESTIONS,
    SHIPPED,
    features,
    guidelines_of,
)
from imageskin.quiz import (
    JUDGING_GUIDELINES,
    QUESTION_GUIDELINES,
    Quizzer,
    judging_asked,
    question_asked,
)
from imageskin.teach import Part

ASKS = "Ask how the idea applies to a practical situation."
JUDGES = "Count an answer right only if it gives the reason."
PARTS = [Part("Primes", "No divisors.")]


def test_they_ship_in_two_parts_as_each_was_asked_before_word_for_word() -> None:
    assert FEATURES["quiz questions"].shipped == QUIZ_QUESTIONS
    assert FEATURES["quiz judging"].shipped == QUIZ_JUDGING
    assert guidelines_of(SHIPPED, "quiz judging") == QUIZ_JUDGING
    assert [f["key"] for f in features(SHIPPED)][3:5] == ["quiz questions", "quiz judging"]
    assert question_asked("Primes", PARTS, 0, ("Why?",)) == (
        'Write one short quiz question about the main ideas of "Primes" that can be answered in'
        " a sentence from the reference text. Say only the question, ending with a question"
        " mark, and don't mention the reference text. Don't ask any of these again: Why?"
    )
    assert judging_asked("Why?", "Because.") == (
        'The participant was asked: "Why?" The participant answered: "Because.". Judge the'
        ' answer from the reference text, talking to the participant as "you". Start with'
        ' exactly one of "Right!", "Partly right." or "Not quite." Then give the correct answer'
        " and a one-line reason, kindly, in at most two more sentences. Don't mention the"
        " reference text, and don't ask anything."
    )


def test_edited_they_take_the_place_of_what_to_ask_and_how_to_go_on() -> None:
    question = question_asked("Primes", PARTS, 0, ("Why?",), ASKS)
    assert question.startswith('Write one short quiz question about the main ideas of "Primes".')
    assert f"ending with a question mark. {QUESTION_GUIDELINES} {ASKS}" in question
    assert question.endswith("Don't ask any of these again: Why?")
    judging = judging_asked("Why?", "Because.", JUDGES)
    # The verdict it starts with stays, as the score is counted from it.
    assert judging.endswith(f'or "Not quite." {JUDGING_GUIDELINES} {JUDGES}')


class EditedWriter(Writer):
    """Writes questions as the app's `Conversation.write` is called with edited guidelines."""

    def __init__(self) -> None:
        super().__init__()
        self.unguided: list[str | None] = []

    def __call__(
        self, instruction: str, material: list[str], unguided: str | None = None, **more: Any
    ) -> str:
        self.unguided.append(unguided)
        return super().__call__(instruction, material)


def test_each_question_and_judgment_is_asked_with_them_as_they_are_then(
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = {"quiz questions": QUIZ_QUESTIONS, "quiz judging": QUIZ_JUDGING}
    write = EditedWriter()
    quizzer = Quizzer(lambda: CONTENTS, lambda q: [], write, guidelines=now.__getitem__)
    with caplog.at_level(logging.INFO, logger="imageskin.quiz"):
        first = said(quizzer.step("Quiz me on Rain", None))
        now.update({"quiz questions": ASKS, "quiz judging": JUDGES})
        step = judged(quizzer.step("It falls.", first.quiz))
        step.teach.then("Right! It does.")  # type: ignore[misc]
    (shipped, _), (edited, _) = write.asked
    assert ASKS not in shipped and edited.endswith(f"{ASKS} Don't ask any of these again: Q1?")
    assert write.unguided[0] is None
    assert write.unguided[1] == question_asked("Rain", [Part("Rain", "It falls.")], 0, ("Q1?",))
    assert step.teach.instruction.endswith(f"{JUDGING_GUIDELINES} {JUDGES}")
    assert step.teach.unguided == judging_asked("Q1?", "It falls.")
    assert step.teach.feature == "quiz judging"
    used = [
        (r.part, r.edited)  # type: ignore[attr-defined]
        for r in caplog.records
        if r.message == "Guidelines used"
    ]
    assert used == [("questions", False), ("judging", True), ("questions", True)]


def test_a_participant_who_doesnt_know_is_told_as_before(tmp_path: Path) -> None:
    now = {"quiz questions": ASKS, "quiz judging": JUDGES}
    quizzer = Quizzer(lambda: CONTENTS, lambda q: [], Writer(), guidelines=now.__getitem__)
    step = judged(quizzer.step("I don't know", kept("Rain", 1, "Q1?", 0)))
    assert JUDGES not in step.teach.instruction and step.teach.unguided is None


def test_unreadable_guidelines_quiz_as_shipped(caplog: pytest.LogCaptureFixture) -> None:
    def broken(key: str) -> str:
        raise OSError("disk gone")

    write = Writer()
    quizzer = Quizzer(lambda: CONTENTS, lambda q: [], write, guidelines=broken)
    with caplog.at_level(logging.ERROR, logger="imageskin.quiz"):
        first = said(quizzer.step("Quiz me on Rain", None))
        step = judged(quizzer.step("It falls.", first.quiz))
    assert write.asked[0][0] == question_asked("Rain", [Part("Rain", "It falls.")], 0, ())
    assert step.teach.instruction == judging_asked("Q1?", "It falls.")
    assert "Could not read the Quiz me guidelines" in caplog.text


def test_guidelines_that_dont_fit_a_question_are_left_out(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """As for Teach me (Codex's review on PR #250): a question written with guidelines near
    their longest is asked as shipped when they don't fit the room left for it."""
    longest = "Ask how the idea applies to a practical situation. " * 38  # about 1,950
    shipped = question_asked("Rain", [Part("Rain", "It falls.")], 0, ())
    guided = question_asked("Rain", [Part("Rain", "It falls.")], 0, (), longest.strip())

    def fits(window: int) -> bool:
        try:
            Conversation(Llm(), lambda: window)._fit(shipped)
        except ValueError:
            return False
        return True

    window = next(w for w in range(256, 8192, 8) if fits(w))
    llm = Llm()
    with caplog.at_level(logging.WARNING, logger="imageskin.chat"):
        Conversation(llm, lambda: window).write(guided, [], shipped, "quiz questions")
    assert llm.sent[0][-1]["content"] == shipped
    assert "Guidelines left out" in caplog.text
    roomy = Llm()
    Conversation(roomy, lambda: 4 * window).write(guided, [], shipped, "quiz questions")
    assert roomy.sent[0][-1]["content"] == guided


def test_the_host_edits_them_and_the_next_question_and_judgment_use_them(
    tmp_path: Path,
) -> None:
    llm = QuizLlm("Partly right. It needs the reason.")
    client: Any = riemann_app(tmp_path, llm)
    assert client.patch("/api/settings", json={"quiz_me": True}).status_code == 200
    for key, text in (("quiz%20questions", ASKS), ("quiz%20judging", JUDGES)):
        saved = client.put(f"/api/customization/guidelines/{key}", json={"text": text})
        assert saved.status_code == 200
    assert [f["edited"] for f in saved.json()["features"][3:5]] == [True, True]
    quiz = started(client, llm, "Zeta Function Integral")
    reply = chat(client, "An integral.", quiz=quiz)
    judging, question = (sent[-1]["content"] for sent in llm.sent[-2:])
    assert judging.endswith(f"{JUDGING_GUIDELINES} {JUDGES}")
    assert f"{QUESTION_GUIDELINES} {ASKS}" in question
    assert reply["content"].startswith("Partly right.") and reply["quiz"]["partly"] == 1
