"""Say it simpler: the latest reply said again in simpler terms (roadmap R157)."""

import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from test_reply_video import REPLY_ID, stop_patches, video_app  # noqa: F401 (a fixture)

from imageskin.chat import LlmCancelled, LlmError, Teach, Turn, ask_stop
from imageskin.review import Review
from imageskin.simpler import INSTRUCTION, SimplerCheck, say_simpler

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


def written_clip(photo: Path, text: str, output: Path) -> None:
    output.write_text(text)


def test_say_it_simpler_asks_the_llm_to_restate_the_latest_reply(tmp_path: Path) -> None:
    asked: list[list[dict[str, str]]] = []

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        asked.append(messages)
        yield "Small drops join. " if len(asked) > 1 else "Condensation nucleates droplets."

    client = video_app(tmp_path, written_clip, stream)
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


def test_a_simpler_version_that_says_something_new_is_offered_and_kept(
    caplog: pytest.LogCaptureFixture,
) -> None:
    asked: list[Teach] = []

    def write(teach: Teach) -> str:
        asked.append(teach)
        return "Small drops join. Then they fall."

    check = SimplerCheck(write)
    with caplog.at_level(logging.INFO, logger="imageskin.simpler"):
        assert check.check(TURNS)
        assert check.check(TURNS)  # kept: not written again
    assert asked == [Teach(INSTRUCTION, ["Condensation nucleates droplets."])]
    assert check.ready(TURNS) == ["Small drops join.", "Then they fall."]
    logged = next(r for r in caplog.records if r.message == "Simpler reply checked")
    assert logged.simpler is True  # type: ignore[attr-defined]
    assert logged.duration_ms >= 0  # type: ignore[attr-defined]
    # Another reply is checked anew, and the one before isn't said for it.
    later = [*TURNS, Turn("user", "Why snow?"), Turn("assistant", "Ice crystals grow.")]
    assert check.ready(later) is None
    assert check.check(later) and len(asked) == 2


@pytest.mark.parametrize(
    "written",
    [
        "condensation NUCLEATES droplets",  # the reply again, in other case and punctuation
        "Rain falls.",  # an earlier reply
        "  ",
    ],
)
def test_a_simpler_version_that_says_nothing_new_is_not_offered(written: str) -> None:
    turns = [Turn("assistant", "Rain falls."), *TURNS]
    check = SimplerCheck(lambda teach: written)
    assert not check.check(turns)
    assert check.ready(turns) is None


def test_no_reply_has_nothing_to_simplify() -> None:
    check = SimplerCheck(lambda teach: pytest.fail("not asked"))
    assert not check.check(TURNS[:1])
    assert check.ready(TURNS[:1]) is None


def test_a_check_that_fails_is_not_kept(caplog: pytest.LogCaptureFixture) -> None:
    answers: list[str | Exception] = [LlmError("down"), "Small drops join."]

    def write(teach: Teach) -> str:
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    check = SimplerCheck(write)
    with caplog.at_level(logging.INFO, logger="imageskin.simpler"):
        assert not check.check(TURNS)
    failed = next(r for r in caplog.records if r.message == "Could not check for a simpler reply")
    assert failed.levelno == logging.ERROR and failed.error == "down"  # type: ignore[attr-defined]
    assert check.check(TURNS)  # asked again


def test_a_new_prompt_cuts_the_check_off(caplog: pytest.LogCaptureFixture) -> None:
    check: SimplerCheck

    def write(teach: Teach) -> str:
        stop = ask_stop.get()
        assert stop is not None and not stop.is_set()
        check.forget()  # a prompt comes in while it is written
        assert stop.is_set()
        raise LlmCancelled("cut off")

    check = SimplerCheck(write)
    with caplog.at_level(logging.INFO, logger="imageskin.simpler"):
        assert not check.check(TURNS)
    assert any(r.message == "Simpler reply check cut off" for r in caplog.records)
    assert check.ready(TURNS) is None
    assert ask_stop.get() is None


def test_say_it_simpler_says_the_version_checked_ahead(tmp_path: Path) -> None:
    streamed: list[list[dict[str, str]]] = []
    written: list[str] = ["Small drops join.", "Small drops join!"]

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        streamed.append(messages)
        yield "Condensation nucleates droplets."

    def ask(messages: list[dict[str, str]]) -> str:
        return written.pop(0) if INSTRUCTION in messages[-1]["content"] else "Summary."

    client = video_app(tmp_path, written_clip, stream, ask_llm=ask)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Why rain?", "reply_id": REPLY_ID})
        assert client.post("/api/chat/simpler").json() == {"simpler": True}
        sent = client.post("/api/chat", json={"prompt": "Say it simpler", "reply_id": "a" * 32})
        assert sent.status_code == 200 and sent.json()["content"] == "Small drops join."
        assert len(streamed) == 1  # said from the check, with no second request
        # Its own simpler version is itself again: Say it simpler is no longer offered.
        assert client.post("/api/chat/simpler").json() == {"simpler": False}
