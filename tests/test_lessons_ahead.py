"""Each topic's first lesson part, written ahead (roadmap R98a)."""

import logging
import threading
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from test_question_scope import Llm
from test_topics import riemann_app

from imageskin.app import create_app
from imageskin.chat import Conversation, LlmError, Message, Teach
from imageskin.lessons_ahead import LESSONS_FILE, LessonsAhead, key, sentences
from imageskin.llm_choice import save_choice
from imageskin.review import Review
from imageskin.uploads import PhotoResult
from imageskin.wiki import Wiki, WikiPage

ZETA = Teach('Teach me the main ideas of "Zeta"', ["Zeta: Zeta sums 1/n^s."])
PRIMES = Teach('Teach me the main ideas of "Primes"', ["Primes: No divisors."])


class Writer:
    """The LLM, answering each part with its topic's name, or failing while `down`."""

    def __init__(self) -> None:
        self.asked: list[Teach] = []
        self.down = 0  # how many asks fail before it answers
        self.answer = "{0} has two ideas. Here is the second, about {0}."

    def __call__(self, teach: Teach) -> str:
        self.asked.append(teach)
        if self.down:
            self.down -= 1
            raise LlmError("The LLM can't be reached.")
        return self.answer.format(teach.instruction.split('"')[1])


def ahead(
    tmp_path: Path,
    firsts: dict[str, Teach],
    writer: Writer,
    wanted: bool = True,
    busy: bool = False,
) -> LessonsAhead:
    return LessonsAhead(
        tmp_path, lambda: firsts, writer, lambda: wanted, lambda: busy, retry_s=0.01
    )


def written(lessons: LessonsAhead) -> LessonsAhead:
    lessons.refresh()
    lessons.wait()
    return lessons


def test_each_topic_s_first_part_is_written_saved_and_said_from(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    writer = Writer()
    with caplog.at_level(logging.INFO, logger="imageskin.lessons_ahead"):
        lessons = written(ahead(tmp_path, {"Zeta": ZETA, "Primes": PRIMES}, writer))
    assert writer.asked == [ZETA, PRIMES]
    assert lessons.saved("Zeta", ZETA) == [
        "Zeta has two ideas.",
        "Here is the second, about Zeta.",
    ]
    assert lessons.status() == {
        "wanted": True,
        "writing": False,
        "ready": True,
        "saved": ["Primes", "Zeta"],
    }
    saved = [r for r in caplog.records if r.message == "Lesson saved"]
    assert [r.topic for r in saved] == ["Zeta", "Primes"]  # type: ignore[attr-defined]
    assert all(r.duration_ms >= 0 for r in saved)  # type: ignore[attr-defined]
    assert "Lessons written ahead" in caplog.text
    # Kept with the wiki, so a new start finds them and writes nothing again.
    assert (tmp_path / LESSONS_FILE).exists()
    again = Writer()
    written(ahead(tmp_path, {"Zeta": ZETA, "Primes": PRIMES}, again))
    assert again.asked == []


def test_a_topic_whose_material_changed_is_taught_as_before_until_written_again(
    tmp_path: Path,
) -> None:
    """An edit, a rebuild or going back to a version changes what the lesson asks."""
    firsts = {"Zeta": ZETA, "Primes": PRIMES}
    writer = Writer()
    lessons = written(ahead(tmp_path, firsts, writer))
    edited = Teach(ZETA.instruction, ["Zeta: Edited by the host."])
    assert lessons.saved("Zeta", edited) is None
    firsts["Zeta"] = edited
    written(lessons)
    assert writer.asked[2:] == [edited]  # only the topic that changed
    assert lessons.saved("Zeta", edited) is not None
    assert lessons.saved("Zeta", ZETA) is None


def test_a_topic_gone_from_the_wiki_is_dropped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    firsts = {"Zeta": ZETA, "Primes": PRIMES}
    lessons = written(ahead(tmp_path, firsts, Writer()))
    del firsts["Primes"]  # its PDF removed
    with caplog.at_level(logging.INFO, logger="imageskin.lessons_ahead"):
        written(lessons)
    assert lessons.status()["saved"] == ["Zeta"]
    assert next(r for r in caplog.records if r.message == "Lessons dropped").topics == [  # type: ignore[attr-defined]
        "Primes"
    ]


def test_nothing_is_written_while_teach_me_is_off(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    writer = Writer()
    with caplog.at_level(logging.INFO, logger="imageskin.lessons_ahead"):
        written(ahead(tmp_path, {"Zeta": ZETA}, writer, wanted=False))
    assert writer.asked == [] and "Teach me is off" in caplog.text


def test_nothing_is_written_while_a_wiki_is_built(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    writer = Writer()
    with caplog.at_level(logging.INFO, logger="imageskin.lessons_ahead"):
        written(ahead(tmp_path, {"Zeta": ZETA}, writer, busy=True))
    assert writer.asked == [] and "Lessons wait for the wiki to be built" in caplog.text


def test_a_build_starting_partway_stops_the_round(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    building = [False]
    writer = Writer()

    def write(teach: Teach) -> str:
        building[0] = True  # a PDF added while the first part was written
        return writer(teach)

    lessons = LessonsAhead(
        tmp_path, lambda: {"Zeta": ZETA, "Primes": PRIMES}, write, lambda: True, lambda: building[0]
    )
    with caplog.at_level(logging.INFO, logger="imageskin.lessons_ahead"):
        written(lessons)
    assert writer.asked == [ZETA] and lessons.status()["saved"] == ["Zeta"]
    # Not ready until a round after the build saves the rest (Larry's run of PR #160).
    assert lessons.status()["ready"] is False
    done = next(r for r in caplog.records if r.message == "Lessons written ahead")
    assert (done.stopped, done.missing) == ("wiki being built", 1)  # type: ignore[attr-defined]
    building[0] = False
    writer.answer = "{0}."
    lessons._write = writer
    assert written(lessons).status()["ready"] is True


def test_with_the_llm_down_it_is_tried_again_later(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    writer = Writer()
    writer.down = 1
    lessons = ahead(tmp_path, {"Zeta": ZETA, "Primes": PRIMES}, writer)
    with caplog.at_level(logging.INFO, logger="imageskin.lessons_ahead"):
        written(lessons)
        for _ in range(200):  # the retry's round
            if lessons.status()["saved"] == ["Primes", "Zeta"]:
                break
            threading.Event().wait(0.01)
            lessons.wait()
    assert lessons.status()["saved"] == ["Primes", "Zeta"]
    failed = next(r for r in caplog.records if r.message == "Lesson not saved")
    assert failed.topic == "Zeta" and "can't be reached" in failed.error  # type: ignore[attr-defined]


def test_an_empty_answer_is_not_saved(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    writer = Writer()
    writer.answer = "   "
    lessons = written(ahead(tmp_path, {"Zeta": ZETA}, writer))
    assert lessons.status()["saved"] == []
    assert "the LLM wrote nothing" in caplog.text


def test_a_refresh_asked_for_during_a_round_runs_another(tmp_path: Path) -> None:
    firsts = {"Zeta": ZETA}
    writer = Writer()
    lessons: LessonsAhead

    def write(teach: Teach) -> str:
        if len(writer.asked) == 0:
            firsts["Primes"] = PRIMES  # a PDF built meanwhile
            lessons.refresh()
        return writer(teach)

    lessons = LessonsAhead(tmp_path, lambda: dict(firsts), write, lambda: True, lambda: False)
    written(lessons)
    assert writer.asked == [ZETA, PRIMES]


def test_an_unreadable_or_old_file_is_written_again(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / LESSONS_FILE).write_text("{not json", encoding="utf-8")
    writer = Writer()
    lessons = ahead(tmp_path, {"Zeta": ZETA}, writer)
    assert lessons.status()["saved"] == []
    assert "Could not read the saved lessons" in caplog.text
    (tmp_path / LESSONS_FILE).write_text('{"format": 0, "lessons": {}}', encoding="utf-8")
    written(lessons)
    assert writer.asked == [ZETA]


def test_a_lesson_that_cannot_be_saved_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    writer = Writer()
    lessons = ahead(tmp_path / "missing", {"Zeta": ZETA, "Primes": PRIMES}, writer)
    with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
        written(lessons)
    assert "Could not save the lessons" in caplog.text
    assert writer.asked == [ZETA]  # the round stops at the first


def test_a_round_that_fails_is_logged_and_the_next_one_runs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    calls = [0]

    def firsts() -> dict[str, Teach]:
        calls[0] += 1
        if calls[0] == 1:
            raise RuntimeError("wiki unreadable")
        return {"Zeta": ZETA}

    lessons = LessonsAhead(tmp_path, firsts, Writer(), lambda: True, lambda: False)
    written(lessons)
    assert "Could not write the lessons ahead" in caplog.text
    assert written(lessons).status()["saved"] == ["Zeta"]


def test_the_key_follows_the_instruction_and_the_material() -> None:
    assert key(ZETA) == key(Teach(ZETA.instruction, list(ZETA.material)))
    assert key(ZETA) != key(Teach(ZETA.instruction, ["Zeta: Other."]))
    assert key(ZETA) != key(Teach("Explain it more simply", ZETA.material))


def test_the_saved_part_is_split_into_sentences() -> None:
    assert sentences("One idea. Two ideas!\n\nThree?") == ["One idea.", "Two ideas!", "Three?"]
    assert sentences("  ") == []


# --- Through the app ---


class TopicLlm(Llm):
    """Answers a lesson part written ahead with the topic it names."""

    def __call__(self, messages: list[Message]) -> str:
        self.sent.append(messages)
        asked = messages[-1]["content"]
        if "main ideas of" in asked:
            return f"Ahead: {asked.split('main ideas of')[1].split(chr(34))[1]}."
        return "Two moons."


def chat(client: Any, prompt: str, lesson: dict[str, Any] | None = None) -> dict[str, Any]:
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        response = client.post("/api/chat", json={"prompt": prompt, "lesson": lesson})
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_a_picked_topic_is_said_from_its_saved_part(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    llm = TopicLlm()
    client = riemann_app(tmp_path, llm, lessons_ahead=True)
    lessons = client.app.state.lessons
    lessons.wait()
    assert llm.sent == []  # Teach me is off
    assert client.patch("/api/settings", json={"teach_me": True}).status_code == 200
    lessons.wait()
    # Written as the lesson asks it, with the system prompt and none of the conversation.
    assert [len(m) for m in llm.sent] == [2, 2]
    assert llm.sent[0][0]["role"] == "system"
    assert 'Teach me the main ideas of "Prime Number Basics"' in llm.sent[0][1]["content"]
    assert client.get("/api/lessons").json() == {
        "wanted": True,
        "writing": False,
        "ready": True,
        "saved": ["Prime Number Basics", "Zeta Function Integral"],
    }

    with caplog.at_level(logging.INFO, logger="imageskin.app"):
        reply = chat(client, "Teach me about Zeta Function Integral")
    assert reply["content"] == "Ahead: Zeta Function Integral."
    assert reply["lesson"] == {
        "topic": "Zeta Function Integral",
        "part": 0,
        "active": True,
        "parts": 1,
    }
    assert len(llm.sent) == 2  # said without asking the LLM
    used = next(r for r in caplog.records if r.message == "Lesson from the saved part")
    assert used.topic == "Zeta Function Integral"  # type: ignore[attr-defined]
    # The next part is written as before.
    reply = chat(client, "Next", reply["lesson"])
    assert len(llm.sent) == 3 and "Sum up in one sentence" in llm.sent[-1][-1]["content"]
    turns = client.get("/api/chat").json()["turns"]
    assert turns[1]["content"] == "Ahead: Zeta Function Integral."


def test_an_edited_topic_is_taught_as_before_then_written_again(tmp_path: Path) -> None:
    llm = TopicLlm()
    client = riemann_app(tmp_path, llm, lessons_ahead=True)
    lessons = client.app.state.lessons
    assert client.patch("/api/settings", json={"teach_me": True}).status_code == 200
    lessons.wait()
    pdf_id = client.get("/api/content").json()[0]["id"]
    wiki = client.app.state.wiki
    wiki.when_changed = None  # not written again yet
    edited = client.put(
        f"/api/wiki/{pdf_id}-zeta",
        json={"title": "Zeta Function Integral", "summary": "Zeta, as edited."},
    )
    assert edited.status_code == 200
    wiki.when_changed = lessons.refresh
    reply = chat(client, "Teach me about Zeta Function Integral")
    assert reply["content"] == "Ahead: Zeta Function Integral."  # the LLM, asked again
    assert "Zeta, as edited." in llm.sent[-1][-1]["content"]
    asked = len(llm.sent)
    lessons.refresh()
    lessons.wait()
    assert len(llm.sent) == asked + 1  # only the edited topic
    assert "Zeta, as edited." in llm.sent[-1][-1]["content"]

    assert client.delete(f"/api/content/{pdf_id}").status_code == 200
    lessons.wait()
    assert client.get("/api/lessons").json()["saved"] == []


def test_with_a_test_s_llm_lessons_are_not_written_ahead(tmp_path: Path) -> None:
    client = riemann_app(tmp_path, Llm())
    assert client.app.state.lessons is None
    assert client.get("/api/lessons").json() == {
        "wanted": False,
        "writing": False,
        "ready": False,
        "saved": [],
    }


def test_the_app_says_whether_the_conversation_is_being_summarized(tmp_path: Path) -> None:
    client = riemann_app(tmp_path, Llm())
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        assert client.get("/api/chat/summary").json() == {"summarizing": False}
    conversation = Conversation(Llm(), lambda: 4096)
    hold = threading.Event()
    conversation._summarizer = threading.Thread(target=hold.wait)
    conversation._summarizer.start()
    assert conversation.summarizing() is True
    hold.set()
    conversation.wait()
    assert conversation.summarizing() is False


def test_turning_teach_me_off_stops_the_round_after_the_lesson_under_way(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Review on PR #160: with a paid provider, no more requests once it is off."""
    wanted = [True]
    writer = Writer()

    def write(teach: Teach) -> str:
        wanted[0] = False  # turned off while the first was written
        return writer(teach)

    lessons = LessonsAhead(
        tmp_path, lambda: {"Zeta": ZETA, "Primes": PRIMES}, write, lambda: wanted[0], lambda: False
    )
    with caplog.at_level(logging.INFO, logger="imageskin.lessons_ahead"):
        written(lessons)
    assert writer.asked == [ZETA]
    done = next(r for r in caplog.records if r.message == "Lessons written ahead")
    assert done.stopped == "Teach me turned off"  # type: ignore[attr-defined]


@pytest.mark.parametrize("on", [True, False])
def test_turning_teach_me_on_or_off_starts_a_round(tmp_path: Path, on: bool) -> None:
    client = riemann_app(tmp_path, TopicLlm(), lessons_ahead=True)
    lessons = client.app.state.lessons
    lessons.wait()
    with patch.object(lessons, "refresh") as refresh:
        assert client.patch("/api/settings", json={"teach_me": on}).status_code == 200
        assert client.patch("/api/settings", json={"quiz_me": True}).status_code == 200
    assert refresh.call_count == 1  # only for Teach me


@pytest.mark.parametrize(("provider", "shares_cores"), [("local", True), ("claude", False)])
def test_a_local_llm_writing_a_lesson_takes_its_share_of_the_cores(
    tmp_path: Path, provider: str, shares_cores: bool
) -> None:
    """Review on PR #160: a topic said from its saved part is spoken while the next is written."""
    save_choice(tmp_path, provider, "k")
    with patch("imageskin.app.CoreShare") as share:
        client = riemann_app(tmp_path, TopicLlm(), lessons_ahead=True)
        assert client.patch("/api/settings", json={"teach_me": True}).status_code == 200
        client.app.state.lessons.wait()
    assert client.get("/api/lessons").json()["ready"] is True
    assert share.return_value.llm.called is shares_cores


def test_a_build_under_way_at_the_start_is_followed_by_a_round(tmp_path: Path) -> None:
    """Review on PR #160: a wiki build begun by catch_up that ends after the first round's
    check, but before the callbacks were installed, left the lessons unwritten."""
    first = riemann_app(tmp_path, TopicLlm())
    assert first.patch("/api/settings", json={"teach_me": True}).status_code == 200
    wiki_folder = first.app.state.wiki.folder
    [built] = [p for p in wiki_folder.glob("*.json") if p.stem not in ("pace", "lessons")]
    built.unlink()  # built again by the next start's catch_up
    release = threading.Event()

    def held(pdf: str, pieces: list[dict[str, Any]], progress: Any, w: Any) -> Wiki:
        release.wait(10)
        return Wiki(2, [WikiPage(f"{pdf}-zeta", "Zeta Function Integral", "Zeta.", [2])])

    class Racing(LessonsAhead):
        started = False

        def refresh(self) -> None:
            wiki = self._busy.__self__  # type: ignore[attr-defined]
            if Racing.started:
                if wiki._worker is None:  # read without the lock, which a change holds
                    super().refresh()
                return  # a round asked for by a change during the build sees it under way
            Racing.started = True
            self._round()  # sees the build under way
            release.set()  # which then ends before refresh returns
            while self._busy():
                threading.Event().wait(0.01)

    llm = TopicLlm()
    with patch("imageskin.app.LessonsAhead", Racing):
        app = create_app(
            tmp_path,
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=lambda photo, text, output: None,
            ask_llm=llm,
            build_wiki=held,
            lessons_ahead=True,
        )
    app.state.wiki.wait()
    app.state.lessons.wait()
    assert app.state.lessons.status()["saved"] == ["Zeta Function Integral"]


def test_a_change_during_a_round_starts_it_again(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    writer = Writer()
    lessons: LessonsAhead

    def write(teach: Teach) -> str:
        if not writer.asked:
            lessons.refresh()  # a wiki entry edited while the first was written
        return writer(teach)

    lessons = LessonsAhead(
        tmp_path, lambda: {"Zeta": ZETA, "Primes": PRIMES}, write, lambda: True, lambda: False
    )
    with caplog.at_level(logging.INFO, logger="imageskin.lessons_ahead"):
        written(lessons)
    assert writer.asked == [ZETA, PRIMES] and lessons.status()["ready"] is True
    first = next(r for r in caplog.records if r.message == "Lessons written ahead")
    assert first.stopped == "wiki changed"  # type: ignore[attr-defined]


def test_a_round_under_way_saves_nothing_once_forgotten(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Delete my data (R31a) forgets the lessons while a part is being written: the round
    saves nothing, so the file is not made again (Codex's review)."""
    writing, release = threading.Event(), threading.Event()
    writer = Writer()

    def slow(teach: Teach) -> str:
        writing.set()
        release.wait(5)
        return writer(teach)

    lessons = LessonsAhead(tmp_path / "wiki", lambda: {"Zeta": ZETA}, slow, lambda: True, bool)
    lessons.refresh()
    assert writing.wait(5)
    with caplog.at_level(logging.INFO):
        lessons.forget()
        release.set()
        lessons.wait()
    assert not (tmp_path / "wiki").exists()
    assert "Lessons forgotten" in caplog.text and "forgotten meanwhile" in caplog.text
    # A round asked for afterwards writes as before.
    assert written(lessons).status()["saved"] == ["Zeta"]
