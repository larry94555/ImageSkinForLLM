"""Guidelines for the assessment (roadmap R198)."""

import logging
from pathlib import Path
from typing import Any

import pytest
from test_assess import Writer, assessed, assessment_on, started
from test_question_scope import Llm
from test_quiz import QuizLlm, chat
from test_teach import CONTENTS
from test_topics import riemann_app

from imageskin.assess import APPLY, LEVELS, RECALL, Assessor, judging_asked, question_asked
from imageskin.chat import Conversation, Message
from imageskin.customization import (
    ASSESSMENT_JUDGING,
    ASSESSMENT_QUESTIONS,
    FEATURES,
    SHIPPED,
    features,
    guidelines_of,
)
from imageskin.quiz import JUDGING_GUIDELINES, QUESTION_GUIDELINES
from imageskin.teach import Part

ASKS = "Recall questions ask for a definition in the participant's own words."
JUDGES = "Count an answer right only if it gives the reason."
PARTS = [Part("Primes", "No divisors.")]


def test_they_ship_in_two_parts_as_each_was_asked_before_word_for_word() -> None:
    assert FEATURES["assessment questions"].shipped == ASSESSMENT_QUESTIONS
    assert guidelines_of(SHIPPED, "assessment judging") == ASSESSMENT_JUDGING
    keys = [f["key"] for f in features(SHIPPED)]
    assert keys[5:7] == ["assessment questions", "assessment judging"]
    assert question_asked("Primes", PARTS, 0, RECALL, ("Why?",)) == (
        "Write one short quiz question that asks the participant to recall one fact from the"
        ' main ideas of "Primes", and that can be answered in a sentence or two from the'
        " reference text. Say only the question, ending with a question mark, and don't mention"
        " the reference text. Don't ask any of these again: Why?"
    )
    assert judging_asked("Why?", "Because.") == (
        'The participant was asked: "Why?" The participant answered: "Because.". Judge the'
        ' answer from the reference text. Reply in exactly two lines: "Verdict:" followed by'
        ' Right, Partly right or Not quite; then "Answer:" followed by the correct answer in one'
        " short sentence."
    )


def test_edited_they_take_the_place_of_what_to_ask_and_how_to_judge() -> None:
    question = question_asked("Primes", PARTS, 0, APPLY, (), ASKS)
    assert question.startswith(
        "Write one short quiz question that asks the participant to apply or connect ideas"
    )
    # The level is named, so the guidelines can say what each level asks.
    assert f"It is a question about {LEVELS[APPLY]}. {QUESTION_GUIDELINES} {ASKS}" in question
    judging = judging_asked("Why?", "Because.", JUDGES)
    assert f'"Because.". {JUDGING_GUIDELINES} {JUDGES} Reply in exactly two lines:' in judging


class EditedWriter(Writer):
    """The LLM as the app's `Conversation.write` is called with edited guidelines."""

    def __init__(self, *verdicts: str) -> None:
        super().__init__(*verdicts)
        self.unguided: list[str | None] = []

    def __call__(
        self, instruction: str, material: list[str], unguided: str | None = None, **more: Any
    ) -> str:
        self.unguided.append(unguided)
        return super().__call__(instruction, material)


def test_each_question_and_judgment_is_asked_with_them_as_they_are_then(
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = {"assessment questions": ASSESSMENT_QUESTIONS, "assessment judging": ASSESSMENT_JUDGING}
    write = EditedWriter("Verdict: Partly right\nAnswer: Yes.")
    a = Assessor(lambda: CONTENTS, lambda q: [], write, guidelines=now.__getitem__)
    with caplog.at_level(logging.INFO, logger="imageskin.assess"):
        first = started(a)
        now.update({"assessment questions": ASKS, "assessment judging": JUDGES})
        step = assessed(a.step("Because.", first))
    (shipped, _), (judged, _), (edited, _) = write.asked
    assert ASKS not in shipped and write.unguided[0] is None
    assert judged.endswith(judging_asked("Q1?", "Because.", JUDGES).split('"Because.". ')[1])
    assert write.unguided[1] == judging_asked("Q1?", "Because.")
    assert f"{QUESTION_GUIDELINES} {ASKS}" in edited and write.unguided[2] is not None
    assert step.assessment is not None and step.assessment.answers[0].verdict == "partly right"
    used = [
        (r.part, r.edited)  # type: ignore[attr-defined]
        for r in caplog.records
        if r.message == "Guidelines used"
    ]
    assert used == [("questions", False), ("judging", True), ("questions", True)]


def test_unreadable_guidelines_assess_as_shipped(caplog: pytest.LogCaptureFixture) -> None:
    def broken(key: str) -> str:
        raise OSError("disk gone")

    write = Writer()
    a = Assessor(lambda: CONTENTS, lambda q: [], write, guidelines=broken)
    with caplog.at_level(logging.ERROR, logger="imageskin.assess"):
        assessed(a.step("Because.", started(a)))
    assert ASKS not in write.asked[0][0]
    assert write.asked[1][0] == judging_asked("Q1?", "Because.")
    assert "Could not read the assessment guidelines" in caplog.text


def test_guidelines_that_dont_fit_a_judgment_are_left_out(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """As for Teach me and Quiz me: a judgment with guidelines near their longest is asked as
    shipped when they don't fit the room left for it."""
    longest = "Count an answer right only if it gives the reason. " * 38  # about 1,950
    shipped = judging_asked("Why?", "Because.")
    guided = judging_asked("Why?", "Because.", longest.strip())

    def fits(window: int) -> bool:
        try:
            Conversation(Llm(), lambda: window)._fit(shipped)
        except ValueError:
            return False
        return True

    window = next(w for w in range(256, 8192, 8) if fits(w))
    llm = Llm()
    with caplog.at_level(logging.WARNING, logger="imageskin.chat"):
        Conversation(llm, lambda: window).write(guided, [], shipped, "assessment judging")
    assert llm.sent[0][-1]["content"] == shipped
    assert "Guidelines left out" in caplog.text


class EditedLlm(QuizLlm):
    """Judges an answer asked for with edited guidelines too, by the lines it replies in."""

    def __call__(self, messages: list[Message]) -> str:
        if "Reply in exactly two lines" in messages[-1]["content"]:
            self.sent.append(messages)
            return self.verdicts.pop(0)
        return super().__call__(messages)


def test_the_host_edits_them_and_the_next_question_and_judgment_use_them(
    tmp_path: Path,
) -> None:
    llm = EditedLlm("Verdict: Partly right\nAnswer: Counted.")
    client: Any = riemann_app(tmp_path, llm)
    assessment_on(client)
    for key, text in (("assessment%20questions", ASKS), ("assessment%20judging", JUDGES)):
        saved = client.put(f"/api/customization/guidelines/{key}", json={"text": text})
        assert saved.status_code == 200
    assert [f["edited"] for f in saved.json()["features"][5:7]] == [True, True]
    reply = chat(client, "Assess me")
    assert f"{QUESTION_GUIDELINES} {ASKS}" in llm.sent[-1][-1]["content"]
    reply = chat(client, "Primes", assessment=reply["assessment"])
    judging = next(
        s[-1]["content"] for s in llm.sent if "Reply in exactly two lines" in s[-1]["content"]
    )
    assert f"{JUDGING_GUIDELINES} {JUDGES}" in judging
    assert reply["assessment"]["answers"][0]["verdict"] == "partly right"
