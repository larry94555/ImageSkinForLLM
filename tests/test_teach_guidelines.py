"""Guidelines for Teach me (roadmap R196)."""

import logging
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from test_question_scope import Llm
from test_teach import CONTENTS, chat, explained
from test_topics import riemann_app

from imageskin.customization import FEATURES, SHIPPED, TEACHING, features, guidelines_of
from imageskin.lessons_ahead import key
from imageskin.teach import TEACH_GUIDELINES, Lesson, Part, Tutor, explain

EDITED = "Use one everyday analogy in each part."
GUIDED = f"{TEACH_GUIDELINES} {EDITED}"
PARTS = [Part("Primes", "No divisors."), Part("Sieves", "Cross out multiples.")]


def test_they_ship_as_how_each_part_was_asked_for_before_word_for_word() -> None:
    assert FEATURES["teach me"].shipped == TEACHING == guidelines_of(SHIPPED, "teach me")
    assert [f["key"] for f in features(SHIPPED)] == ["questions", "topics", "teach me"]
    assert explain("Primes", PARTS, 0) == (
        'Teach me the main ideas of "Primes", as a tutor talking to someone new to it, in two to'
        " four short sentences. Don't ask me anything."
    )
    assert explain("Primes", PARTS, 2) == (
        'Sum up in one sentence what we have just learned about "Primes". Say only that sentence.'
    )


def test_edited_they_take_the_place_of_how_to_teach_in_every_part() -> None:
    main, entry, summary = (explain("Primes", PARTS, p, guidelines=EDITED) for p in (0, 1, 2))
    assert main == f'Teach me the main ideas of "Primes". {GUIDED}'
    assert entry == f'Teach me "Sieves", part of "Primes". {GUIDED}'
    # The summary stays one line, as the code makes it.
    assert summary.startswith("Sum up in one sentence") and summary.endswith(GUIDED)
    # Saying it more simply has its own guidelines (R200).
    assert EDITED not in explain("Primes", PARTS, 1, simpler=True, guidelines=EDITED)


def tutor_with(now: list[str]) -> Tutor:
    return Tutor(lambda: CONTENTS, lambda q: [], guidelines=lambda: now[0])


def test_each_part_is_asked_with_the_guidelines_as_they_are_then(
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = [TEACHING]
    t = tutor_with(now)
    with caplog.at_level(logging.INFO, logger="imageskin.teach"):
        first = explained(t.step("Teach me about Prime Numbers", None))
        now[0] = EDITED
        second = explained(t.step("Next", first.lesson))
        simpler = explained(t.step("Say it more simply", second.lesson))
        question = explained(t.step("Why?", second.lesson))
    assert GUIDED not in first.teach.instruction
    assert second.teach.instruction.endswith(GUIDED)
    assert GUIDED not in simpler.teach.instruction and question.teach.instruction == "Why?"
    used = [
        (r.feature, r.edited)  # type: ignore[attr-defined]
        for r in caplog.records
        if r.message == "Guidelines used"
    ]
    assert used == [("teach me", False), ("teach me", True)]


def test_parts_written_ahead_are_written_again_once_they_change() -> None:
    now = [TEACHING]
    t = tutor_with(now)
    shipped = t.first_parts()
    now[0] = EDITED
    edited = t.first_parts()
    assert all(GUIDED in teach.instruction for teach in edited.values())
    # A part written ahead is said only while its key is the same (R98a).
    assert all(key(shipped[topic]) != key(edited[topic]) for topic in shipped)


def test_unreadable_guidelines_teach_as_shipped(caplog: pytest.LogCaptureFixture) -> None:
    def broken() -> str:
        raise OSError("disk gone")

    t = Tutor(lambda: CONTENTS, lambda q: [], guidelines=broken)
    with caplog.at_level(logging.ERROR, logger="imageskin.teach"):
        step = explained(t.step("Teach me about Rain", None))
    assert step.teach.instruction == explain("Rain", [Part("Rain", "It falls.")], 0)
    assert "Could not read the Teach me guidelines" in caplog.text
    assert step.lesson == Lesson("Rain", 0)
    assert GUIDED not in t.first_parts()["Rain"].instruction


def test_the_host_edits_them_and_the_next_lesson_part_is_taught_with_them(
    tmp_path: Path,
) -> None:
    llm = Llm()
    client: Any = riemann_app(tmp_path, llm, lessons_ahead=False)
    assert client.patch("/api/settings", json={"teach_me": True}).status_code == 200
    saved = client.put("/api/customization/guidelines/teach%20me", json={"text": EDITED})
    assert saved.status_code == 200 and saved.json()["features"][2]["edited"] is True
    reply = chat(client, "Teach me about Zeta Function Integral")
    assert llm.sent[-1][-1]["content"].endswith(f'"Zeta Function Integral". {GUIDED}')
    chat(client, "Next", reply["lesson"])
    assert llm.sent[-1][-1]["content"].endswith(GUIDED)  # the summary
    client.put("/api/customization/guidelines/teach%20me", json={"text": None})
    chat(client, "Teach me about Zeta Function Integral")
    assert "as a tutor talking to someone new to it" in llm.sent[-1][-1]["content"]
    assert GUIDED not in llm.sent[-1][-1]["content"]


def test_saving_them_writes_the_parts_ahead_again(tmp_path: Path) -> None:
    client: Any = riemann_app(tmp_path, Llm(), lessons_ahead=True)
    lessons = client.app.state.lessons
    with patch.object(lessons, "refresh") as refresh:
        client.put("/api/customization/guidelines/topics", json={"text": "Be brief."})
        assert refresh.call_count == 0  # only Teach me's are in the parts written ahead
        client.put("/api/customization/guidelines/teach%20me", json={"text": EDITED})
    assert refresh.call_count == 1
