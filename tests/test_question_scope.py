import io
import logging
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from imageskin.app import create_app
from imageskin.chat import OFF_TOPIC, Conversation, Message, Turn
from imageskin.pdf_reading import Piece, Progress, Reading
from imageskin.review import Review
from imageskin.uploads import PhotoResult
from imageskin.wiki import Progress as WikiProgress
from imageskin.wiki import Wiki, WikiPage

PDF = b"%PDF-1.7\n" + b"x" * 100 + b"\n%%EOF\n"
MARS = ["Moons (a.pdf, page 3): Mars has two moons."]


class Llm:
    def __init__(self) -> None:
        self.sent: list[list[Message]] = []

    def __call__(self, messages: list[Message]) -> str:
        self.sent.append(messages)
        return "Two moons."


def find(prompt: str) -> list[str]:
    return MARS if "Mars" in prompt else []


def test_an_off_topic_prompt_is_declined_without_asking_the_llm(
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm = Llm()
    conversation = Conversation(llm, lambda: 4096, find=find, content_only=lambda: True)
    with caplog.at_level(logging.INFO):
        assert conversation.send("Tell me a joke.") == (Turn("assistant", OFF_TOPIC), 1)
        assert conversation.send("How many moons has Mars?")[1] == 3

    assert len(llm.sent) == 1 and "Mars has two moons." in llm.sent[0][-1]["content"]
    assert len(llm.sent[0]) == 2  # the declined prompt isn't sent to the LLM later
    assert [t.content for t in conversation.turns()] == [
        "Tell me a joke.",
        OFF_TOPIC,
        "How many moons has Mars?",
        "Two moons.",
    ]
    assert "Prompt declined: general prompts are off" in caplog.text


def test_an_off_topic_prompt_is_answered_when_general_prompts_are_allowed() -> None:
    llm = Llm()
    conversation = Conversation(llm, lambda: 4096, find=find, content_only=lambda: False)
    assert conversation.send("Tell me a joke.")[0].content == "Two moons."
    assert llm.sent[0][-1]["content"] == "Tell me a joke."


def test_a_failed_lookup_is_answered_not_declined() -> None:
    def broken(prompt: str) -> list[str]:
        raise OSError("disk gone")

    llm = Llm()
    Conversation(llm, lambda: 4096, find=broken, content_only=lambda: True).send("Hello?")
    assert llm.sent[0][-1]["content"] == "Hello?"


def test_the_decline_is_spoken_like_a_streamed_reply() -> None:
    def stream(messages: list[Message]) -> Any:
        raise AssertionError("the LLM isn't asked")

    said: list[str | None] = []
    conversation = Conversation(
        Llm(), lambda: 4096, stream=stream, find=find, content_only=lambda: True
    )
    conversation.send("Tell me a joke.", said.append)
    assert said == [
        None,
        "Sorry, I can only answer questions about the material I was given.",
        "Try asking about something in it.",
    ]


def app_with_content(tmp_path: Path, llm: Llm, general_prompts: bool, add_pdf: bool) -> TestClient:
    def lesson(path: Path, progress: Progress) -> Reading:
        return Reading("text", 1, [Piece(1, "paragraph", "Phobos and Deimos circle Mars.")], [])

    def topics(pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress, w: Any) -> Wiki:
        return Wiki(1, [WikiPage(f"{pdf_id}-moons", "Moons of Mars", "Mars has two moons.", [1])])

    app = create_app(
        tmp_path,
        check_photo=lambda p: PhotoResult([], 80),
        prepare_voice=lambda: None,
        prepare_face=lambda photo, progress: None,
        render_clip=lambda photo, text, output: None,
        ask_llm=llm,
        read_pdf=lesson,
        build_wiki=topics,
        general_prompts=general_prompts,
    )
    client = TestClient(app)
    client.post("/api/consent", json={"agreed": True})
    if add_pdf:
        client.post("/api/content", files={"file": ("space.pdf", io.BytesIO(PDF))})
        app.state.readings.wait()
        app.state.wiki.wait()
    return client


@pytest.mark.parametrize(
    ("general_prompts", "add_pdf", "answer"),
    [
        # the default: declined, naming the topic it can answer instead (R41f)
        (
            False,
            True,
            "Sorry, I can only answer questions about the material I was given."
            " You could ask me about Moons of Mars.",
        ),
        (True, True, "Two moons."),  # allowed: answered
        (False, False, "Two moons."),  # no PDFs yet: nothing to keep to, so answered
    ],
)
def test_the_chat_keeps_to_the_content_unless_general_prompts_are_allowed(
    tmp_path: Path, general_prompts: bool, add_pdf: bool, answer: str
) -> None:
    llm = Llm()
    client = app_with_content(tmp_path, llm, general_prompts, add_pdf)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        off_topic = client.post("/api/chat", json={"prompt": "What is the capital of Peru?"})
        on_topic = client.post("/api/chat", json={"prompt": "Which moons circle Mars?"})
    assert off_topic.status_code == 200 and off_topic.json()["content"] == answer
    assert on_topic.json()["content"] == "Two moons."


def test_the_question_scope_changed_on_the_settings_page_holds_from_the_next_prompt(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # R27: the config file's setting is only the default; the Settings page changes it at once.
    llm = Llm()
    with caplog.at_level(logging.INFO):
        client = app_with_content(tmp_path, llm, general_prompts=False, add_pdf=True)
    assert "Question scope" in caplog.text
    peru = {"prompt": "What is the capital of Peru?"}
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        assert client.post("/api/chat", json=peru).json()["content"].startswith("Sorry")
        client.patch("/api/settings", json={"general_prompts": True})
        assert client.post("/api/chat", json=peru).json()["content"] == "Two moons."
        client.patch("/api/settings", json={"general_prompts": False})
        assert client.post("/api/chat", json=peru).json()["content"].startswith("Sorry")
