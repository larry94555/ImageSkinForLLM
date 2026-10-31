"""Guidelines for the level of detail (roadmap R199)."""

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
    KEEP_TRACK,
    Conversation,
    detail_level,
    reply_tokens,
    system_message,
    system_prompt,
)
from imageskin.customization import (
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


def test_each_step_ships_with_the_text_it_was_asked_with_word_for_word() -> None:
    keys = [f["key"] for f in features(SHIPPED)]
    assert keys[7:] == [f"detail {step}" for step in range(1, 6)]
    assert FEATURES["detail 1"].label == "Level of detail: 1, High level"
    assert FEATURES["detail 5"].label == "Level of detail: 5, In depth"
    for step in DETAIL_LEVELS:
        assert guidelines_of(SHIPPED, detail_key(step)) == DETAIL_STEPS[step]
        assert system_prompt(step, DETAIL_STEPS[step]) == system_prompt(step)
    assert system_prompt(3, DETAIL_STEPS[3]) == BEFORE
    with detail_level(3, SHIPPED):
        assert BEFORE in system_message(None)["content"]


def test_edited_a_step_takes_the_place_of_its_text_and_keeps_its_room() -> None:
    edited = with_guidelines(SHIPPED, "detail 5", EXAMPLE)
    with detail_level(5, edited):
        instructions = system_message(None)["content"]
        assert reply_tokens() == DETAIL_LEVELS[5][1]
    assert f"{DETAIL_GUIDELINES} {EXAMPLE} Reply without lists," in instructions
    assert instructions.count(KEEP_TRACK) == 1
    assert DETAIL_STEPS[5].removesuffix(".") not in instructions
    with detail_level(1, edited):  # the other steps are as shipped
        assert system_prompt(1) in system_message(None)["content"]
        assert EXAMPLE not in system_message(None)["content"]


def test_each_reply_is_asked_with_the_step_as_it_is_then(
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
        now[0] = Read(with_guidelines(SHIPPED, "detail 5", EXAMPLE), False, 0.1)
        talk.send("Why is the sky blue?")
        level["now"] = 1
        talk.send("Why is the sky blue?")
    shipped, edited, high = (sent[0]["content"] for sent in llm.sent)
    assert system_prompt(5) in shipped and EXAMPLE not in shipped
    assert f"{DETAIL_GUIDELINES} {EXAMPLE}" in edited
    assert system_prompt(1) in high and EXAMPLE not in high
    assert llm.rooms == [DETAIL_LEVELS[5][1]] * 2 + [DETAIL_LEVELS[1][1]]
    used = [
        (r.step, r.edited)  # type: ignore[attr-defined]
        for r in caplog.records
        if r.message == "Guidelines used" and r.feature == "level of detail"  # type: ignore[attr-defined]
    ]
    assert used == [(5, False), (5, True), (1, False)]


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
    now = [Read(with_guidelines(SHIPPED, "detail 5", longest), False, 0.1)]
    llm = Recorder()
    talk = Conversation(llm, lambda: 8192, detail=lambda: 5, customization=lambda: now[0])
    for i in range(6):
        talk.send(f"Question {i} " + "x" * 200)
        talk.wait()
    assert all(longest.strip() in sent[0]["content"] for sent in llm.sent)
    assert set(llm.rooms) == {DETAIL_LEVELS[5][1]}


def test_the_host_edits_in_depth_and_high_level_is_unchanged(tmp_path: Path) -> None:
    llm = Llm()
    client: Any = riemann_app(tmp_path, llm)
    saved = client.put("/api/customization/guidelines/detail%205", json={"text": EXAMPLE})
    assert saved.status_code == 200 and saved.json()["features"][11]["edited"] is True
    assert client.patch("/api/settings", json={"detail": 5}).status_code == 200
    chat(client, "What is the zeta function?")
    assert f"{DETAIL_GUIDELINES} {EXAMPLE}" in llm.sent[-1][0]["content"]
    assert client.patch("/api/settings", json={"detail": 1}).status_code == 200
    chat(client, "What is the zeta function?")
    assert system_prompt(1) in llm.sent[-1][0]["content"]
    assert EXAMPLE not in llm.sent[-1][0]["content"]
    client.put("/api/customization/guidelines/detail%205", json={"text": None})
    assert client.patch("/api/settings", json={"detail": 5}).status_code == 200
    chat(client, "What is the zeta function?")
    assert system_prompt(5) in llm.sent[-1][0]["content"]
