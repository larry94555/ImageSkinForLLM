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
    CHECKING,
    CHOOSE_NOTHING,
    EXPLAIN_IT,
    GONE,
    HELP,
    MOST_QUESTIONS,
    NOTHING_TO_GO_OVER,
    PLAIN,
    RECALL,
    STILL_READING,
    STOPPED,
    TOO_MANY,
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

    def __init__(
        self, *verdicts: str, questions: list[str] | None = None, sorts: list[str] | None = None
    ) -> None:
        self.verdicts = list(verdicts)
        self.questions = list(questions or [])
        self.sorts = list(sorts or [])  # how each reply the words don't settle is sorted
        self.asked: list[tuple[str, list[str]]] = []
        self.written = 0

    def __call__(self, instruction: str, material: list[str]) -> str:
        self.asked.append((instruction, material))
        if instruction.startswith("Write one short quiz question"):
            self.written += 1
            return self.questions.pop(0) if self.questions else f"Q{self.written}?"
        if instruction.startswith("In an assessment, a student was asked"):
            return self.sorts.pop(0) if self.sorts else "A"
        if instruction.startswith("In an assessment, the student"):
            return "It asks what Euler set out to do."
        if instruction.startswith("The student stopped an assessment"):
            return "Euler started by counting the primes."
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
    assert max(levels.values()) - min(levels.values()) <= 1 and len(levels) == 3


@pytest.mark.parametrize("topics", [1, 2, 4, 5, 7, 10, 14])
def test_a_topic_asked_again_moves_to_another_level(topics: int) -> None:
    """Review on PR #90: with 4 topics, the fourth was asked to recall four times."""
    plan = [planned(i, topics) for i in range(size(topics))]
    for topic in range(topics):
        levels = [level for t, level in plan if t == topic]
        assert all(a != b for a, b in zip(levels, levels[1:], strict=False)), levels
        assert len(set(levels)) == min(len(levels), 3), levels


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


@pytest.mark.parametrize(
    ("topics", "starts"), [(MOST_QUESTIONS, True), (MOST_QUESTIONS + 1, False)]
)
def test_with_too_many_topics_it_says_so_rather_than_leave_some_out(
    topics: int, starts: bool
) -> None:
    """Review on PR #90: with 201 topics, one was never asked about."""
    many = [{"entries": [entry(f"T{n}", "Some.") for n in range(topics)]}]
    step = assessed(assessor(contents=many).step("Assess me", None))
    if starts:
        assert step.assessment is not None and step.assessment.total == topics
    else:
        assert step.sentences == [TOO_MANY.format(201, 200)] and step.assessment is None


def test_it_waits_until_all_the_material_is_read() -> None:
    """Review on PR #90: it covers all the content, so topics from some files aren't enough."""
    some = assessed(assessor(complete=False).step("Assess me", None))
    assert (some.sentences, some.assessment) == ([STILL_READING], None)


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
            step = assessed(a.step(f"Reply {n}", assessment))
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
    assert 'The student answered: "Reply 1"' in instruction and "Verdict:" in instruction
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
    write = Writer()
    a = assessor(write=write)
    first = started(a)
    again = assessed(a.step("What's the question?", first))
    assert again.sentences == ["Question 1 of 15: Q1?"] and again.assessment == first
    explain = assessed(a.step("Can you explain the question?", first))
    assert explain.sentences == ["It asks what Euler set out to do.", "Question 1 of 15: Q1?"]
    assert explain.assessment == first
    instruction, material = write.asked[-1]
    assert "without answering it and without saying whether any guess is right" in instruction
    assert material == []  # so the answer can't be given away


LARRYS_DIALOGUE = [  # Larry's test (2026-10-15): each of these was taken as an answer
    ("Was his initial approach to attempt to count the number of primes?", "B", "clarify"),
    ("Can you give me the answer to question 1?", None, "talk"),
]


@pytest.mark.parametrize(
    ("prompt", "sorted_as", "kind"),
    [
        *LARRYS_DIALOGUE,
        ("Can I have a hint?", None, "clarify"),
        ("How many questions are left?", None, "process"),
        ("Is this assessment marked?", None, "process"),
        ("How does this work?", None, "process"),
        ("Can I stop and come back later?", None, "process"),
        ("Will I get a score at the end?", None, "process"),
        ("Which part of the course is this from?", "C.", "process"),
        ("What was the answer to question 2?", None, "talk"),
        ("Could we talk about that question?", None, "talk"),
        ("Hmm, I'd rather go over the one before, help", "Letter: D", "talk"),
        ("I don't know", None, "don't know"),
        ("Is it the sun?", "A", "answer"),  # a guess the LLM takes as an answer
        ("Euler counted the primes by a product over them.", None, "answer"),
        ("It's about primes, question everything " * 12, None, "answer"),  # long: an answer
    ],
)
def test_each_reply_is_sorted_before_it_counts_as_an_answer(
    prompt: str, sorted_as: str | None, kind: str, caplog: pytest.LogCaptureFixture
) -> None:
    write = Writer(sorts=[sorted_as] if sorted_as else [])
    a = assessor(write=write)
    first = started(a)
    with caplog.at_level(logging.INFO, logger="imageskin.assess"):
        a.step(prompt, first)
    logged = next(r for r in caplog.records if r.message == "Assessment reply sorted")
    by = "llm" if sorted_as else "words"
    assert (logged.kind, logged.by) == (kind, by)  # type: ignore[attr-defined]


def test_larrys_clarifying_question_isn_t_taken_as_an_answer() -> None:
    a = assessor(write=Writer(sorts=["B"]))
    first = started(a)
    step = assessed(a.step(LARRYS_DIALOGUE[0][0], first))
    assert step.assessment == first  # still on question 1, nothing counted
    assert step.sentences == [CHECKING, "Question 1 of 15: Q1?"]  # neither confirmed nor denied


@pytest.mark.parametrize(
    "prompt", ["Do you mean the first one?", "Is the question about Euler or Riemann?"]
)
def test_a_question_about_what_the_question_means_is_answered_by_the_llm(prompt: str) -> None:
    a = assessor(write=Writer(sorts=["B"]))
    first = started(a)
    step = assessed(a.step(prompt, first))
    assert step.sentences == ["It asks what Euler set out to do.", "Question 1 of 15: Q1?"]


@pytest.mark.parametrize(
    "prompt",
    [
        "Don't give me the answer, just give me a hint",
        "Don't give me the answer, just a hint",
        "I don't want you to tell me the answer; can I have a clue?",
    ],
)
def test_saying_not_to_give_the_answer_is_a_hint_not_a_stop(prompt: str) -> None:
    """Review on PR #90: these stopped the assessment and gave the answer away."""
    write = Writer()
    a = assessor(write=write)
    first = started(a)
    step = assessed(a.step(prompt, first))
    assert step.assessment == first
    instruction, material = write.asked[-1]
    assert "Never state the answer" in instruction and material


def test_saying_not_to_give_the_answer_without_a_hint_is_sorted_by_the_llm() -> None:
    write = Writer(sorts=["B"])
    a = assessor(write=write)
    first = started(a)
    step = assessed(a.step("Don't tell me the answer yet", first))
    assert step.assessment == first  # not "I don't know", and not a stop
    assert write.asked[-2][0].startswith("In an assessment, a student was asked")


@pytest.mark.parametrize(
    ("again", "correct"), [("Euler multiplied.", "Euler multiplied."), ("", "")]
)
def test_a_judgement_with_no_answer_still_keeps_the_correct_one(
    again: str, correct: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Review on PR #90: a "Verdict: Not quite" with no "Answer:" left the answer out of the
    evaluation; it is asked for again, or the material's first sentence is kept."""

    def judge(instruction: str, material: list[str]) -> str:
        if instruction.startswith("Write"):
            return "Q?"
        if instruction.startswith("In one short sentence, give the correct answer"):
            return again
        return "Verdict: Not quite"

    a = assessor(contents=[{"entries": [entry("Rain", "It falls. It is wet.")]}], write=judge)
    first = started(a)
    with caplog.at_level(logging.INFO, logger="imageskin.assess"):
        step = assessed(a.step("Up", first))
    assert step.assessment is not None
    kept = step.assessment.answers[0].correct
    assert kept == (correct or "Rain: It falls.")  # never empty
    assert "Assessment judgement had no answer" in caplog.text


def test_a_hint_is_written_from_the_material_without_the_answer() -> None:
    """Larry's run (2026-10-15): without the material a hint guessed, and guessed wrong."""
    write = Writer()
    a = assessor(write=write)
    first = started(a)
    step = assessed(a.step("Can I have a hint?", first))
    assert step.assessment == first  # still on question 1, nothing counted
    instruction, material = write.asked[-1]
    assert "Never state the answer or any part of it" in instruction
    assert material  # the question's material, so the hint points the right way


@pytest.mark.parametrize(
    ("prompt", "said"),
    [
        ("How many questions are left?", "This is question 1 of 15, so 14 more come after it."),
        ("What question am I on?", "This is question 1 of 15."),
        ("Is this assessment marked?", "Each answer is judged right, partly right or wrong,"),
        ("Can I stop if I want to?", "Yes: say stop at any time"),
        (
            "Can I stop and come back later?",  # review on PR #90: stopping ends it
            "Yes: say stop at any time to end the assessment and hear how you did so far, but"
            " it can't be picked up again after that. If you just leave or reload the page, it"
            " stays where it is",
        ),
        ("How does this work?", "There are 15 questions across every topic"),
    ],
)
def test_a_clear_question_about_the_assessment_is_answered_without_the_llm(
    prompt: str, said: str
) -> None:
    """Larry's run (2026-10-15): the small LLM said 14 of 15 were answered on question 1."""
    write = Writer()
    a = assessor(write=write)
    first = started(a)
    asked = len(write.asked)
    step = assessed(a.step(prompt, first))
    assert step.assessment == first  # still on question 1, nothing counted
    assert step.sentences[0].startswith(said)
    assert step.sentences[1] == "Question 1 of 15: Q1?"
    assert len(write.asked) == asked


def test_a_question_about_the_assessment_is_answered_and_it_carries_on() -> None:
    write = Writer(sorts=["C"])
    a = assessor(write=write)
    first = started(a)
    step = assessed(a.step("Which part of the course is this from?", first))
    assert step.assessment == first
    instruction, material = write.asked[-1]
    assert "this is question 1 of 15, so 14 more come after it" in instruction
    assert 'it is fine to say "stop" at any time to stop the assessment and talk' in instruction
    assert material == []


def test_asking_for_an_answer_stops_the_assessment_to_talk_about_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Larry (2026-10-15): it is fine to stop the assessment and talk about the questions."""
    write = Writer("Verdict: Not quite\nAnswer: He multiplied over the primes.")
    a = assessor(write=write)
    second = assessed(a.step("Primes", started(a))).assessment
    with caplog.at_level(logging.INFO, logger="imageskin.assess"):
        step = assessed(a.step(LARRYS_DIALOGUE[1][0], second))
    assert step.assessment is None
    assert step.sentences[:3] == [
        "OK, we'll stop the assessment here so we can talk about it.",
        "Euler started by counting the primes.",
        "You got 0 of 1 right.",
    ]
    instruction, material = write.asked[-1]
    assert '"Can you give me the answer to question 1?"' in instruction
    assert material[:2] == [
        "Question 1 was: Q1? The correct answer: He multiplied over the primes.",
        "Question 2, not answered yet, was: Q2?",
    ]
    assert "Assessment stopped to talk" in caplog.text


def test_when_the_llm_can_t_help_a_plain_reply_is_given(
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls = []

    def flaky(instruction: str, material: list[str]) -> str:
        calls.append(instruction)
        if instruction.startswith("Write"):
            return "Q?"
        raise LlmError("The LLM is not running.")

    a = assessor(write=flaky)
    first = started(a)
    with caplog.at_level(logging.INFO, logger="imageskin.assess"):
        sorted_as = assessed(a.step("Can you explain the question?", first))
        assert sorted_as.sentences == [HELP, "Question 1 of 15: Q?"]
        talk = assessed(a.step("Tell me the answer", first))
        assert talk.sentences == ["OK, we'll stop the assessment here so we can talk about it."]
        with pytest.raises(LlmError):  # not sortable: an answer, which can't be judged
            a.step("Is it the sun?", first)
    assert "Could not answer an assessment question" in caplog.text
    assert "Could not talk about the assessment" in caplog.text
    assert "Could not sort an assessment reply" in caplog.text


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


@pytest.mark.parametrize(
    "now",
    [
        ["Rain", "Snow", "Hail", "Fog"],  # one added, still 15 questions
        ["Rain", "Snow"],  # one removed
        ["Rain", "Snow", "Fog"],  # one replaced, same count
        ["Snow", "Rain", "Hail"],  # reordered
    ],
)
def test_any_change_in_the_topics_ends_it_even_at_the_same_size(now: list[str]) -> None:
    """Review on PR #90: the plan comes from the topics in order, so it can't change under it."""
    contents = [{"entries": [entry(name, "Some.") for name in ["Rain", "Snow", "Hail"]]}]
    a = assessor(contents=contents)
    first = started(a)
    assert first.topic == "Rain"  # the current topic is still there in every case
    contents[:] = [{"entries": [entry(name, "Some.") for name in now]}]
    step = assessed(a.step("Wet", first))
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
    gone = Assessment(first.total, 1, "Rain", RECALL, 4, "Q?", first.source, first.plan)
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
        "How would you describe Rain to a friend?",  # explain, not apply: see below
    ]


def test_a_plain_question_can_be_answered_from_the_least_material() -> None:
    """Review on PR #90: "How do the ideas in Rain fit together?" can't be answered from "Rain:
    It falls.", so an apply question the LLM can't write is asked as an explain question, and
    counted as one."""
    judged: list[list[str]] = []

    def fails(instruction: str, material: list[str]) -> str:
        if instruction.startswith("Write"):
            raise LlmError("The LLM is not running.")
        judged.append(material)
        return "Verdict: Right\nAnswer: It falls."

    a = assessor(contents=[{"entries": [entry("Rain", "It falls.")]}], write=fails)
    step = assessed(a.step("Assess me", None))
    answers: tuple[Answer, ...] = ()
    while step.assessment is not None:
        question = step.assessment.question
        assert step.assessment.level != APPLY
        assert question.split("Rain")[0] in {q.split("{}")[0] for pool in PLAIN for q in pool}
        answers = (*step.assessment.answers,)
        step = assessed(a.step("It falls", step.assessment))
    assert all(m == judged[0] for m in judged) and "It falls." in judged[0][0]
    assert {a.level for a in answers} == {RECALL, EXPLAIN_IT}
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


def test_larrys_dialogue_through_the_chat(tmp_path: Path) -> None:
    llm = QuizLlm()
    client = riemann_app(tmp_path, llm)
    assessment_on(client)
    first = chat(client, "Assess me")["assessment"]
    reply = chat(client, "Can you explain the question?", assessment=first)
    assert reply["content"] == "Two moons. Question 1 of 15: Question 1?"
    assert reply["assessment"] == first  # not taken as an answer
    reply = chat(client, "Can you give me the answer to question 1?", assessment=first)
    assert reply["assessment"] is None
    assert (
        reply["content"] == "OK, we'll stop the assessment here so we can talk about it. Two moons."
    )
