"""Say it simpler: the latest reply said again in simpler terms (roadmap R157)."""

import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from test_reply_video import REPLY_ID, stop_patches, video_app  # noqa: F401 (a fixture)

from imageskin.chat import Turn
from imageskin.review import Review
from imageskin.simpler import INSTRUCTION, say_simpler

TURNS = [Turn("user", "Why rain?"), Turn("assistant", "Condensation nucleates droplets.")]


def test_only_a_prompt_asking_for_it_simpler_after_a_reply_is_restated(
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert say_simpler("Why does snow fall?", TURNS) is None
    assert say_simpler("Say it simpler", TURNS[:1]) is None  # no reply yet
    with caplog.at_level(logging.INFO, logger="imageskin.simpler"):
        for prompt in ("Say it simpler", "say that more simply please", "I don't get it"):
            teach = say_simpler(prompt, TURNS)
            assert teach is not None
            assert teach.instruction == INSTRUCTION
            assert teach.material == ["Condensation nucleates droplets."]
    logged = next(r for r in caplog.records if r.message == "Simpler reply asked")
    assert logged.reply_chars == len(TURNS[1].content)  # type: ignore[attr-defined]


def written(photo: Path, text: str, output: Path) -> None:
    output.write_text(text)


def test_say_it_simpler_asks_the_llm_to_restate_the_latest_reply(tmp_path: Path) -> None:
    asked: list[list[dict[str, str]]] = []

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        asked.append(messages)
        yield "Small drops join. " if len(asked) > 1 else "Condensation nucleates droplets."

    client = video_app(tmp_path, written, stream)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Why rain?", "reply_id": REPLY_ID})
        sent = client.post("/api/chat", json={"prompt": "Say it simpler", "reply_id": "a" * 32})
        assert sent.status_code == 200 and sent.json()["content"] == "Small drops join."
        turns = [t["content"] for t in client.get("/api/chat").json()["turns"]]
    last = asked[-1][-1]["content"]
    assert INSTRUCTION in last and "Condensation nucleates droplets." in last
    # The conversation so far is sent too, and keeps the prompt as it was asked.
    assert [m["content"] for m in asked[-1][-3:-1]] == [
        "Why rain?",
        "Condensation nucleates droplets.",
    ]
    assert turns == [
        "Why rain?",
        "Condensation nucleates droplets.",
        "Say it simpler",
        "Small drops join.",
    ]
