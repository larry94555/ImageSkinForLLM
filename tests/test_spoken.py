"""Spoken questions heard in context (roadmap R24, Larry's test on PR #91)."""

import logging
import threading
from pathlib import Path
from typing import Any

import pytest
from test_question_scope import Llm
from test_quiz import chat
from test_teach import entry
from test_topics import riemann_app

from imageskin.chat import SUMMARY_PROMPT, LlmError, Message
from imageskin.spoken import MOST_WORDS, corrected, kept, vocabulary

CONTENTS = [
    {
        "entries": [
            entry(
                "Euler's Product",
                "Euler multiplied over the primes. Riemann later extended it. The sum grows.",
                entry("Zeta Function", "Riemann's zeta function. This is what Euler found."),
            )
        ]
    }
]
TERMS = vocabulary(CONTENTS)


def test_the_content_s_words_are_its_titles_and_capitalised_words_most_used_first() -> None:
    assert TERMS[:2] == ["Euler", "Riemann"]  # "Euler's" and "Riemann's" counted with them
    assert {"Product", "Zeta", "Function"} <= set(TERMS)
    assert not {"This", "The", "multiplied"} & set(TERMS)  # sentence starts and plain words
    many = [{"entries": [entry(f"Word{n:03d}", "") for n in range(MOST_WORDS + 5)]}]
    assert len(vocabulary(many)) == MOST_WORDS


@pytest.mark.parametrize(
    ("heard", "said", "keep"),
    [
        ("What did Oiler multiply over?", "What did Euler multiply over?", True),
        ("Tell me about the boiler product", "Tell me about the Euler product", True),
        ("What is the zeta fun shun?", "What is the zeta function?", True),  # two words, one term
        ("What is a prime?", "What is a prime?", False),  # nothing changed
        ("What did Oiler do?", "What did the mathematician do?", False),  # not the content's
        ("What did Oiler do?", "Euler?", False),  # dropped more than it put back
        # Larry's "boiler", put back as a content word that sounds nothing like it
        ("Tell me about the boiler product", "Tell me about the function product", False),
        # Review on PR #91: the words left as heard must keep their places.
        ("Did Oiler accuse Riemann?", "Did Riemann accuse Euler?", False),
        ("Did Oiler accuse Riemann?", "Did Euler accuse Riemann?", True),
        ("What did Oiler do?", "What did Euler do do?", False),  # a word added, none dropped
    ],
)
def test_a_change_is_kept_only_when_it_puts_the_content_s_words_back(
    heard: str, said: str, keep: bool
) -> None:
    assert kept(heard, said, TERMS) is keep


def test_larrys_oiler_is_taken_as_euler(caplog: pytest.LogCaptureFixture) -> None:
    """Larry (2026-10-15): "Euler" was heard as "Oiler" or "Boiler", and taken as off topic."""
    asked: list[tuple[str, list[str]]] = []

    def write(instruction: str, material: list[str]) -> str:
        asked.append((instruction, material))
        return '"What did Euler multiply over?"'

    with caplog.at_level(logging.INFO, logger="imageskin.spoken"):
        meant = corrected("What did Oiler multiply over?", TERMS, write)
    assert meant == "What did Euler multiply over?"
    instruction, material = asked[0]
    assert '"What did Oiler multiply over?"' in instruction
    assert "Euler" in material[0] and "Riemann" in material[0]
    record = next(r for r in caplog.records if r.message == "Spoken question corrected")
    assert record.heard == "What did Oiler multiply over?"  # type: ignore[attr-defined]


def test_a_rewritten_question_is_not_taken(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="imageskin.spoken"):
        heard = corrected("What did Oiler do?", TERMS, lambda i, m: "Who was a mathematician?")
    assert heard == "What did Oiler do?"
    assert "Spoken question kept" in caplog.text


def test_with_no_content_or_no_llm_it_is_taken_as_heard(caplog: pytest.LogCaptureFixture) -> None:
    def down(instruction: str, material: list[str]) -> str:
        raise LlmError("The LLM is not running.")

    assert corrected("What did Oiler do?", [], down) == "What did Oiler do?"
    with caplog.at_level(logging.INFO, logger="imageskin.spoken"):
        assert corrected("What did Oiler do?", TERMS, down) == "What did Oiler do?"
    assert "Could not check a spoken question" in caplog.text


class Hearing(Llm):
    """Puts "Prime" back for "Crime" when asked about a spoken question; answers otherwise."""

    def __call__(self, messages: list[Message]) -> str:
        self.sent.append(messages)
        if "speech recognition wrote it down" in messages[-1]["content"]:
            return "What are Prime Number Basics?"
        return "Two moons."


def test_a_spoken_prompt_is_answered_and_shown_as_meant(tmp_path: Path) -> None:
    llm = Hearing()
    client = riemann_app(tmp_path, llm)
    reply = chat(client, "What are Crime Number Basics?", spoken=True)
    assert reply["prompt"] == "What are Prime Number Basics?"
    assert reply["content"] == "Two moons."
    turns: list[dict[str, Any]] = client.get("/api/chat").json()["turns"]
    assert turns[-2] == {"role": "user", "content": "What are Prime Number Basics?"}


def test_a_typed_prompt_is_not_checked(tmp_path: Path) -> None:
    llm = Hearing()
    client = riemann_app(tmp_path, llm)
    reply = chat(client, "What are Crime Number Basics?")
    assert "prompt" not in reply
    assert not any("speech recognition" in m[-1]["content"] for m in llm.sent)


def test_a_spoken_prompt_waits_for_the_summary_before_it_is_corrected(tmp_path: Path) -> None:
    """Review on PR #91: the correction asked the LLM while the summary was still being made."""
    release = threading.Event()
    asked: list[str] = []

    class Slow(Hearing):
        def __call__(self, messages: list[Message]) -> str:
            if messages[0]["content"] == SUMMARY_PROMPT:
                asked.append("summary")
                assert release.wait(5)
                return "SUMMARY"
            if "speech recognition wrote it down" in messages[-1]["content"]:
                asked.append("correction")
            return super().__call__(messages)

    client = riemann_app(tmp_path, Slow())
    for _ in range(20):  # until a reply starts a summary
        chat(client, "How are primes counted? " + "primes counted " * 40)
        if asked:
            break
    assert asked == ["summary"]  # being made
    spoken = threading.Thread(
        target=chat, args=(client, "What are Crime Number Basics?"), kwargs={"spoken": True}
    )
    spoken.start()
    spoken.join(0.3)
    assert asked == ["summary"]  # the correction waits
    release.set()
    spoken.join(5)
    assert asked == ["summary", "correction"]
