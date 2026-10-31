"""Guidelines for the level of detail (roadmap R199): the lowest, moderate and highest detail, with
general guidelines for every step of the bar (Larry, PR #253)."""

import logging
from pathlib import Path
from typing import Any

import pytest
from test_detail import BEFORE, Recorder
from test_question_scope import Llm
from test_teach import chat
from test_topics import riemann_app

from imageskin.chat import (
    DETAIL_GUIDELINES,
    DETAIL_LEVELS,
    GENERAL_GUIDELINES,
    KEEP_TRACK,
    Conversation,
    asked_system_prompt,
    detail_level,
    reply_tokens,
    system_message,
    system_prompt,
)
from imageskin.customization import (
    DETAIL_GENERAL,
    DETAIL_STEPS,
    FEATURES,
    SHIPPED,
    Read,
    detail_key,
    features,
    guidelines_of,
    with_guidelines,
)

EXAMPLE = "Always include a worked example."
SHORT = "Answer in a few words."
DEFINE = "Define each term you use."
DETAIL = ["detail lowest", "detail moderate", "detail highest", "detail general"]


def edited(*pairs: tuple[str, str]) -> Any:
    customization = SHIPPED
    for key, text in pairs:
        customization = with_guidelines(customization, key, text)
    return customization


def asked_at(level: int, customization: Any) -> str:
    with detail_level(level, customization):
        return asked_system_prompt()


def test_three_inputs_and_general_ones_in_their_own_section() -> None:
    listed = features(SHIPPED)
    assert [f["key"] for f in listed][8:] == DETAIL
    assert [f["label"] for f in listed][8:] == [
        "Lowest detail",
        "Moderate detail",
        "Highest detail",
        "General guidelines",
    ]
    sections = {f["key"]: f["section"] for f in listed}
    assert {sections[k] for k in DETAIL} == {"Level of detail"}
    assert sections["assessment questions"] == sections["assessment judging"] == "Assessment"
    assert {sections[k] for k in ("questions", "topics", "teach me", "quiz judging")} == {
        "Guidelines"
    }
    # The bar's two High level steps share the lowest, its two In depth steps the highest.
    assert [detail_key(step) for step in range(1, 6)] == [
        "detail lowest",
        "detail lowest",
        "detail moderate",
        "detail highest",
        "detail highest",
    ]


def test_as_shipped_every_step_is_asked_word_for_word_as_before() -> None:
    assert guidelines_of(SHIPPED, "detail lowest") == DETAIL_STEPS[1]
    assert guidelines_of(SHIPPED, "detail moderate") == DETAIL_STEPS[3]
    assert guidelines_of(SHIPPED, "detail highest") == DETAIL_STEPS[5]
    assert FEATURES["detail general"].shipped == DETAIL_GENERAL
    for step in DETAIL_LEVELS:  # steps 2 and 4 keep their own text
        assert asked_at(step, SHIPPED) == system_prompt(step)
    assert asked_at(3, SHIPPED) == BEFORE
    with detail_level(3, SHIPPED):
        assert BEFORE in system_message(None)["content"]


def test_edited_a_side_takes_the_place_of_both_its_steps_and_keeps_their_room() -> None:
    now = edited(("detail highest", EXAMPLE), ("detail lowest", SHORT))
    for step, text in ((4, EXAMPLE), (5, EXAMPLE), (1, SHORT), (2, SHORT)):
        asked = asked_at(step, now)
        assert f"{DETAIL_GUIDELINES} {text} Reply without lists," in asked
        assert DETAIL_LEVELS[step][0] not in asked and asked.count(KEEP_TRACK) == 1
        with detail_level(step, now):
            assert reply_tokens() == DETAIL_LEVELS[step][1]
    assert asked_at(3, now) == BEFORE  # the middle is as shipped


def test_general_ones_are_added_at_every_step_only_once_edited() -> None:
    now = edited(("detail general", DEFINE))
    for step in DETAIL_LEVELS:
        asked = asked_at(step, now)
        assert asked.startswith(system_prompt(step).removesuffix(KEEP_TRACK))
        assert asked.endswith(f"{GENERAL_GUIDELINES} {DEFINE}{KEEP_TRACK}")
    both = asked_at(5, edited(("detail general", DEFINE), ("detail highest", EXAMPLE)))
    assert f"{EXAMPLE} Reply without lists," in both and both.index(EXAMPLE) < both.index(DEFINE)
    # Emptied, they add nothing.
    assert asked_at(3, edited(("detail general", ""))) == BEFORE


def test_each_reply_is_asked_with_them_as_they_are_then(
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm = Recorder()
    level = {"now": 5}
    now = [Read(SHIPPED, True, 0.1)]
    talk = Conversation(
        llm, lambda: 4096, detail=lambda: level["now"], customization=lambda: now[0]
    )
    with caplog.at_level(logging.INFO, logger="imageskin.chat"):
        talk.send("Why is the sky blue?")
        now[0] = Read(edited(("detail highest", EXAMPLE), ("detail general", DEFINE)), False, 0.1)
        talk.send("Why is the sky blue?")
        level["now"] = 1
        talk.send("Why is the sky blue?")
    shipped, edit, high = (sent[0]["content"] for sent in llm.sent)
    assert system_prompt(5) in shipped and EXAMPLE not in shipped
    assert f"{DETAIL_GUIDELINES} {EXAMPLE}" in edit and DEFINE in edit
    assert DETAIL_LEVELS[1][0] in high and EXAMPLE not in high and DEFINE in high
    assert llm.rooms == [DETAIL_LEVELS[5][1]] * 2 + [DETAIL_LEVELS[1][1]]
    used = [
        (r.step, r.guidelines, r.edited, r.general_edited)  # type: ignore[attr-defined]
        for r in caplog.records
        if r.message == "Guidelines used" and r.feature == "level of detail"  # type: ignore[attr-defined]
    ]
    assert used == [
        (5, "highest", False, False),
        (5, "highest", True, True),
        (1, "lowest", False, True),
    ]


def test_unreadable_guidelines_ask_as_shipped(caplog: pytest.LogCaptureFixture) -> None:
    def broken() -> Read:
        raise OSError("disk gone")

    llm = Recorder()
    talk = Conversation(llm, lambda: 4096, detail=lambda: 5, customization=broken)
    with caplog.at_level(logging.ERROR, logger="imageskin.chat"):
        talk.send("Why is the sky blue?")
    assert llm.sent[0][0]["content"].startswith(system_prompt(5))
    assert "Could not read the identity" in caplog.text


def test_long_edited_guidelines_take_their_room_from_the_history() -> None:
    """The instructions are counted before the history is fitted, so guidelines near their
    longest leave less room for earlier turns, never for the reply."""
    longest = "Always include a worked example, step by step. " * 40  # about 1,900
    now = [Read(edited(("detail highest", longest), ("detail general", longest)), False, 0.1)]
    llm = Recorder()
    talk = Conversation(llm, lambda: 16384, detail=lambda: 5, customization=lambda: now[0])
    for i in range(6):
        talk.send(f"Question {i} " + "x" * 200)
        talk.wait()
    assert all(sent[0]["content"].count(longest.strip()) == 2 for sent in llm.sent)
    assert set(llm.rooms) == {DETAIL_LEVELS[5][1]}


def test_the_host_edits_highest_detail_and_high_level_is_unchanged(tmp_path: Path) -> None:
    llm = Llm()
    client: Any = riemann_app(tmp_path, llm)
    saved = client.put("/api/customization/guidelines/detail%20highest", json={"text": EXAMPLE})
    assert saved.status_code == 200
    shown = {f["key"]: f for f in saved.json()["features"]}
    assert shown["detail highest"]["edited"] is True
    assert shown["detail highest"]["section"] == "Level of detail"
    assert client.patch("/api/settings", json={"detail": 5}).status_code == 200
    chat(client, "What is the zeta function?")
    assert f"{DETAIL_GUIDELINES} {EXAMPLE}" in llm.sent[-1][0]["content"]
    assert client.patch("/api/settings", json={"detail": 1}).status_code == 200
    chat(client, "What is the zeta function?")
    assert system_prompt(1).removesuffix(KEEP_TRACK) in llm.sent[-1][0]["content"]
    assert EXAMPLE not in llm.sent[-1][0]["content"]
    client.put("/api/customization/guidelines/detail%20highest", json={"text": None})
    assert client.patch("/api/settings", json={"detail": 5}).status_code == 200
    chat(client, "What is the zeta function?")
    assert system_prompt(5) in llm.sent[-1][0]["content"]
