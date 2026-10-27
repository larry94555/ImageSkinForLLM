"""What thinking is doing while a prompt is answered, and how long it took (R134c)."""

import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from imageskin import thinking
from imageskin.app import create_app
from imageskin.chat import Conversation, Message, Turn, load_saved
from imageskin.review import Review
from imageskin.thinking import PARTS, PHRASE_S, PHRASES, STARTING, WRITING, Part, Thinking, say
from imageskin.uploads import PhotoResult


class Recorded(Thinking):
    """A Thinking that keeps every stage it was told, in order."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: list[str] = []

    def stage(self, name: str, since: float | None = None, part: Part | None = None) -> None:
        self.seen.append(name)
        super().stage(name, since, part)


@pytest.fixture(autouse=True)
def fresh_times(tmp_path: Path) -> Iterator[None]:
    """Each test starts knowing no stage's usual time, and the warm-up at its start."""
    thinking.remember_in(tmp_path / "thinking_times.json")
    yield
    thinking.getting_ready(thinking.GETTING_READY)
    thinking.warm_up_ended()


@contextmanager
def following(thought: Thinking) -> Iterator[None]:
    token = thinking.current.set(thought)
    try:
        yield
    finally:
        thinking.current.reset(token)


def test_a_stage_keeps_its_start_when_told_again() -> None:
    thought = Thinking(now=time.perf_counter() - 3)
    assert thought.now()["stage"] == STARTING and thought.now()["elapsed_s"] >= 3
    thought.stage(WRITING)
    started = thought._stage[1]
    thought.stage(WRITING)  # each piece of the reply says so again
    assert thought._stage[1] == started
    assert set(thought.now()) == {"stage", "elapsed_s"}  # no detail, no numbers but the time


def test_nothing_is_followed_without_a_prompt() -> None:
    thinking.stage("Thinking about the answer")  # no prompt on this thread: nothing happens
    assert thinking.took() is None


def test_the_time_taken_is_read_on_the_prompts_thread() -> None:
    thought = Thinking(now=time.perf_counter() - 2.04)
    with following(thought):
        assert thinking.took() == 2.0


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
    assert thought.seen[:2] == ["Looking through the course material", "Thinking about the answer"]
    assert set(thought.seen[2:]) == {WRITING}
    # Plain words for anyone: no numbers and no technical terms (Larry, testing PR #179).
    assert not any(c.isdigit() for c in "".join(thought.seen))
    assert not any(w in "".join(thought.seen).lower() for w in ("token", "llm", "pdf"))
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
    assert thought.seen[0] == "Remembering what we talked about"


def test_the_topics_reply_says_it_lists_them() -> None:
    conversation = Conversation(lambda messages: "", lambda: 4096, topics=lambda: ["Cells"])
    thought = Recorded()
    with following(thought):
        conversation.send("What topics can you talk about?")
    assert "Listing what we can talk about" in thought.seen


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
    assert now["stage"] == "Reading your question" and now["elapsed_s"] >= 0
    assert replies[0]["content"] == "Hello" and replies[0]["thinking_s"] >= 0  # type: ignore[operator]
    assert client.get(f"/api/chat/thinking/{reply_id}").status_code == 404  # the reply is in
    assert client.get("/api/chat/thinking/not-an-id").status_code == 422


def test_a_long_stage_shows_progress_and_never_says_the_same_twice() -> None:
    """Never the same words for more than 10 seconds, and never the same words again: a stage
    that goes on counts its parts (Larry, testing PR #179)."""
    assert 5 <= PHRASE_S <= 10
    said = [say(thinking.ANSWERING, PHRASE_S * n + 1) for n in range(20)]
    assert said[:3] == ["Reading your question", thinking.ANSWERING, "Planning how to explain it"]
    assert said[3] == "Planning how to explain it, part 4"
    assert len(set(said)) == len(said)
    assert say("Listing what we can talk about", 60) == "Listing what we can talk about"
    for phrases in PHRASES.values():
        assert len(set(phrases)) == len(phrases)
        for words in phrases:
            assert not any(c.isdigit() for c in words) and len(words.split()) <= 6
            assert not any(w in words.lower() for w in ("voice", "video", "load", "llm", "token"))


def test_the_parts_are_counted_out_of_how_long_it_took_last_time(tmp_path: Path) -> None:
    times = tmp_path / "thinking_times.json"
    thought = Thinking()
    thought.stage(thinking.ANSWERING)
    thought._stage = (thinking.ANSWERING, thought._stage[1] - 40, None)
    thought.stage(WRITING)  # it took 40 seconds: five parts of 8
    assert json.loads(times.read_text(encoding="utf-8")) == {thinking.ANSWERING: 40.0}
    thinking.remember_in(times)  # read back, as at the next start
    assert thinking.usual(thinking.ANSWERING) == 40.0
    planning = "Planning how to explain it"
    assert say(thinking.ANSWERING, PHRASE_S * 3 + 1) == f"{planning}, part 4 of about 5"
    assert say(thinking.ANSWERING, PHRASE_S * 5 + 1) == (
        "Planning how to explain it, part 6, longer than last time"
    )
    thought.stage(STARTING)  # a stage over in a moment isn't remembered
    assert thinking.usual(WRITING) is None
    thought.done()
    assert thinking.usual(STARTING) is None


def test_counted_work_says_its_part_all_along() -> None:
    assert say(WRITING, 1, Part(3)) == "Writing my answer, part 3"
    assert say(thinking.FACE, 1, Part(1, 300)) == f"{thinking.FACE}, part 1 of {PARTS}"
    assert say(thinking.FACE, 30, Part(150, 300)) == f"Getting comfortable, part 5 of {PARTS}"
    assert say(thinking.FACE, 90, Part(300, 300)) == f"Getting comfortable, part {PARTS} of {PARTS}"


def test_saved_times_that_are_not_numbers_are_left_out(tmp_path: Path) -> None:
    times = tmp_path / "thinking_times.json"
    times.write_text(json.dumps({"a": 9, "b": True, "c": "9", "d": -1}), encoding="utf-8")
    thinking.remember_in(times)
    assert [thinking.usual(k) for k in "abcd"] == [9.0, None, None, None]
    times.write_text("not json", encoding="utf-8")
    thinking.remember_in(times)
    assert thinking.usual("a") is None
    times.write_text("[]", encoding="utf-8")
    thinking.remember_in(times)
    assert thinking.usual("a") is None


def test_times_that_cant_be_kept_are_logged(tmp_path: Path) -> None:
    (tmp_path / "file").write_text("", encoding="utf-8")
    thinking.remember_in(tmp_path / "file" / "thinking_times.json")  # under a file: can't
    with patch.object(thinking.logger, "warning") as warned:
        thinking._took(thinking.ANSWERING, 20)
    assert warned.call_args.args[0] == "Could not keep how long thinking took"
    assert thinking.usual(thinking.ANSWERING) == 20  # still known until the next start
    with patch.object(thinking.logger, "warning") as warned:
        thinking.remember_in(tmp_path)  # a folder: can't be read
    assert warned.call_args.args[0] == "Could not read how long thinking took"


def test_the_phrase_follows_the_stages_time() -> None:
    thought = Thinking()
    thought.stage(thinking.ANSWERING)
    started = thought._stage[1]
    with patch("imageskin.thinking.time.perf_counter", return_value=started + PHRASE_S + 1):
        assert thought.now()["stage"] == thinking.ANSWERING


def test_a_prompt_waiting_for_the_warm_up_says_its_steps(tmp_path: Path) -> None:
    """Larry saw "Getting ready" for 154 seconds: that was the replies' warm-up after a start.
    A prompt waiting for it now says each of its steps, and how far the counted ones have come."""
    said: list[str] = []
    go = threading.Event()

    def warm_up() -> None:
        for step in (thinking.WAKING_VOICE, thinking.FIRST_WORD, thinking.FACE):
            thinking.getting_ready(step)
            if step == thinking.FACE:
                thinking.ready_part(30, 100)
            go.wait(5)
            go.clear()
        thinking.warm_up_ended()

    class Seen(Thinking):
        def stage(self, name: str, since: float | None = None, part: Part | None = None) -> None:
            super().stage(name, since, part)
            words = self.now()["stage"]
            if not said or said[-1] != words:
                said.append(words)

    client = TestClient(
        create_app(
            tmp_path,
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=lambda photo, text, output: None,
            ask_llm=lambda messages: "Hello",
        )
    )
    client.post("/api/consent", json={"agreed": True})
    app = client.app
    app.state.reply_warm_up = threading.Thread(target=warm_up)  # type: ignore[attr-defined]
    app.state.reply_warm_up.start()  # type: ignore[attr-defined]

    def step_on() -> None:
        for _ in range(3):
            time.sleep(0.7)
            go.set()

    stepping = threading.Thread(target=step_on)
    stepping.start()
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        with patch("imageskin.app.thinking.Thinking", Seen):
            reply = client.post("/api/chat", json={"prompt": "Hi", "reply_id": "cd" * 16})
    stepping.join()
    assert reply.json()["content"] == "Hello"
    assert said[:3] == [
        thinking.WAKING_VOICE,
        thinking.FIRST_WORD,
        f"{thinking.FACE}, part 3 of 10",
    ]
    assert thinking.ready_step().name == thinking.FACE


def test_the_same_work_for_a_reply_says_nothing_to_the_warm_up() -> None:
    thinking.getting_ready(thinking.FACE)
    elsewhere = threading.Thread(target=lambda: thinking.ready_part(5, 10))
    elsewhere.start()
    elsewhere.join()
    assert thinking.ready_step().part is None
    thinking.ready_part(5, 10)
    assert thinking.ready_step().part == Part(5, 10)


def test_the_warm_up_remembers_how_long_its_steps_took() -> None:
    thinking.getting_ready(thinking.WAKING_VOICE)
    thinking._ready[0] = thinking._ready[0]._replace(since=time.perf_counter() - 30)
    thinking.getting_ready(thinking.FIRST_WORD)
    assert thinking.usual(thinking.WAKING_VOICE) == pytest.approx(30, abs=1)
    thinking._ready[0] = thinking._ready[0]._replace(since=time.perf_counter() - 12)
    thinking.warm_up_ended()
    assert thinking.usual(thinking.FIRST_WORD) == pytest.approx(12, abs=1)
    thinking.getting_ready(thinking.FACE)  # a warm-up that ended doesn't time the next start
    assert thinking.usual(thinking.FIRST_WORD) == pytest.approx(12, abs=1)
    # A prompt that waited for a step doesn't time it too.
    thought = Thinking()
    thought.stage(thinking.FACE, since=time.perf_counter() - 50)
    thought.stage(thinking.ANSWERING)
    assert thinking.usual(thinking.FACE) is None
