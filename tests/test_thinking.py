"""What thinking is doing while a prompt is answered, and how long it took (R134c)."""

import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from imageskin import thinking
from imageskin.app import create_app
from imageskin.chat import Conversation, Message, Turn, load_saved, quoted, reading
from imageskin.review import Review
from imageskin.thinking import STARTING, Thinking
from imageskin.uploads import PhotoResult


class Recorded(Thinking):
    """A Thinking that keeps every stage it was told, in order."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: list[tuple[str, str | None]] = []

    def stage(self, name: str, detail: str | None = None) -> None:
        self.seen.append((name, detail))
        super().stage(name, detail)


@contextmanager
def following(thought: Thinking) -> Iterator[None]:
    token = thinking.current.set(thought)
    try:
        yield
    finally:
        thinking.current.reset(token)


def test_a_stage_keeps_its_start_while_its_detail_changes() -> None:
    thought = Thinking(now=time.perf_counter() - 3)
    assert thought.now()["stage"] == STARTING and thought.now()["elapsed_s"] >= 3
    thought.stage("Asking the LLM", "It reads about 100 tokens")
    thought.wrote("Light is ")
    writing = thought._stage[2]
    thought.wrote("scattered by air.")
    now = thought.now()
    assert now["stage"] == "Writing the reply" and now["detail"] == "5 words so far"
    assert thought._stage[2] == writing  # the same stage: its start is kept
    assert now["stage_s"] <= now["elapsed_s"]


def test_nothing_is_followed_without_a_prompt() -> None:
    thinking.stage("Asking the LLM")  # no prompt on this thread: nothing happens
    thinking.wrote("words")
    assert thinking.took() is None


def test_the_time_taken_is_read_on_the_prompts_thread() -> None:
    thought = Thinking(now=time.perf_counter() - 2.04)
    with following(thought):
        assert thinking.took() == 2.0


def test_what_the_llm_reads_is_said_plainly() -> None:
    hi = [Turn("user", "Hi"), Turn("assistant", "Hello")]
    assert reading(0, [], None) == "your question"
    assert reading(1, [], None) == "your question and 1 passage from the PDFs"
    assert reading(3, hi, "Earlier") == (
        "your question, 3 passages from the PDFs, 2 earlier messages and a summary of the "
        "conversation"
    )


def test_words_are_said_plainly() -> None:
    assert thinking.plural(1, "passage") == "1 passage"
    assert thinking.plural(3, "passage") == "3 passages"
    assert quoted("Why is the sky blue?") == "“Why is the sky blue?”"
    long = quoted("word " * 30)
    assert long.endswith("…”") and len(long) <= 63


def test_a_reply_from_the_pdfs_goes_through_each_stage_and_keeps_its_time() -> None:
    def stream(messages: list[Message]) -> Iterator[str]:
        yield "Light is "
        yield "scattered."

    conversation = Conversation(
        lambda messages: "unused",
        lambda: 4096,
        stream=stream,
        find=lambda prompt: ["Blue light scatters most.", "The sky is blue."],
    )
    thought = Recorded()
    with following(thought):
        reply, turn = conversation.send("Why is the sky blue?")
    names = [name for name, _ in thought.seen]
    assert names[:3] == ["Looking through the PDFs", "Looking through the PDFs", "Asking the LLM"]
    assert thought.seen[0][1] == "For “Why is the sky blue?”"
    assert thought.seen[1][1] == "Found 2 passages; 2 fit with the question"
    assert (thought.seen[2][1] or "").endswith(
        "(your question and 2 passages from the PDFs) before it writes the first word"
    )
    assert thought.seen[-1] == ("Writing the reply", "3 words so far")
    assert reply.thinking_s is not None and reply.thinking_s >= 0
    assert conversation.turns()[turn] == reply


def test_a_prompt_waiting_for_the_summary_says_so() -> None:
    conversation = Conversation(lambda messages: "Hello", lambda: 4096)
    release = threading.Event()
    conversation._summarizer = threading.Thread(target=release.wait)
    conversation._summarizer.start()
    thought = Recorded()
    threading.Timer(0.05, release.set).start()
    with following(thought):
        conversation.send("Hi")
    assert thought.seen[0][0] == "Catching up on the conversation"


def test_the_topics_reply_says_it_lists_them() -> None:
    conversation = Conversation(lambda messages: "", lambda: 4096, topics=lambda: ["Cells"])
    thought = Recorded()
    with following(thought):
        conversation.send("What topics can you talk about?")
    assert ("Listing the topics in the PDFs", None) in thought.seen


def test_the_time_is_saved_and_read_back(tmp_path: Path) -> None:
    saved = tmp_path / "conversation.json"
    conversation = Conversation(lambda messages: "Hello", lambda: 4096, saved=saved)
    with following(Thinking(now=time.perf_counter() - 4)):
        conversation.send("Hi")
    data = json.loads(saved.read_text(encoding="utf-8"))
    assert data["transcript"][0] == {"role": "user", "content": "Hi"}
    assert data["transcript"][1]["thinking_s"] >= 4
    assert "thinking_s" not in data["turns"][1]  # never sent to the LLM
    assert load_saved(saved).transcript[1].thinking_s == data["transcript"][1]["thinking_s"]


def test_a_saved_time_that_isnt_a_number_is_left_out(tmp_path: Path) -> None:
    saved = tmp_path / "conversation.json"
    turns = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello", "thinking_s": True},
        {"role": "user", "content": "Again"},
        {"role": "assistant", "content": "Hello", "thinking_s": "4"},
    ]
    saved.write_text(json.dumps({"transcript": turns, "turns": turns}), encoding="utf-8")
    assert [t.thinking_s for t in load_saved(saved).transcript] == [None] * 4
    assert Turn("assistant", "Hello").shown() == {"role": "assistant", "content": "Hello"}


def test_the_api_says_what_a_prompt_is_thinking_about(tmp_path: Path) -> None:
    asked = threading.Event()
    answer = threading.Event()

    def ask(messages: list[Message]) -> str:
        asked.set()
        answer.wait(5)
        return "Hello"

    client = TestClient(
        create_app(
            tmp_path,
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=lambda photo, text, output: None,
            ask_llm=ask,
        )
    )
    client.post("/api/consent", json={"agreed": True})
    reply_id = "ab" * 16
    assert client.get(f"/api/chat/thinking/{reply_id}").status_code == 404  # not come yet
    replies: list[dict[str, object]] = []
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        sending = threading.Thread(
            target=lambda: replies.append(
                client.post("/api/chat", json={"prompt": "Hi", "reply_id": reply_id}).json()
            )
        )
        sending.start()
        assert asked.wait(5)
        now = client.get(f"/api/chat/thinking/{reply_id}").json()
        answer.set()
        sending.join(5)
    assert now["stage"] == "Asking the LLM" and "It reads about" in now["detail"]
    assert now["elapsed_s"] >= now["stage_s"] >= 0
    assert replies[0]["content"] == "Hello" and replies[0]["thinking_s"] >= 0  # type: ignore[operator]
    assert client.get(f"/api/chat/thinking/{reply_id}").status_code == 404  # the reply is in
    assert client.get("/api/chat/thinking/not-an-id").status_code == 422
