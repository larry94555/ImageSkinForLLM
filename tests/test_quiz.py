"""Quiz me (roadmap R41i, item 54)."""

import logging
import re
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from test_question_scope import Llm
from test_teach import CONTENTS, entry
from test_topics import riemann_app

from imageskin.chat import Conversation, LlmError, Message, Teach, Turn
from imageskin.quiz import (
    _PLAIN,
    CHANGED,
    CHOOSE,
    NO_QUIZ,
    NOTHING_TO_GO_OVER,
    PARTLY,
    QUESTIONS,
    RIGHT,
    STILL_READING_QUIZ,
    STOPPED,
    WRONG,
    Judge,
    Quiz,
    Quizzer,
    Said,
    fingerprint,
    part_for,
    plain_question,
    verdict,
)
from imageskin.review import Review
from imageskin.teach import Choice, Teacher, lesson_topics


class Writer:
    """Writes the quiz questions: "Q<n>?" in turn, as the LLM would from the material."""

    def __init__(self, *written: str) -> None:
        self.written = list(written)
        self.asked: list[tuple[str, list[str]]] = []

    def __call__(self, instruction: str, material: list[str]) -> str:
        self.asked.append((instruction, material))
        if self.written:
            return self.written.pop(0)
        return f"Q{len(self.asked)}?"


def quizzer(
    contents: list[dict[str, Any]] | None = None,
    write: Any = None,
    complete: bool = True,
    found: list[str] | None = None,
) -> Quizzer:
    return Quizzer(
        lambda: CONTENTS if contents is None else contents,
        lambda question: list(found or []),
        write or Writer(),
        lambda: complete,
    )


def kept(
    topic: str, number: int, question: str, part: int, *args: Any, found: Any = None, **kw: Any
) -> Quiz:
    """A quiz as the browser keeps it, with the fingerprint of the material its question was
    written from, as it is now."""
    material = Teacher(lambda: CONTENTS, lambda q: list(found or [])).material(
        topic, lesson_topics(CONTENTS)[topic], part
    )
    return Quiz(topic, number, question, part, *args, **{"source": fingerprint(material), **kw})


FOUND = ["(book.pdf, page 2): 2 is prime."]


def said(step: Any) -> Said:
    assert isinstance(step, Said)
    return step


def judged(step: Any) -> Judge:
    assert isinstance(step, Judge)
    return step


@pytest.mark.parametrize(
    ("reply", "found"),
    [
        ("Right! Primes have two divisors.", RIGHT),
        ("**Correct.** Well done.", RIGHT),
        ("Yes, that's it.", RIGHT),
        ("Partly right. You missed one.", PARTLY),
        ("Partially correct.", PARTLY),
        ("Half right: ...", PARTLY),
        ("Not quite. It is 2.", WRONG),
        ("Wrong.", WRONG),
        ("", WRONG),
    ],
)
def test_the_verdict_is_read_from_how_the_reply_starts(reply: str, found: str) -> None:
    assert verdict(reply) == found


def test_the_questions_are_spread_over_the_topic_s_parts_main_ideas_first() -> None:
    assert [part_for(n, 4) for n in range(1, QUESTIONS + 1)] == [0, 0, 1, 2, 3]
    assert [part_for(n, 1) for n in range(1, QUESTIONS + 1)] == [0] * QUESTIONS
    assert [part_for(n, 10) for n in range(1, QUESTIONS + 1)] == [0, 2, 4, 6, 8]


@pytest.mark.parametrize("prompt", ["Hello", "Teach me", "Quiz", "quiz me now and then"])
def test_a_prompt_with_no_quiz_going_is_left_alone(prompt: str) -> None:
    assert quizzer().step(prompt, None) is None


def test_quiz_me_with_no_topic_asks_which_one(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="imageskin.quiz"):
        step = said(quizzer().step("Can you quiz me?", None))
    assert step.sentences == [CHOOSE]
    assert step.choices == [
        Choice("Prime Numbers", "Quiz me on Prime Numbers"),
        Choice("Zeta Function", "Quiz me on Zeta Function"),
        Choice("Rain", "Quiz me on Rain"),
    ]
    assert step.quiz is None and "Quiz topic asked for" in caplog.text


def test_quiz_me_on_an_unknown_topic_says_so_and_asks_which_one() -> None:
    step = said(quizzer().step("Quiz me on knitting", None))
    assert step.sentences == ["I don't have a topic called knitting.", CHOOSE]
    assert len(step.choices) == 3


def test_with_no_material_there_is_nothing_to_quiz() -> None:
    assert said(quizzer([]).step("Quiz me", None)).sentences == [NO_QUIZ]
    waiting = said(quizzer([], complete=False).step("Test me on rain", None))
    assert (waiting.sentences, waiting.choices) == ([STILL_READING_QUIZ], [])


@pytest.mark.parametrize(
    "prompt", ["Quiz me on prime numbers", "please test me about the Prime Numbers!"]
)
def test_quiz_me_on_a_topic_asks_the_first_question(prompt: str) -> None:
    write = Writer("Question 1: **What is a prime?**\nIt has two divisors.")
    step = said(quizzer(write=write, found=FOUND).step(prompt, None))
    assert step.sentences == [
        "Let's see what you know about Prime Numbers. I'll ask you 5 questions, one at a time;"
        " say stop to end the quiz.",
        "Question 1 of 5: What is a prime?",
    ]
    assert step.quiz == kept(
        "Prime Numbers", 1, "What is a prime?", 0, ("What is a prime?",), found=FOUND
    )
    instruction, material = write.asked[0]
    assert 'about the main ideas of "Prime Numbers"' in instruction
    assert material == [
        "Prime Numbers: Primes have no divisors but 1 and themselves. A repeat in a second PDF.",
        "(book.pdf, page 2): 2 is prime.",
    ]


def test_a_question_that_can_t_be_written_is_asked_plainly(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fails(instruction: str, material: list[str]) -> str:
        raise LlmError("The LLM is not running.")

    with caplog.at_level(logging.INFO, logger="imageskin.quiz"):
        step = said(quizzer(write=fails).step("Quiz me on rain", None))
    assert step.sentences[-1] == "Question 1 of 5: What can you tell me about Rain?"
    assert "Could not write a quiz question" in caplog.text
    blank = said(quizzer(write=Writer(" \n ")).step("Quiz me on rain", None))
    assert blank.sentences[-1] == "Question 1 of 5: What can you tell me about Rain?"


LARRYS_QUESTION_1 = (
    "Euler's initial approach focused on the problem of determining how many prime numbers there"
    " are."
)


def test_a_statement_is_never_asked_as_a_question(caplog: pytest.LogCaptureFixture) -> None:
    """Larry's test (2026-10-15): question 1 was a statement, so he couldn't tell what to
    answer."""
    with caplog.at_level(logging.INFO, logger="imageskin.quiz"):
        step = said(quizzer(write=Writer(LARRYS_QUESTION_1)).step("Quiz me on rain", None))
    assert step.sentences[-1] == "Question 1 of 5: What can you tell me about Rain?"
    assert "Quiz question was not a question" in caplog.text
    mixed = Writer("Here's one. **How does rain form?** It's from clouds.")
    step = said(quizzer(write=mixed).step("Quiz me on rain", None))
    assert step.sentences[-1] == "Question 1 of 5: How does rain form?"


@pytest.mark.parametrize(
    ("prompt", "kind"),
    [
        # Larry's (2026-10-15)
        ("What's the question?", "again"),
        ("Please ask the question again", "again"),
        ("Restate the question", "again"),
        ("Can you explain the question?", "explain"),
        (
            "I don't know the answer to the question, can you just give me the answer?",
            "reveal",
        ),
        # and others like them
        ("what is the question", "again"),
        ("Sorry, what was that question?", "again"),
        ("Can you repeat the question please?", "again"),
        ("Could you rephrase that?", "again"),
        ("Say that again", "again"),
        ("Ask it again", "again"),
        ("repeat", "again"),
        ("Pardon?", "again"),
        ("I didn't catch that", "again"),
        ("What does that question mean?", "explain"),
        ("I don't understand the question", "explain"),
        ("Can you give me a hint?", "explain"),
        ("Can you clarify?", "explain"),
        ("Could you put it differently?", "explain"),
        ("I don't know", "reveal"),
        ("No idea", "reveal"),
        ("Not a clue!", "reveal"),
        ("No clue, sorry.", "reveal"),
        ("Just tell me the answer", "reveal"),
        ("What's the answer?", "reveal"),
        ("I give up", "reveal"),
        ("Skip this one", "reveal"),
        ("Pass", "reveal"),
        ("Repeat, please", "again"),
        ("Explain it", "explain"),
        # answers
        ("Evaporation", "answer"),
        # answers with a word a request may have (review on PR #88)
        ("Water can pass through soil.", "answer"),
        ("It gives a hint of how clouds form", "answer"),
        ("Skipping stones make ripples", "answer"),
        ("It cools and condenses into tiny drops that make clouds.", "answer"),
        ("The water cycle repeats itself, again and again, forever. " * 3, "answer"),
    ],
)
def test_a_reply_that_isn_t_an_answer_is_sorted_by_its_words(
    prompt: str, kind: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Larry's test (2026-10-15): "What's the question?" was judged as a wrong answer. Clear
    requests are sorted without asking the LLM."""
    write = Writer()
    with caplog.at_level(logging.INFO, logger="imageskin.quiz"):
        quizzer(write=write).step(prompt, kept("Rain", 2, "How does rain form?", 0))
    logged = next(r for r in caplog.records if r.message == "Quiz reply sorted")
    assert (logged.kind, logged.by) == (kind, "words")  # type: ignore[attr-defined]
    assert write.asked == []


@pytest.mark.parametrize(
    ("prompt", "said", "kind"),
    [
        ("I'm not sure, maybe clouds?", "A", "answer"),
        ("Help, which one do you mean by that?", "C.", "explain"),
        ("Could you say the whole question once more?", "B", "again"),
        ("I am lost here, sorry, can you help", "Letter: D", "reveal"),
        ("Is the answer clouds?", "Hmm.", "answer"),
        # its words don't make it a request (review on PR #88)
        ("The water cycle can repeat itself.", "A", "answer"),  # can't tell: taken as an answer
    ],
)
def test_a_reply_its_words_don_t_settle_is_sorted_by_the_llm(
    prompt: str, said: str, kind: str, caplog: pytest.LogCaptureFixture
) -> None:
    write = Writer(said)
    with caplog.at_level(logging.INFO, logger="imageskin.quiz"):
        quizzer(write=write).step(prompt, kept("Rain", 2, "How does rain form?", 0))
    logged = next(r for r in caplog.records if r.message == "Quiz reply sorted")
    assert (logged.kind, logged.by) == (kind, "llm")  # type: ignore[attr-defined]
    instruction, material = write.asked[0]
    assert '"How does rain form?"' in instruction and f'"{prompt}"' in instruction
    assert material == []


def test_a_reply_the_llm_can_t_sort_is_taken_as_an_answer(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fails(instruction: str, material: list[str]) -> str:
        raise LlmError("The LLM is not running.")

    with caplog.at_level(logging.INFO, logger="imageskin.quiz"):
        step = quizzer(write=fails).step("Maybe, I'm not sure", kept("Rain", 2, "Q?", 0))
    assert isinstance(step, Judge) and "Could not sort a quiz reply" in caplog.text


def test_asking_for_the_question_again_says_it_again(caplog: pytest.LogCaptureFixture) -> None:
    quiz = kept("Rain", 2, "How does rain form?", 0, right=1)
    with caplog.at_level(logging.INFO, logger="imageskin.quiz"):
        step = said(quizzer().step("Please ask the question again", quiz))
    assert step.sentences == ["Question 2 of 5: How does rain form?"]
    assert step.quiz == quiz  # still on the same question
    assert "Quiz question asked again" in caplog.text


def test_asking_what_the_question_means_explains_it_then_asks_it_again() -> None:
    quiz = kept("Rain", 2, "How does rain form?", 0, right=1)
    step = judged(quizzer().step("Can you explain the question?", quiz))
    assert "explain what the question is asking for, in simpler words, without answering" in (
        step.teach.instruction
    )
    assert step.teach.material == []  # so the answer can't be given away
    assert step.teach.then is not None
    assert step.teach.then("It asks where rain comes from.") == [
        "Question 2 of 5: How does rain form?"
    ]
    assert step.quiz == quiz  # still on the same question, nothing counted


def test_not_knowing_gives_the_answer_then_the_next_question(
    caplog: pytest.LogCaptureFixture,
) -> None:
    quiz = kept("Rain", 2, "How does rain form?", 0, ("Q1?", "How does rain form?"))
    write = Writer("Where does it fall?")
    step = judged(quizzer(write=write).step("I don't know, can you just give me the answer?", quiz))
    assert "doesn't know the answer" in step.teach.instruction
    assert step.teach.then is not None
    with caplog.at_level(logging.INFO, logger="imageskin.quiz"):
        # Even when the LLM starts kindly with "Right", it isn't counted as right.
        assert step.teach.then("Right, no problem: drops join in clouds.") == [
            "Question 3 of 5: Where does it fall?"
        ]
    assert step.quiz is not None
    assert (step.quiz.right, step.quiz.review) == (0, ("Rain",))
    logged = next(r for r in caplog.records if r.message == "Quiz answer judged")
    assert logged.verdict == "answer given"  # type: ignore[attr-defined]


def test_a_question_asked_already_is_asked_plainly_instead(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """With the real AI (Qwen 2.5 1.5B), the same question sometimes came again."""
    step = judged(
        quizzer(write=Writer("what is rain?")).step(
            "Wet", kept("Rain", 1, "What is rain?", 0, ("What is rain?",))
        )
    )
    assert step.teach.then is not None
    with caplog.at_level(logging.INFO, logger="imageskin.quiz"):
        assert step.teach.then("Right!") == ["Question 2 of 5: What can you tell me about Rain?"]
    assert "Quiz question repeated" in caplog.text


def test_an_answer_is_judged_from_the_question_s_part_then_the_next_is_asked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    write = Writer()
    q = quizzer(write=write)
    quiz = kept("Prime Numbers", 2, "What is a sieve?", 1, ("Q0?", "What is a sieve?"))
    step = judged(q.step("It crosses out multiples", quiz))
    assert step.quiz == quiz  # until the reply is in
    assert (
        'The student was asked: "What is a sieve?" The student answered: "It crosses out'
        ' multiples".'
    ) in step.teach.instruction
    assert step.teach.material == ["Sieves: A sieve crosses out multiples."]
    assert step.teach.then is not None
    with caplog.at_level(logging.INFO, logger="imageskin.quiz"):
        assert step.teach.then("Right! It does.") == ["Question 3 of 5: Q1?"]
    assert step.quiz == kept(
        "Prime Numbers", 3, "Q1?", 1, ("Q0?", "What is a sieve?", "Q1?"), right=1
    )
    assert 'about "Sieves", part of "Prime Numbers"' in write.asked[0][0]
    assert "Don't ask any of these again: Q0? What is a sieve?" in write.asked[0][0]
    logged = next(r for r in caplog.records if r.message == "Quiz answer judged")
    assert (logged.question, logged.verdict) == (2, RIGHT)  # type: ignore[attr-defined]


def test_the_last_answer_ends_the_quiz_with_the_score_and_what_to_go_over() -> None:
    quiz = kept("Prime Numbers", 5, "Q?", 3, right=2, partly=1, review=("Sieves",))
    step = judged(quizzer().step("No idea", quiz))
    assert step.teach.then is not None
    assert step.teach.then("Not quite. Primes thin out.") == [
        "That's the end of the quiz on Prime Numbers.",
        "You got 2 of 5 right, and 1 partly right.",
        "Go over Sieves and Gaps again.",
    ]
    assert step.quiz is None


def test_all_right_means_nothing_to_go_over() -> None:
    step = judged(quizzer().step("2", kept("Rain", 5, "Q?", 0, right=4)))
    assert step.teach.then is not None
    assert step.teach.then("Right!")[1:] == ["You got 5 of 5 right.", NOTHING_TO_GO_OVER]


def test_a_part_already_to_go_over_is_named_once() -> None:
    step = judged(quizzer().step("?", kept("Rain", 2, "Q?", 0, review=("Rain",))))
    assert step.teach.then is not None
    step.teach.then("Partly right.")
    assert step.quiz is not None
    assert (step.quiz.partly, step.quiz.review) == (1, ("Rain",))


def test_stop_ends_the_quiz_with_the_score_so_far(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="imageskin.quiz"):
        step = said(quizzer().step("Stop the quiz", kept("Rain", 3, "Q?", 0, right=1)))
    assert step.sentences == [STOPPED, "You got 1 of 2 right."]
    assert step.quiz is None and "Quiz stopped" in caplog.text
    assert said(quizzer().step("stop", kept("Rain", 1, "Q?", 0))).sentences == [STOPPED]


def test_a_quiz_whose_topic_is_gone_asks_again() -> None:
    step = said(quizzer().step("Two", Quiz("Knitting", 2, "Q?", 0)))
    assert step.sentences == ['"Knitting" is no longer in the material.', CHOOSE]
    assert step.quiz is None


# --- The conversation ---


def test_then_adds_sentences_after_the_llm_s_reply_spoken_and_kept() -> None:
    spoken: list[str | None] = []
    conversation = Conversation(Llm(), lambda: 4096, stream=lambda m: iter(["Right! Yes."]))
    teach = Teach("Judge it.", ["Rain: It falls."], lambda reply: [f"Next after {reply}"])
    reply, _ = conversation.send("It falls", spoken.append, teach)
    assert reply == Turn("assistant", "Right! Yes. Next after Right! Yes.")
    assert spoken == [None, "Right!", "Yes.", "Next after Right! Yes."]
    assert conversation.turns()[-1] == reply


def test_a_one_off_answer_leaves_the_conversation_alone(caplog: pytest.LogCaptureFixture) -> None:
    llm = Llm()
    conversation = Conversation(llm, lambda: 4096)
    with caplog.at_level(logging.INFO, logger="imageskin.chat"):
        assert conversation.write("Write a question.", ["Rain: It falls."]) == "Two moons."
    assert conversation.turns() == []
    sent: list[Message] = llm.sent[-1]
    assert len(sent) == 1 and "Rain: It falls." in sent[0]["content"]
    assert sent[0]["content"].endswith("Write a question.")
    assert "One-off LLM answer received" in caplog.text


# --- Through the app ---


class QuizLlm(Llm):
    """Writes "Question n?" when asked for a question, and judges answers in turn."""

    def __init__(self, *verdicts: str) -> None:
        super().__init__()
        self.verdicts = list(verdicts)
        self.written = 0

    def __call__(self, messages: list[Message]) -> str:
        self.sent.append(messages)
        asked = messages[-1]["content"]
        if "Write one short quiz question" in asked:
            self.written += 1
            return f"Question {self.written}?"
        if "Judge the answer" in asked:
            return self.verdicts.pop(0)
        return "Two moons."


def chat(client: Any, prompt: str, **kept: Any) -> dict[str, Any]:
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        response = client.post("/api/chat", json={"prompt": prompt, **kept})
    assert response.status_code == 200, response.text
    return dict(response.json())


def started(client: Any, llm: QuizLlm, topic: str, **changed: Any) -> dict[str, Any]:
    """A quiz started on the topic, as the browser sends it back, with what the test changes;
    the LLM's messages so far are forgotten."""
    quiz = dict(chat(client, f"Quiz me on {topic}")["quiz"])
    del quiz["questions"]
    llm.sent.clear()
    return {**quiz, **changed}


def test_with_quiz_me_off_quiz_me_is_an_ordinary_prompt(tmp_path: Path) -> None:
    llm = QuizLlm()
    client = riemann_app(tmp_path, llm)
    reply = chat(client, "Quiz me on Zeta Function Integral")
    assert reply["content"] == "Two moons." and reply["quiz"] is None


def test_a_quiz_through_the_chat(tmp_path: Path) -> None:
    llm = QuizLlm("Right! Yes.", "Partly right. Also x.", "Not quite. It's counted.", "Right!")
    client = riemann_app(tmp_path, llm)
    assert client.patch("/api/settings", json={"quiz_me": True}).status_code == 200
    reply = chat(client, "Quiz me")
    assert [c["label"] for c in reply["choices"]] == [
        "Prime Number Basics",
        "Zeta Function Integral",
    ]
    reply = chat(client, "Quiz me on Prime Number Basics")
    assert reply["content"].endswith("Question 1 of 5: Question 1?")
    quiz = reply["quiz"]
    assert (quiz["number"], quiz["questions"]) == (1, QUESTIONS)
    written = llm.sent[-1][-1]["content"]
    assert "Prime Number Basics: Primes are counted." in written

    for answer in ["Primes", "Some", "None", "Counting"]:
        reply = chat(client, answer, quiz={k: v for k, v in quiz.items() if k != "questions"})
        quiz = reply["quiz"]
        assert "Judge the answer" in llm.sent[-2][-1]["content"]
    assert reply["content"] == "Right! Question 5 of 5: Question 5?"
    assert (quiz["right"], quiz["partly"], quiz["review"]) == (2, 1, ["Prime Number Basics"])

    llm.verdicts.append("Not quite.")
    reply = chat(client, "Sixes", quiz={k: v for k, v in quiz.items() if k != "questions"})
    assert reply["quiz"] is None
    assert reply["content"] == (
        "Not quite. That's the end of the quiz on Prime Number Basics. You got 2 of 5 right,"
        " and 1 partly right. Go over Prime Number Basics again."
    )
    turns = client.get("/api/chat").json()["turns"]
    assert [t["content"] for t in turns if t["role"] == "user"][-2:] == ["Counting", "Sixes"]


def test_a_quiz_answer_isn_t_taken_by_a_lesson_going(tmp_path: Path) -> None:
    llm = QuizLlm("Right!")
    client = riemann_app(tmp_path, llm)
    client.patch("/api/settings", json={"quiz_me": True, "teach_me": True})
    lesson = {"topic": "Zeta Function Integral", "part": 0, "active": True}
    quiz = started(client, llm, "Zeta Function Integral")
    reply = chat(client, "Next", lesson=lesson, quiz=quiz)
    assert reply["content"].startswith("Right!") and reply["quiz"]["number"] == 2
    assert reply["lesson"] == {**lesson, "parts": 1}  # where it was


def test_the_end_of_a_lesson_s_topic_offers_a_quiz_on_it(tmp_path: Path) -> None:
    client = riemann_app(tmp_path, QuizLlm())
    lesson = {"topic": "Zeta Function Integral", "part": 0, "active": True}
    client.patch("/api/settings", json={"teach_me": True})
    assert chat(client, "Next", lesson=lesson)["choices"] == []  # only with Quiz me on
    client.patch("/api/settings", json={"quiz_me": True})
    reply = chat(client, "Next", lesson=lesson)
    assert reply["lesson"]["part"] == 1  # the summary
    assert reply["choices"] == [
        {
            "label": "Quiz me on Zeta Function Integral",
            "prompt": "Quiz me on Zeta Function Integral",
        }
    ]


def test_a_quiz_sent_by_the_browser_is_checked(tmp_path: Path) -> None:
    client = riemann_app(tmp_path, QuizLlm())
    bads: list[dict[str, Any]] = [
        {"number": 0},
        {"number": QUESTIONS + 1},
        {"right": -1},
        {"asked": ["Q"] * 9},
    ]
    for bad in bads:
        quiz = {"topic": "A", "number": 1, "question": "Q?", "part": 0, **bad}
        with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
            response = client.post("/api/chat", json={"prompt": "Two", "quiz": quiz})
        assert response.status_code == 422, bad


def test_larrys_whats_the_question_through_the_chat(tmp_path: Path) -> None:
    llm = QuizLlm()
    client = riemann_app(tmp_path, llm)
    client.patch("/api/settings", json={"quiz_me": True})
    quiz = started(client, llm, "Prime Number Basics", question="How are primes counted?")
    reply = chat(client, "What's the question?", quiz=quiz)
    assert reply["content"] == "Question 1 of 5: How are primes counted?"
    assert reply["quiz"]["number"] == 1 and llm.sent == []  # not judged


def test_larrys_other_replies_through_the_chat(tmp_path: Path) -> None:
    llm = QuizLlm()
    client = riemann_app(tmp_path, llm)
    client.patch("/api/settings", json={"quiz_me": True})
    quiz = started(client, llm, "Prime Number Basics", question="How?")
    reply = chat(client, "Can you explain the question?", quiz=quiz)
    assert reply["content"] == "Two moons. Question 1 of 5: How?"
    assert reply["quiz"]["number"] == 1  # still on it
    assert "explain what the question is asking" in llm.sent[-1][-1]["content"]
    reply = chat(
        client,
        "I don't know the answer to the question, can you just give me the answer?",
        quiz=quiz,
    )
    assert reply["content"] == "Two moons. Question 2 of 5: Question 2?"
    assert (reply["quiz"]["right"], reply["quiz"]["review"]) == (0, ["Prime Number Basics"])


def test_a_one_part_topic_never_asks_the_same_plain_question_twice() -> None:
    """Review on PR #88: with the LLM down, or writing statements, a quiz on a one-part topic
    asked "What can you tell me about Rain?" five times."""

    def fails(instruction: str, material: list[str]) -> str:
        raise LlmError("The LLM is not running.")

    for write in [fails, lambda instruction, material: LARRYS_QUESTION_1]:
        q = quizzer(write=write)
        quiz = said(q.step("Quiz me on rain", None)).quiz
        assert quiz is not None
        for _ in range(QUESTIONS - 1):
            step = judged(q.step("It falls", quiz))
            assert step.teach.then is not None
            step.teach.then("Right!")
            assert step.quiz is not None
            quiz = step.quiz
        assert len({a.casefold() for a in quiz.asked}) == QUESTIONS
        assert quiz.asked[:2] == (
            "What can you tell me about Rain?",
            "What is the main idea of Rain?",
        )


def test_a_question_asked_already_with_other_spacing_or_punctuation_is_not_asked_again(
    caplog: pytest.LogCaptureFixture,
) -> None:
    step = judged(
        quizzer(write=Writer("  What   is RAIN ?!")).step(
            "Wet", kept("Rain", 1, "What is rain?", 0, ("What is rain?",))
        )
    )
    assert step.teach.then is not None
    with caplog.at_level(logging.INFO, logger="imageskin.quiz"):
        assert step.teach.then("Right!") == ["Question 2 of 5: What can you tell me about Rain?"]
    assert "Quiz question repeated" in caplog.text


def rain_contents(summary: str) -> list[dict[str, Any]]:
    return [{"entries": [entry("Rain", summary)]}]


def test_an_answer_is_judged_from_the_material_its_question_was_written_from(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Review on PR #88: the wiki rebuilt between asking and answering (the quiz is kept over a
    reload) judged the answer from material the question wasn't written from."""
    contents = rain_contents("It falls.")
    q = quizzer(contents=contents, write=Writer("Where does rain fall?", "Why is rain wet?"))
    quiz = said(q.step("Quiz me on rain", None)).quiz
    assert quiz is not None
    assert judged(q.step("Down", quiz)).teach.material == ["Rain: It falls."]  # unchanged

    contents[:] = rain_contents("It is water from clouds.")
    with caplog.at_level(logging.INFO, logger="imageskin.quiz"):
        step = said(q.step("Down", quiz))
    assert step.sentences == [CHANGED, "Question 1 of 5: Why is rain wet?"]
    assert step.quiz is not None
    assert (step.quiz.number, step.quiz.asked) == (1, ("Why is rain wet?",))
    assert step.quiz.source == fingerprint(["Rain: It is water from clouds."]) != quiz.source
    assert "Quiz material changed" in caplog.text
    assert judged(q.step("Clouds", step.quiz)).teach.material == ["Rain: It is water from clouds."]


@pytest.mark.parametrize("kept_quiz", [{"source": ""}, {"part": 3}])
def test_a_question_with_no_material_now_is_asked_anew(kept_quiz: dict[str, Any]) -> None:
    """A quiz kept by a browser before questions had a fingerprint, or whose part is gone."""
    quiz = kept("Rain", 2, "Q?", 0, ("Q0?", "Q?"))
    step = said(quizzer(write=Writer("Is rain wet?")).step("Wet", replace(quiz, **kept_quiz)))
    assert step.sentences == [CHANGED, "Question 2 of 5: Is rain wet?"]
    assert step.quiz is not None
    assert (step.quiz.part, step.quiz.asked) == (0, ("Q0?", "Is rain wet?"))


def test_every_plain_question_asks_only_what_the_material_says() -> None:
    """Review on PR #88: with material as small as "Rain: It falls.", a plain question must still
    be answerable from it, so none asks why, for an example, or anything beyond the part."""
    asked: tuple[str, ...] = ()
    for _ in range(QUESTIONS):
        asked = (*asked, plain_question("Rain", asked))
    assert asked == tuple(p.format("Rain") for p in _PLAIN)
    for question in asked:
        assert re.search(r"\b(?:why|example|how does|matter)\b", question.lower()) is None
        assert re.search(r"\b(?:tell|main idea|describe|learned|know)\b", question) is not None
