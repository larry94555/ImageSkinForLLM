"""Guidelines for Say it simpler (roadmap R200)."""

import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from test_question_scope import Llm
from test_teach import CONTENTS, chat, explained
from test_topics import riemann_app

from imageskin.chat import Conversation, Turn
from imageskin.customization import FEATURES, SHIPPED, SIMPLER, TEACHING, features
from imageskin.simpler import INSTRUCTION, instruction, say_simpler
from imageskin.teach import SIMPLER_GUIDELINES, Part, Tutor, explain

TWELVE = "Explain it as you would to a 12-year-old."
GUIDED = f"{SIMPLER_GUIDELINES} {TWELVE}"
PARTS = [Part("Primes", "No divisors."), Part("Sieves", "Cross out multiples.")]
TURNS = [Turn("user", "Why rain?"), Turn("assistant", "Condensation nucleates droplets.")]


def test_they_ship_as_both_were_asked_before_word_for_word() -> None:
    listed = features(SHIPPED)
    keys = [f["key"] for f in listed]
    assert keys[7] == "say it simpler" and listed[7]["section"] == "Guidelines"
    assert FEATURES["say it simpler"].shipped == SIMPLER
    before = (
        "Say your last answer again in simpler terms, for someone new to the subject: in short"
        " sentences with everyday words, saying the same thing and adding nothing new. Don't"
        " ask me anything."
    )
    assert instruction() == instruction(SIMPLER) == INSTRUCTION == before
    assert explain("Primes", PARTS, 1, simpler=True) == (
        'Explain "Sieves", part of "Primes" again, more simply: in two or three short sentences,'
        " with everyday words and an everyday example. Don't ask me anything."
    )


def test_edited_they_take_the_place_of_how_to_say_it_more_simply() -> None:
    assert instruction(TWELVE) == f"Say your last answer again, more simply. {GUIDED}"
    edited = explain("Primes", PARTS, 1, simpler=True, simpler_guidelines=TWELVE)
    assert edited == f'Explain "Sieves", part of "Primes" again, more simply. {GUIDED}'
    # Teach me's guidelines don't change saying a part more simply, and these don't change a part.
    assert "Teach" not in explain("Primes", PARTS, 1, True, "Use analogies.")
    assert TWELVE not in explain("Primes", PARTS, 1, simpler_guidelines=TWELVE)


def test_a_simpler_reply_is_asked_with_them_as_they_are_then(
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = [SIMPLER]
    with caplog.at_level(logging.INFO, logger="imageskin.teach"):
        shipped = say_simpler("Say it simpler", TURNS, lambda: now[0])
        now[0] = TWELVE
        edited = say_simpler("say that more simply please", TURNS, lambda: now[0])
    assert shipped is not None and edited is not None
    assert shipped.instruction == INSTRUCTION and shipped.unguided is None
    assert edited.instruction == instruction(TWELVE) and edited.unguided == INSTRUCTION
    assert edited.material == ["Condensation nucleates droplets."]
    assert edited.feature == "say it simpler"
    used = [
        (r.feature, r.edited)  # type: ignore[attr-defined]
        for r in caplog.records
        if r.message == "Guidelines used"
    ]
    assert used == [("say it simpler", False), ("say it simpler", True)]
    assert say_simpler("Why snow?", TURNS, lambda: now[0]) is None


def test_a_lesson_part_said_more_simply_is_asked_with_them(
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = [SIMPLER]
    t = Tutor(lambda: CONTENTS, lambda q: [], guidelines=lambda: TEACHING, simpler=lambda: now[0])
    first = explained(t.step("Teach me about Prime Numbers", None))
    shipped = explained(t.step("Say it more simply", first.lesson))
    now[0] = TWELVE
    caplog.clear()  # of the parts before, which a logger set to INFO elsewhere keeps
    with caplog.at_level(logging.INFO, logger="imageskin.teach"):
        edited = explained(t.step("Say it more simply", first.lesson))
    assert shipped.teach.unguided is None and GUIDED not in shipped.teach.instruction
    assert edited.teach.instruction.endswith(f"again, more simply. {GUIDED}")
    assert edited.teach.unguided == shipped.teach.instruction
    assert edited.teach.feature == "say it simpler" and edited.lesson == first.lesson
    assert edited.teach.material == shipped.teach.material
    used = [r for r in caplog.records if r.message == "Guidelines used"]
    assert [(r.feature, r.edited) for r in used] == [("say it simpler", True)]  # type: ignore[attr-defined]


def test_unreadable_guidelines_say_it_simpler_as_shipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken() -> str:
        raise OSError("disk gone")

    t = Tutor(lambda: CONTENTS, lambda q: [], simpler=broken)
    with caplog.at_level(logging.ERROR, logger="imageskin.teach"):
        teach = say_simpler("Say it simpler", TURNS, broken)
        first = explained(t.step("Teach me about Rain", None))
        part = explained(t.step("Say it more simply", first.lesson))
    assert teach is not None and teach.instruction == INSTRUCTION
    assert part.teach.instruction == explain("Rain", [Part("Rain", "It falls.")], 0, True)
    assert caplog.text.count("Could not read the Say it simpler guidelines") == 2


def test_guidelines_that_dont_fit_are_left_out(caplog: pytest.LogCaptureFixture) -> None:
    """As for the other guidelines: a simpler reply asked for with guidelines near their longest
    is asked as shipped when they don't fit the room left for it."""
    longest = "Explain it as you would to a 12-year-old. " * 45  # about 1,900 characters
    teach = say_simpler("Say it simpler", TURNS, lambda: longest.strip())
    assert teach is not None
    teach = replace(teach, material=[])

    def fits(window: int) -> bool:
        try:
            Conversation(Llm(), lambda: window)._fit(INSTRUCTION)
        except ValueError:
            return False
        return True

    window = next(w for w in range(256, 8192, 8) if fits(w))
    llm = Llm()
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="imageskin.chat"):
        Conversation(llm, lambda: window).send("Say it simpler", teach=teach)
    assert llm.sent[0][-1]["content"] == INSTRUCTION
    warned = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert [(r.message, r.feature) for r in warned] == [  # type: ignore[attr-defined]
        ("Guidelines left out", "say it simpler"),
    ]
    roomy = Llm()
    Conversation(roomy, lambda: 4 * window).send("Say it simpler", teach=teach)
    assert roomy.sent[0][-1]["content"] == teach.instruction


def test_the_host_edits_them_and_the_next_simpler_reply_uses_them(tmp_path: Path) -> None:
    llm = Llm()
    client: Any = riemann_app(tmp_path, llm)
    saved = client.put("/api/customization/guidelines/say%20it%20simpler", json={"text": TWELVE})
    assert saved.status_code == 200
    shown = {f["key"]: f for f in saved.json()["features"]}["say it simpler"]
    assert shown["edited"] is True and shown["section"] == "Guidelines"
    chat(client, "What is the zeta function?")
    chat(client, "Say it simpler")
    assert GUIDED in llm.sent[-1][-1]["content"]
    client.put("/api/customization/guidelines/say%20it%20simpler", json={"text": None})
    chat(client, "Say it simpler")
    last = llm.sent[-1][-1]["content"]
    assert INSTRUCTION in last and TWELVE not in last  # said again, with the length after it
