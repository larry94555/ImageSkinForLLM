"""The assessment (roadmap R41j, item 55)."""

import logging
from collections import Counter
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from test_quiz import QuizLlm, chat
from test_teach import CONTENTS, entry
from test_topics import riemann_app

from imageskin.assess import (
    APPLY,
    AT_LEAST,
    CHANGED,
    CHOOSE_NOTHING,
    EXPLAIN_IT,
    GONE,
    NO_EXPLAINING,
    NOTHING_TO_GO_OVER,
    RECALL,
    STILL_READING,
    STOPPED,
    Answer,
    Assessed,
    Assessment,
    Assessor,
    evaluation,
    part_for,
    planned,
    size,
)
from imageskin.chat import LlmError
from imageskin.quiz import PARTLY, RIGHT, WRONG
from imageskin.review import Review
from imageskin.teach import Choice


class Writer:
    """The LLM: writes "Q<n>?" for each question, and judges each answer with the next
    verdict given (Right by default)."""

    def __init__(self, *verdicts: str, questions: list[str] | None = None) -> None:
        self.verdicts = list(verdicts)
        self.questions = list(questions or [])
        self.asked: list[tuple[str, list[str]]] = []
        self.written = 0

    def __call__(self, instruction: str, material: list[str]) -> str:
        self.asked.append((instruction, material))
        if instruction.startswith("Write one short quiz question"):
            self.written += 1
            return self.questions.pop(0) if self.questions else f"Q{self.written}?"
        return self.verdicts.pop(0) if self.verdicts else "Verdict: Right\nAnswer: Yes."


def assessor(contents: Any = None, write: Any = None, complete: bool = True) -> Assessor:
    return Assessor(
        lambda: CONTENTS if contents is None else contents,
        lambda question: [],
        write or Writer(),
        lambda: complete,
    )


def assessed(step: Any) -> Assessed:
    assert isinstance(step, Assessed)
    return step


def started(a: Assessor) -> Assessment:
    first = assessed(a.step("Assess me", None)).assessment
    assert first is not None
    return first


@pytest.mark.parametrize("topics", [1, 2, 3, 5, 7, 14, 15, 16, 20])
def test_every_topic_is_asked_once_before_any_twice_and_the_levels_are_even(topics: int) -> None:
    total = size(topics)
    assert total == max(AT_LEAST, topics)
    plan = [planned(i, topics) for i in range(total)]
    for start in range(0, total, topics):  # each round asks every topic once
        rounds = [t for t, _ in plan[start : start + topics]]
        assert len(set(rounds)) == len(rounds)
    counts = Counter(t for t, _ in plan)
    assert max(counts.values()) - min(counts.values()) <= 1 and len(counts) == topics
    levels = Counter(level for _, level in plan)
    assert min(levels.values()) >= total // 3 and len(levels) == 3


def test_deeper_questions_come_from_the_entries_under_a_topic() -> None:
    assert part_for(RECALL, 5, 3, 4) == 0
    assert [part_for(EXPLAIN_IT, i, 3, 4) for i in (1, 4, 7, 10)] == [1, 2, 3, 1]
    assert part_for(APPLY, 2, 3, 1) == 0  # nothing under it: its main ideas


@pytest.mark.parametrize(
    "prompt", ["Assess me", "Can you assess me?", "test me on everything", "Assessment please"]
)
def test_assess_me_starts_the_assessment(prompt: str, caplog: pytest.LogCaptureFixture) -> None:
    write = Writer()
    with caplog.at_level(logging.INFO, logger="imageskin.assess"):
        step = assessed(assessor(write=write).step(prompt, None))
    assert step.sentences == [
        "Let's see what you know across all 3 topics. I'll ask you 15 questions, one at a time,"
        " and tell you how you did at the end; say stop to end the assessment.",
        "Question 1 of 15: Q1?",
    ]
    assert step.assessment is not None
    assert (step.assessment.topic, step.assessment.level, step.assessment.part) == (
        "Prime Numbers",
        RECALL,
        0,
    )
    instruction, material = write.asked[0]
    assert 'recall one fact from the main ideas of "Prime Numbers"' in instruction
    assert material[0].startswith("Prime Numbers: Primes have no divisors")
    assert "Assessment started" in caplog.text


def test_with_nothing_to_assess_it_says_so() -> None:
    assert assessed(assessor(contents=[]).step("Assess me", None)).sentences == [CHOOSE_NOTHING]
    still = assessed(assessor(contents=[], complete=False).step("Assess me", None))
    assert (still.sentences, still.assessment) == ([STILL_READING], None)


def test_a_prompt_with_no_assessment_going_is_left_alone() -> None:
    assert assessor().step("Quiz me", None) is None


def test_a_whole_assessment_then_its_evaluation(caplog: pytest.LogCaptureFixture) -> None:
    verdicts = ["Verdict: Right\nAnswer: A."] * 15
    verdicts[1] = "Verdict: Partly right\nAnswer: Zeta sums powers."
    verdicts[2] = "Verdict: Not quite\nAnswer: It falls from clouds."
    write = Writer(*verdicts)
    a = assessor(write=write)
    step = assessed(a.step("Assess me", None))
    asked = []
    with caplog.at_level(logging.INFO, logger="imageskin.assess"):
        for n in range(1, 16):
            assessment = step.assessment
            assert assessment is not None and assessment.number == n
            asked.append((assessment.topic, assessment.level, assessment.part))
            step = assessed(a.step(f"Answer {n}", assessment))
            if n < 15:
                assert step.sentences == ["Thanks.", f"Question {n + 1} of 15: Q{n + 1}?"]
    assert step.assessment is None
    assert step.sentences == [
        "That's the end of the assessment.",
        "You got 13 of 15 right, and 1 partly right.",
        "Breadth: you answered 2 of 3 topics well.",
        "Depth: recalling facts, 5 of 5 right, explaining ideas, 4 of 5 right and applying and"
        " connecting ideas, 4 of 5 right.",
        "Question 2, on Zeta Function: Zeta sums powers.",
        "Question 3, on Rain: It falls from clouds.",
        "Go over Zeta Function and Rain again.",
    ]
    assert step.choices == [
        Choice("Teach me about Zeta Function", "Teach me about Zeta Function"),
        Choice("Teach me about Rain", "Teach me about Rain"),
    ]
    assert Counter(t for t, _, _ in asked) == {"Prime Numbers": 5, "Zeta Function": 5, "Rain": 5}
    deeper = [part for t, level, part in asked if t == "Prime Numbers" and level != RECALL]
    assert deeper and all(part > 0 for part in deeper)  # from the entries under it
    judged = [r for r in caplog.records if r.message == "Assessment answer judged"]
    assert [r.verdict for r in judged[:3]] == [RIGHT, PARTLY, WRONG]  # type: ignore[attr-defined]
    assert "Assessment finished" in caplog.text
    instruction, material = write.asked[1]  # the first answer judged from its question's part
    assert 'The student answered: "Answer 1"' in instruction and "Verdict:" in instruction
    assert material[0].startswith("Prime Numbers: ")
    # Each question asked so far is given, so it isn't asked again.
    assert "Don't ask any of these again: Q1? Q2?" in write.asked[-2][0]


@pytest.mark.parametrize(
    ("said", "found", "correct"),
    [
        ("Verdict: Partly right.\nAnswer: Primes have two divisors.", PARTLY, "Primes have two"),
        ("**Verdict:** Not quite\n**Answer:** Two. It is the only even prime.", WRONG, "Two."),
        ("Right! Well done.", RIGHT, ""),  # not as asked: the verdict, and no answer to keep
    ],
)
def test_the_verdict_and_correct_answer_are_kept_not_said(
    said: str, found: str, correct: str
) -> None:
    a = assessor(write=Writer(said))
    step = assessed(a.step("Seven", started(a)))
    assert step.sentences == ["Thanks.", "Question 2 of 15: Q2?"]  # nothing taught yet
    assert step.assessment is not None
    answer = step.assessment.answers[0]
    assert (answer.verdict, answer.question, answer.level) == (found, "Q1?", RECALL)
    assert answer.correct.startswith(correct) and "even" not in answer.correct


def test_not_knowing_counts_as_wrong_with_the_answer_kept() -> None:
    a = assessor(write=Writer("Verdict: Right\nAnswer: Two divisors."))
    step = assessed(a.step("I don't know", started(a)))
    assert step.assessment is not None
    assert step.assessment.answers[0].verdict == WRONG
    assert step.assessment.answers[0].correct == "Two divisors."


def test_asking_again_or_for_an_explanation_doesn_t_count_as_an_answer() -> None:
    a = assessor()
    first = started(a)
    again = assessed(a.step("What's the question?", first))
    assert again.sentences == ["Question 1 of 15: Q1?"] and again.assessment == first
    explain = assessed(a.step("Can you explain the question?", first))
    assert explain.sentences == [NO_EXPLAINING, "Question 1 of 15: Q1?"]
    assert explain.assessment == first


def test_stop_ends_it_with_the_evaluation_so_far(caplog: pytest.LogCaptureFixture) -> None:
    a = assessor()
    first = started(a)
    with caplog.at_level(logging.INFO, logger="imageskin.assess"):
        assert assessed(a.step("stop", first)).sentences == [STOPPED]
    assert "Assessment stopped" in caplog.text
    second = assessed(a.step("Seven", first)).assessment
    stopped = assessed(a.step("Stop the assessment", second))
    assert stopped.assessment is None
    assert stopped.sentences[:3] == [
        STOPPED,
        "You got 1 of 1 right.",
        "Breadth: you answered 1 of 3 topics well.",
    ]


def test_a_change_in_the_topics_ends_it() -> None:
    a = assessor(contents=[{"entries": [entry("Rain", "It falls.")]}])
    first = started(a)
    assert first.total == AT_LEAST
    many = [{"entries": [entry(f"T{n}", "Some.") for n in range(20)]}]
    step = assessed(assessor(contents=many).step("Seven", first))
    assert (step.sentences, step.assessment) == ([GONE], None)


def test_a_question_whose_material_changed_is_asked_anew(caplog: pytest.LogCaptureFixture) -> None:
    contents = [{"entries": [entry("Rain", "It falls.")]}]
    a = assessor(contents=contents, write=Writer(questions=["Does it fall?", "Is it wet?"]))
    first = started(a)
    contents[:] = [{"entries": [entry("Rain", "It is water.")]}]
    with caplog.at_level(logging.INFO, logger="imageskin.assess"):
        step = assessed(a.step("Down", first))
    assert step.sentences == [CHANGED, "Question 1 of 15: Is it wet?"]
    assert step.assessment is not None and step.assessment.source != first.source
    assert "Assessment material changed" in caplog.text
    gone = Assessment(first.total, 1, "Rain", RECALL, 4, "Q?", first.source)
    assert assessed(a.step("Down", gone)).sentences[0] == CHANGED  # its part is gone


def test_a_question_the_llm_can_t_write_is_asked_plainly_never_twice() -> None:
    def fails(instruction: str, material: list[str]) -> str:
        if instruction.startswith("Write"):
            raise LlmError("The LLM is not running.")
        return "Verdict: Right\nAnswer: Yes."

    a = assessor(contents=[{"entries": [entry("Rain", "It falls.")]}], write=fails)
    step = assessed(a.step("Assess me", None))
    questions = []
    while step.assessment is not None:
        questions.append(step.assessment.question)
        step = assessed(a.step("Wet", step.assessment))
    assert len(questions) == AT_LEAST == len(set(questions))
    assert questions[:3] == [
        "What is one fact about Rain?",
        "How would you explain Rain in your own words?",
        "How do the ideas in Rain fit together?",
    ]
    statement = assessor(write=Writer(questions=["Primes are counted."]))
    assert started(statement).question == "What is one fact about Prime Numbers?"


def test_a_judgement_the_llm_can_t_give_is_an_error() -> None:
    def fails(instruction: str, material: list[str]) -> str:
        if instruction.startswith("Write"):
            return "Q?"
        raise LlmError("The LLM is not running.")

    a = assessor(write=fails)
    with pytest.raises(LlmError):
        a.step("Seven", started(a))


def test_all_right_means_nothing_to_go_over() -> None:
    answers = (Answer("Rain", RECALL, "Q?", RIGHT, "Yes."),)
    sentences, review = evaluation(answers, 1)
    assert sentences[-1] == NOTHING_TO_GO_OVER and review == []
    assert "Question 1" not in " ".join(sentences)


# --- Through the chat ---


def assessment_on(client: Any, **more: bool) -> None:
    assert client.patch("/api/settings", json={"assessment": True, **more}).status_code == 200


def test_with_assessment_off_assess_me_is_an_ordinary_prompt(tmp_path: Path) -> None:
    reply = chat(riemann_app(tmp_path, QuizLlm()), "Assess me")
    assert reply["assessment"] is None and not reply["content"].startswith("Let's see")


def test_an_assessment_through_the_chat(tmp_path: Path) -> None:
    llm = QuizLlm()
    client = riemann_app(tmp_path, llm)
    assessment_on(client, teach_me=True, quiz_me=True)
    reply = chat(client, "Test me on everything")  # not a quiz on "everything"
    assessment = reply["assessment"]
    assert reply["content"].endswith("Question 1 of 15: Question 1?")
    assert (assessment["total"], assessment["number"], reply["quiz"]) == (15, 1, None)
    llm.verdicts.extend(["Verdict: Not quite\nAnswer: Counted."] + ["Verdict: Right"] * 14)
    for _ in range(15):
        reply = chat(client, "Primes", assessment=assessment)
        assessment = reply["assessment"]
    assert assessment is None
    assert reply["content"].startswith("That's the end of the assessment. You got 14 of 15")
    assert "Question 1, on Prime Number Basics: Counted." in reply["content"]
    assert reply["choices"] == [
        {
            "label": "Teach me about Prime Number Basics",
            "prompt": "Teach me about Prime Number Basics",
        }
    ]


def test_teach_me_isn_t_offered_when_it_is_off(tmp_path: Path) -> None:
    llm = QuizLlm()
    client = riemann_app(tmp_path, llm)
    assessment_on(client)
    assessment = chat(client, "Assess me")["assessment"]
    llm.verdicts.extend(["Verdict: Not quite"] * 15)
    for _ in range(15):
        reply = chat(client, "No", assessment=assessment)
        assessment = reply["assessment"]
    assert reply["content"].startswith("That's the end") and reply["choices"] == []


def test_an_assessment_sent_by_the_browser_is_checked(tmp_path: Path) -> None:
    client = riemann_app(tmp_path, QuizLlm())
    good = {"total": 15, "number": 1, "topic": "A", "level": 0, "part": 0, "question": "Q?"}
    answer = {"topic": "A", "level": 0, "question": "Q?", "verdict": "right", "correct": ""}
    bads: list[dict[str, Any]] = [
        {"number": 16},
        {"level": 3},
        {"number": 2},  # no answer for question 1
        {"number": 2, "answers": [{**answer, "verdict": "great"}]},
    ]
    for bad in bads:
        with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
            response = client.post(
                "/api/chat", json={"prompt": "Two", "assessment": {**good, **bad}}
            )
        assert response.status_code == 422, bad
