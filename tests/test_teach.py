"""Teach me (roadmap R41h, item 54)."""

import logging
import threading
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from test_question_scope import Llm
from test_topics import app_with_topics, riemann_app

from imageskin.chat import Conversation, Turn
from imageskin.review import Review
from imageskin.teach import (
    ALL_DONE,
    CHOOSE,
    EVERYTHING,
    EVERYTHING_SO_FAR,
    MORE_COMING,
    NO_LESSON,
    NOT_YET,
    STILL_READING_LESSON,
    STOPPED,
    Choice,
    Explain,
    Lesson,
    Part,
    Say,
    Teacher,
    lesson_topics,
)


def entry(title: str, summary: str, *parts: dict[str, Any]) -> dict[str, Any]:
    return {"title": title, "summary": summary, "entries": list(parts)}


CONTENTS = [
    {
        "entries": [
            entry(
                "Prime Numbers",
                "Primes have no divisors but 1 and themselves.",
                entry("Sieves", "A sieve crosses out multiples.", entry("Eratosthenes", "Oldest.")),
                entry("Gaps", "Primes thin out."),
            ),
            entry("Zeta Function", "Zeta sums 1/n^s."),
        ]
    },
    {"entries": [entry("prime numbers", "A repeat in a second PDF."), entry("Rain", "It falls.")]},
]


def teacher(
    contents: list[dict[str, Any]] | None = None,
    found: list[str] | None = None,
    complete: bool = True,
) -> Teacher:
    asked: list[str] = []

    def find(question: str) -> list[str]:
        asked.append(question)
        return list(found or [])

    t = Teacher(lambda: CONTENTS if contents is None else contents, find, lambda: complete)
    t.asked = asked  # type: ignore[attr-defined]
    return t


def explained(step: Any) -> Explain:
    assert isinstance(step, Explain)
    return step


def said(step: Any) -> Say:
    assert isinstance(step, Say)
    return step


def test_each_topic_is_taught_in_parts_main_ideas_first_then_each_entry_under_it() -> None:
    assert lesson_topics(CONTENTS) == {
        "Prime Numbers": [
            # The second PDF's "prime numbers" is the same topic: its summary is taught too.
            Part(
                "Prime Numbers",
                "Primes have no divisors but 1 and themselves. A repeat in a second PDF.",
            ),
            Part("Sieves", "A sieve crosses out multiples."),
            Part("Eratosthenes", "Oldest."),
            Part("Gaps", "Primes thin out."),
        ],
        "Zeta Function": [Part("Zeta Function", "Zeta sums 1/n^s.")],
        "Rain": [Part("Rain", "It falls.")],
    }


def test_a_topic_in_several_pdfs_is_taught_from_all_of_them() -> None:
    """Review on PR #87: what a later PDF has under the same topic is never left out."""
    contents = [
        {"entries": [entry("Primes", "Have two divisors.", entry("Gaps", "Primes thin out."))]},
        {"entries": [entry("Rain", "It falls.")]},
        {
            "entries": [
                entry(
                    " primes ",
                    "Have two divisors.",  # already said: not said twice
                    entry("Gaps", "Primes thin out."),
                    entry("gaps", "Twin primes have a gap of 2."),
                    entry("Twin Primes", "Pairs two apart.", entry("Cousins", "Four apart.")),
                ),
                entry("  ", "No title: not a topic."),
            ]
        },
    ]
    assert lesson_topics(contents) == {
        "Primes": [
            Part("Primes", "Have two divisors."),
            Part("Gaps", "Primes thin out. Twin primes have a gap of 2."),
            Part("Twin Primes", "Pairs two apart."),
            Part("Cousins", "Four apart."),
        ],
        "Rain": [Part("Rain", "It falls.")],
    }
    step = explained(teacher(contents).step("Next", Lesson("Primes", 1)))
    assert step.lesson == Lesson("Primes", 2)
    assert step.teach.material[0] == "Twin Primes: Pairs two apart."


@pytest.mark.parametrize(
    "prompt", ["Hello", "What is a prime?", "Next", "Teach me how to fish", "teacher me"]
)
def test_an_ordinary_prompt_with_no_lesson_going_is_left_alone(prompt: str) -> None:
    assert teacher().step(prompt, None) is None
    assert teacher().step(prompt, Lesson("Rain", 0, active=False)) is None


def test_teach_me_with_no_topic_asks_which_one() -> None:
    step = said(teacher().step("Teach me", None))
    assert step.sentences == [CHOOSE, "Pick one of the topics, or everything from the start."]
    assert step.lesson is None
    assert step.choices == [
        Choice("Prime Numbers", "Teach me about Prime Numbers"),
        Choice("Zeta Function", "Teach me about Zeta Function"),
        Choice("Rain", "Teach me about Rain"),
        Choice(EVERYTHING, "Teach me everything from the start"),
    ]


def test_teach_me_offers_to_carry_on_where_the_student_left_off() -> None:
    left = Lesson("Zeta Function", 1, active=False)
    step = said(teacher().step("Can you teach me?", left))
    assert step.choices[0] == Choice("Carry on with Zeta Function", "Teach me about Zeta Function")
    assert step.lesson == left  # kept until they choose


@pytest.mark.parametrize(
    "prompt", ["Teach me about prime numbers", "please teach me on the Prime Numbers!"]
)
def test_teach_me_about_a_topic_starts_at_its_main_ideas(prompt: str) -> None:
    t = teacher(found=["Primes (book.pdf, page 2): 2, 3, 5 and 7 are prime."])
    step = explained(t.step(prompt, None))
    assert step.lesson == Lesson("Prime Numbers", 0)
    assert step.kind == "start"
    assert step.teach.instruction.startswith('Teach me the main ideas of "Prime Numbers"')
    assert step.teach.material == [
        "Prime Numbers: Primes have no divisors but 1 and themselves. A repeat in a second PDF.",
        "Primes (book.pdf, page 2): 2, 3, 5 and 7 are prime.",
    ]
    assert t.asked == ["Prime Numbers"]  # type: ignore[attr-defined]


def test_a_topic_named_inside_a_longer_phrase_is_found() -> None:
    step = explained(teacher().step("Teach me about the history of the zeta function", None))
    assert step.lesson == Lesson("Zeta Function", 0)


def test_teach_me_about_an_unknown_topic_says_so_and_asks_which_one() -> None:
    step = said(teacher().step("Teach me about volcanoes", None))
    assert step.sentences[0] == "I don't have a topic called volcanoes."
    assert step.choices[-1].label == EVERYTHING


def test_teach_me_everything_starts_at_the_first_topic() -> None:
    for prompt in ["Teach me everything from the start", "teach me everything"]:
        assert explained(teacher().step(prompt, None)).lesson == Lesson("Prime Numbers", 0)


def test_teach_me_about_the_topic_left_off_carries_on_from_the_same_part() -> None:
    left = Lesson("Prime Numbers", 2, active=False)
    step = explained(teacher().step("Teach me about Prime Numbers", left))
    assert (step.lesson, step.kind) == (Lesson("Prime Numbers", 2), "resume")
    assert step.teach.instruction.startswith('Teach me "Eratosthenes", part of "Prime Numbers"')
    # a part past the end (the wiki changed) is the topic's summary
    step = explained(teacher().step("Teach me about Rain", Lesson("Rain", 9)))
    assert step.lesson == Lesson("Rain", 1) and step.kind == "summary"


def test_next_goes_through_the_parts_then_the_summary_then_the_next_topic() -> None:
    t = teacher()
    lesson = Lesson("Prime Numbers", 0)
    seen = []
    for _ in range(6):
        step = explained(t.step("Next", lesson))
        lesson = step.lesson
        seen.append((lesson.topic, lesson.part, step.kind))
    assert seen == [
        ("Prime Numbers", 1, "next"),
        ("Prime Numbers", 2, "next"),
        ("Prime Numbers", 3, "next"),
        ("Prime Numbers", 4, "summary"),
        ("Zeta Function", 0, "next"),
        ("Zeta Function", 1, "summary"),
    ]
    assert step.teach.instruction.startswith("Sum up in one sentence what we have just learned")
    assert step.teach.material == ["Zeta Function: Zeta sums 1/n^s."]


@pytest.mark.parametrize(
    "prompt", ["next", "OK, next.", "Go on", "carry on please", "What's next?"]
)
def test_next_can_be_said_several_ways(prompt: str) -> None:
    assert explained(teacher().step(prompt, Lesson("Rain", 0))).lesson == Lesson("Rain", 1)


def test_after_the_last_topic_the_lesson_is_over(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="imageskin.teach"):
        step = said(teacher().step("next", Lesson("Rain", 1)))
    assert (step.sentences, step.lesson) == ([ALL_DONE], None)
    assert any(r.message == "Lesson finished" for r in caplog.records)


@pytest.mark.parametrize(
    "prompt", ["Say it more simply", "simpler please", "Can you explain that again, more simply?",
               "I don't get it"]
)  # fmt: skip
def test_more_simply_teaches_the_same_part_again(prompt: str) -> None:
    step = explained(teacher().step(prompt, Lesson("Prime Numbers", 1)))
    assert (step.lesson, step.kind) == (Lesson("Prime Numbers", 1), "simpler")
    assert step.teach.instruction.startswith('Explain "Sieves", part of "Prime Numbers" again')
    assert "everyday example" in step.teach.instruction


def test_stop_keeps_the_place_so_the_student_can_carry_on_later() -> None:
    step = said(teacher().step("Stop the lesson", Lesson("Prime Numbers", 3)))
    assert (step.sentences, step.lesson) == ([STOPPED], Lesson("Prime Numbers", 3, active=False))


def test_a_question_partway_is_answered_from_the_part_and_the_lesson_stays(
    caplog: pytest.LogCaptureFixture,
) -> None:
    t = teacher(found=["Sieve (book.pdf, page 4): cross out every second number."])
    with caplog.at_level(logging.INFO, logger="imageskin.teach"):
        step = explained(t.step("Why does that work?", Lesson("Prime Numbers", 1)))
    assert any(r.message == "Lesson question" for r in caplog.records)
    assert (step.lesson, step.kind) == (Lesson("Prime Numbers", 1), "question")
    assert step.teach.instruction == "Why does that work?"
    assert step.teach.material[0] == "Sieves: A sieve crosses out multiples."
    assert "Sieve (book.pdf, page 4): cross out every second number." in step.teach.material


def test_a_lesson_whose_topic_is_gone_asks_again(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="imageskin.teach"):
        step = said(teacher().step("next", Lesson("Volcanoes", 2)))
    assert step.sentences[0] == '"Volcanoes" is no longer in the material.'
    assert step.lesson is None and step.choices


def test_with_no_material_there_is_nothing_to_teach() -> None:
    step = said(teacher(contents=[]).step("Teach me", None))
    assert step.sentences == [NO_LESSON]


def test_a_failed_lookup_still_teaches_from_the_wiki(caplog: pytest.LogCaptureFixture) -> None:
    def broken(question: str) -> list[str]:
        raise OSError("disk")

    with caplog.at_level(logging.ERROR, logger="imageskin.teach"):
        step = explained(Teacher(lambda: CONTENTS, broken).step("Teach me about Rain", None))
    assert step.teach.material == ["Rain: It falls."]
    assert "Could not look the lesson part up in the content" in caplog.text


def test_a_reply_made_outside_the_llm_is_spoken_and_kept() -> None:
    llm = Llm()
    spoken: list[str | None] = []
    conversation = Conversation(llm, lambda: 4096, stream=lambda m: iter(["Hi."]))
    reply, place = conversation.say("Teach me", ["Which one?", "Pick one."], spoken.append)
    assert (reply, place) == (Turn("assistant", "Which one? Pick one."), 1)
    assert spoken == [None, "Which one?", "Pick one."]
    conversation.send("Hello")
    assert conversation.turns()[0] == Turn("user", "Teach me")


def test_a_reply_made_outside_the_llm_checks_the_prompt_as_send_does() -> None:
    """Review on PR #87: a prompt too long for the context is refused, never kept."""
    conversation = Conversation(Llm(), lambda: 2048)
    for prompt in ["🐶" * 300, "  "]:
        with pytest.raises(ValueError) as said_:
            conversation.say(prompt, ["Which one?"])
        with pytest.raises(ValueError) as sent:
            conversation.send(prompt)
        assert str(said_.value) == str(sent.value)
    assert conversation.turns() == []


def test_while_material_is_still_read_the_lesson_never_says_that_is_everything(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Review on PR #87: the topics so far are never given as all there is."""
    asked = said(teacher(complete=False).step("Teach me", None))
    assert asked.sentences[-1] == MORE_COMING
    assert asked.choices[-1] == Choice(EVERYTHING_SO_FAR, "Teach me everything from the start")
    with caplog.at_level(logging.INFO, logger="imageskin.teach"):
        waiting = said(teacher(complete=False).step("Next", Lesson("Rain", 1)))
    assert waiting.sentences == [NOT_YET]
    assert waiting.lesson == Lesson("Rain", 1)  # still on the summary, to carry on from
    assert "Lesson waiting for material" in caplog.text


def test_with_no_topic_yet_while_material_is_read_teach_me_says_so() -> None:
    """Review on PR #87: "no material has been added" only when that is true."""
    assert said(teacher([], complete=False).step("Teach me", None)) == Say(
        [STILL_READING_LESSON], None, []
    )
    assert said(teacher([], complete=False).step("Teach me everything", None)).choices == []
    assert said(teacher([]).step("Teach me", None)).sentences == [NO_LESSON]


def test_a_question_on_the_summary_is_answered_from_the_whole_topic() -> None:
    """Review on PR #87: the material the summary was made from, not the last part's."""
    t = teacher(found=["(book.pdf, page 2): More."])
    summary = explained(t.step("Next", Lesson("Prime Numbers", 3)))
    step = explained(t.step("Why does that matter?", summary.lesson))
    assert step.kind == "question" and step.lesson == Lesson("Prime Numbers", 4)
    assert step.teach.material == [*summary.teach.material, "(book.pdf, page 2): More."]
    assert "Sieves: A sieve crosses out multiples." in step.teach.material


def test_a_part_s_own_wiki_entry_is_given_once() -> None:
    """Review on PR #87: the lookup finds the part's own entry too; it isn't given twice."""
    found = [
        "Sieves (book.pdf, page 3): A sieve crosses out multiples.",
        "Sieves (other.pdf, page 1): Something else about sieves.",
        "Gaps (book.pdf, page 4): Primes thin out.",
        "(book.pdf, page 3): The sieve of Eratosthenes.",
    ]
    step = explained(teacher(found=found).step("Next", Lesson("Prime Numbers", 0)))
    assert step.teach.material == ["Sieves: A sieve crosses out multiples.", *found[1:]]


# --- Through the app ---


def chat(client: Any, prompt: str, lesson: dict[str, Any] | None = None) -> dict[str, Any]:
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        response = client.post("/api/chat", json={"prompt": prompt, "lesson": lesson})
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_with_teach_me_off_teach_me_is_an_ordinary_prompt(tmp_path: Path) -> None:
    """Off unless it is turned on in the settings (Larry, 2026-10-15)."""
    llm = Llm()
    client = riemann_app(tmp_path, llm)
    lesson = {"topic": "Zeta Function Integral", "part": 0, "active": True}
    reply = chat(client, "Teach me about Zeta Function Integral", lesson)
    assert reply["content"] == "Two moons." and reply["choices"] == []
    assert llm.sent[-1][-1]["content"].endswith("Teach me about Zeta Function Integral")
    assert "Teach me the main ideas" not in llm.sent[-1][-1]["content"]
    assert reply["lesson"] == {**lesson, "parts": 1}  # kept as it was, for when it is on again


def test_a_lesson_through_the_chat(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    llm = Llm()
    client = riemann_app(tmp_path, llm)
    assert client.patch("/api/settings", json={"teach_me": True}).status_code == 200
    reply = chat(client, "Teach me")
    assert reply["content"].startswith(CHOOSE)
    assert [c["label"] for c in reply["choices"]] == [
        "Prime Number Basics",
        "Zeta Function Integral",
        EVERYTHING,
    ]
    assert reply["lesson"] is None and llm.sent == []

    with caplog.at_level(logging.INFO, logger="imageskin.teach"):
        reply = chat(client, "Teach me about Zeta Function Integral")
    assert reply["content"] == "Two moons."
    lesson = reply["lesson"]
    assert lesson == {"topic": "Zeta Function Integral", "part": 0, "active": True, "parts": 1}
    asked = llm.sent[-1][-1]["content"]
    assert "Zeta Function Integral: The zeta function as an integral." in asked
    assert 'Teach me the main ideas of "Zeta Function Integral"' in asked
    logged = next(r for r in caplog.records if r.message == "Lesson part")
    assert (logged.topic, logged.kind) == ("Zeta Function Integral", "start")  # type: ignore[attr-defined]

    # A question partway is answered from the part, even with general prompts off.
    reply = chat(client, "Why?", lesson)
    assert reply["content"] == "Two moons." and reply["lesson"] == lesson
    assert "The zeta function as an integral." in llm.sent[-1][-1]["content"]

    reply = chat(client, "Next", lesson)
    assert reply["lesson"]["part"] == 1  # the summary
    assert "Sum up in one sentence" in llm.sent[-1][-1]["content"]
    reply = chat(client, "Next", reply["lesson"])
    assert reply["content"] == ALL_DONE and reply["lesson"] is None

    turns = client.get("/api/chat").json()["turns"]
    assert [t["content"] for t in turns if t["role"] == "user"] == [
        "Teach me",
        "Teach me about Zeta Function Integral",
        "Why?",
        "Next",
        "Next",
    ]


def test_a_lesson_sent_by_the_browser_is_checked(tmp_path: Path) -> None:
    client = riemann_app(tmp_path, Llm())
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        bad = client.post(
            "/api/chat", json={"prompt": "Next", "lesson": {"topic": "A", "part": -1}}
        )
    assert bad.status_code == 422


def test_a_teach_me_prompt_too_long_is_refused_like_any_other(tmp_path: Path) -> None:
    """Review on PR #87: "Teach me about <a huge unknown topic>" is answered here, not by the
    LLM, and is refused for its length all the same."""
    client = riemann_app(tmp_path, Llm())
    assert client.patch("/api/settings", json={"teach_me": True}).status_code == 200
    huge = " ".join(["zeta"] * 40000)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        lesson = client.post("/api/chat", json={"prompt": f"Teach me about {huge}"})
        ordinary = client.post("/api/chat", json={"prompt": f"Tell me about {huge}"})
    assert lesson.status_code == ordinary.status_code == 400
    assert lesson.json() == ordinary.json()
    assert "too long" in lesson.json()["detail"]
    assert client.get("/api/chat").json()["turns"] == []


def test_a_lesson_part_through_the_app_gives_its_wiki_entry_once(tmp_path: Path) -> None:
    llm = Llm()
    client = riemann_app(tmp_path, llm)
    assert client.patch("/api/settings", json={"teach_me": True}).status_code == 200
    chat(client, "Teach me about Zeta Function Integral")
    asked = llm.sent[-1][-1]["content"]
    assert asked.count("The zeta function as an integral.") == 1
    assert "The zeta function is given by an integral over x." in asked  # the PDF, still there


def test_a_lesson_cannot_finish_while_a_pdf_is_still_read(tmp_path: Path) -> None:
    """Review on PR #87: with one PDF ready and one still being built, the last topic so far
    is not the end; once the second is ready, Next carries on into it."""
    hold = threading.Event()
    llm = Llm()
    client = app_with_topics(tmp_path, llm, ["Rain"], "Rain falls.", pdfs=2, hold=hold)
    try:
        assert client.patch("/api/settings", json={"teach_me": True}).status_code == 200
        asked = chat(client, "Teach me")
        assert asked["content"].endswith(MORE_COMING)
        assert [c["label"] for c in asked["choices"]] == ["Rain", EVERYTHING_SO_FAR]
        lesson = chat(client, "Teach me about Rain")["lesson"]
        lesson = chat(client, "Next", lesson)["lesson"]  # the summary
        reply = chat(client, "Next", lesson)
        assert reply["content"] == NOT_YET and reply["lesson"] == lesson
    finally:
        hold.set()
    client.app.state.wiki.wait()
    reply = chat(client, "Next", lesson)
    assert reply["lesson"] == {"topic": "Rain 2", "part": 0, "active": True, "parts": 1}
    reply = chat(client, "Next", chat(client, "Next", reply["lesson"])["lesson"])
    assert reply["content"] == ALL_DONE


def test_teach_me_while_the_first_pdf_is_still_read(tmp_path: Path) -> None:
    hold = threading.Event()
    llm = Llm()
    client = app_with_topics(tmp_path, llm, ["Rain"], "Rain.", hold=hold, hold_first=True)
    try:
        assert client.patch("/api/settings", json={"teach_me": True}).status_code == 200
        reply = chat(client, "Teach me")
        assert (reply["content"], reply["choices"]) == (STILL_READING_LESSON, [])
    finally:
        hold.set()
    client.app.state.wiki.wait()
    assert [c["label"] for c in chat(client, "Teach me")["choices"]] == ["Rain", EVERYTHING]
    assert llm.sent == []
