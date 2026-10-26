"""Replies to the example questions, kept once made (roadmap R130a)."""

import io
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from test_question_scope import PDF
from test_reply_video import REPLY_ID, stop_patches, video_app  # noqa: F401 (a fixture)

from imageskin.pdf_reading import Piece, Progress, Reading
from imageskin.reply_video import ReplyVideos, SentenceClips, VoiceReady
from imageskin.review import Review
from imageskin.topic_replies import REPLY_FILE, TopicReplies, context_of
from imageskin.wiki import Progress as WikiProgress
from imageskin.wiki import Wiki, WikiPage

QUESTION = "What can you tell me about Rain?"


def clips_in(folder: Path, *texts: str) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for n, text in enumerate(texts, 1):
        path = folder / f"{n}.mp4"
        path.write_text(text)
        paths.append(path)
    return paths


def test_a_reply_kept_is_given_back_only_for_its_context(tmp_path: Path) -> None:
    kept = TopicReplies(tmp_path / "topics")
    assert kept.get(QUESTION, "a") is None
    kept.keep(QUESTION, "a", "Rain falls.", clips_in(tmp_path / "made", "one", "two"))
    got = kept.get(f"  {QUESTION.lower()} ", "a")  # as typed, in any case
    assert got is not None and got.text == "Rain falls."
    assert [c.read_text() for c in got.clips] == ["one", "two"]
    assert kept.get(QUESTION, "b") is None  # another person, voice or wiki
    assert kept.get("Tell me about Snow.", "a") is None


def test_keeping_a_reply_replaces_the_last_and_removes_other_contexts(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    kept = TopicReplies(tmp_path / "topics")
    kept.keep(QUESTION, "old", "Old.", clips_in(tmp_path / "a", "old"))
    kept.keep("Tell me about Snow.", "old", "Snow.", clips_in(tmp_path / "b", "snow"))
    with caplog.at_level(logging.INFO, logger="imageskin.topic_replies"):
        kept.keep(QUESTION, "new", "New.", clips_in(tmp_path / "c", "new"))
    got = kept.get(QUESTION, "new")
    assert got is not None and got.text == "New."
    assert len(list((tmp_path / "topics").iterdir())) == 1  # Snow's, made with "old", is gone
    logged = next(r for r in caplog.records if r.message == "Topic reply kept")
    assert (logged.clips, logged.stale_removed) == (1, 1)  # type: ignore[attr-defined]
    assert logged.duration_ms >= 0  # type: ignore[attr-defined]


def test_a_reply_with_a_clip_missing_or_unreadable_is_not_given(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    kept = TopicReplies(tmp_path / "topics")
    kept.keep(QUESTION, "a", "Rain.", clips_in(tmp_path / "made", "one", "two"))
    entry = next((tmp_path / "topics").iterdir())
    (entry / "2.mp4").unlink()
    assert kept.get(QUESTION, "a") is None
    (entry / REPLY_FILE).write_text("{not json")
    with caplog.at_level(logging.WARNING, logger="imageskin.topic_replies"):
        assert kept.get(QUESTION, "a") is None
    assert any(r.message == "Kept topic reply can't be read" for r in caplog.records)


def test_a_reply_that_cant_be_kept_is_logged_and_leaves_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    kept = TopicReplies(tmp_path / "topics")
    with caplog.at_level(logging.ERROR, logger="imageskin.topic_replies"):
        kept.keep(QUESTION, "a", "Rain.", [tmp_path / "gone.mp4"])
    logged = next(r for r in caplog.records if r.message == "Could not keep a topic reply")
    assert "gone.mp4" in logged.error  # type: ignore[attr-defined]
    assert list((tmp_path / "topics").iterdir()) == []


def test_the_context_tells_what_a_reply_was_made_with_apart() -> None:
    assert context_of("photo", "voice", [{"t": 1}]) == context_of("photo", "voice", [{"t": 1}])
    assert context_of("photo", "voice", [{"t": 1}]) != context_of("photo", "voice", [{"t": 2}])
    assert len(context_of(None)) == 16


def write_text(photo: Path, text: str, output: Path) -> None:
    output.write_text(text)


def sentence_clips(tmp_path: Path) -> SentenceClips:
    videos = ReplyVideos(tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"))
    return videos.sentence_clips(tmp_path / "me.jpg", REPLY_ID)


def test_the_clips_are_handed_on_once_all_are_rendered(tmp_path: Path) -> None:
    clips = sentence_clips(tmp_path)
    handed: list[list[str]] = []
    clips.on_complete = lambda made: handed.append([p.read_text() for p in made])
    clips("Hi there.")
    clips("Bye.")
    clips.close()
    clips.wait(5)
    assert handed == [["Hi there.", "Bye."]] and clips.done


def test_clips_stopped_or_failed_are_not_handed_on(tmp_path: Path) -> None:
    clips = sentence_clips(tmp_path)
    handed: list[list[Path]] = []
    clips.on_complete = handed.append
    clips._cancelled = True  # stopped before its sentence was made
    clips("Hi there.")
    clips.close()
    clips.wait(5)
    assert handed == []


def test_a_failure_handing_the_clips_on_is_logged_and_the_reply_still_ends(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clips = sentence_clips(tmp_path)

    def fail(made: list[Path]) -> None:
        raise RuntimeError("disk gone")

    clips.on_complete = fail
    clips("Hi there.")
    with caplog.at_level(logging.ERROR, logger="imageskin.reply_video"):
        clips.close()
        clips.wait(5)
    assert clips.done and clips.error is None
    assert any(r.message == "Could not hand on a reply's clips" for r in caplog.records)


def test_clips_made_before_are_listed_whole_at_once(tmp_path: Path) -> None:
    clips = sentence_clips(tmp_path)
    clips.replay(clips_in(tmp_path / "kept", "one", "two"))
    clips.close()
    assert clips.done and clips.sentences == 2 and clips.rendered == 2
    found = clips.clip(2)
    assert found is not None and found[1] and found[0].read_text() == "two"
    assert found[0].parent == clips.folder  # a copy: the kept one stays when these are removed


# --- In the chat ---


def app_with_examples(tmp_path: Path, asked: list[str], titles: list[str]) -> Any:
    """A chat that streams its replies into clips, with a PDF whose wiki has these topics."""

    def read(path: Path, progress: Progress) -> Reading:
        return Reading("text", 1, [Piece(1, "paragraph", "Rain falls. Snow is frozen.")], [])

    def build(pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress, w: Any) -> Wiki:
        pages = [
            WikiPage(f"{pdf_id}-{i}", t, f"{t} is weather.", [1]) for i, t in enumerate(titles)
        ]
        return Wiki(1, pages)

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        asked.append(messages[-1]["content"])
        yield from ["It falls from clouds. ", "It is wet."]

    client = video_app(tmp_path, write_text, stream, read_pdf=read, build_wiki=build)
    client.post("/api/content", files={"file": ("weather.pdf", io.BytesIO(PDF))})
    client.app.state.readings.wait()  # type: ignore[attr-defined]
    client.app.state.wiki.wait()  # type: ignore[attr-defined]
    return client


def ask_and_play(client: Any, prompt: str, reply_id: str) -> tuple[str, list[str]]:
    """The reply's text and its clips' contents, once every clip is made."""
    sent = client.post("/api/chat", json={"prompt": prompt, "reply_id": reply_id})
    assert sent.status_code == 200 and sent.json()["streamed"] is True
    api = f"/api/chat/clips/{reply_id}"
    status = client.get(api).json()
    while not status["done"]:
        status = client.get(api, params={"known": len(status["clips"])}).json()
    return sent.json()["content"], [client.get(c["url"]).text for c in status["clips"]]


def test_an_example_question_asked_again_is_said_from_its_kept_reply(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    asked: list[str] = []
    client = app_with_examples(tmp_path, asked, ["Rain"])
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        examples = client.get("/api/chat/hints").json()["examples"]
        assert examples == [QUESTION]
        first = ask_and_play(client, QUESTION, REPLY_ID)
        assert first == (
            "It falls from clouds. It is wet.",
            ["It falls from clouds.", "It is wet."],
        )
        assert len(asked) == 1
        with caplog.at_level(logging.INFO, logger="imageskin.app"):
            again = ask_and_play(client, QUESTION, "e" * 32)
        assert again == first and len(asked) == 1  # no LLM call, no rendering
        logged = next(r for r in caplog.records if r.message == "Topic reply from the kept one")
        assert logged.clips == 2  # type: ignore[attr-defined]
        # Kept in the conversation like any reply.
        turns = client.get("/api/chat").json()["turns"]
        assert [t["content"] for t in turns][-2:] == [QUESTION, first[0]]
        # Any other question still goes to the LLM, every time.
        for reply_id in ("a" * 32, "b" * 32):
            ask_and_play(client, "Why does rain fall?", reply_id)
        assert len(asked) == 3


def test_a_kept_reply_is_made_again_once_the_wiki_changes(tmp_path: Path) -> None:
    asked: list[str] = []
    client = app_with_examples(tmp_path, asked, ["Rain"])
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        ask_and_play(client, QUESTION, REPLY_ID)
        edited = client.app.state.wiki.contents()
        with patch.object(
            client.app.state.wiki, "contents", return_value=[{**edited[0], "pdf_name": "new.pdf"}]
        ):
            ask_and_play(client, QUESTION, "e" * 32)
        assert len(asked) == 2


def test_delete_my_data_removes_the_kept_replies(tmp_path: Path) -> None:
    from imageskin.delete_data import delete_my_data

    TopicReplies(tmp_path / "replies" / "topics").keep(
        QUESTION, "a", "Rain.", clips_in(tmp_path / "made", "one")
    )
    delete_my_data(tmp_path)
    assert not (tmp_path / "replies" / "topics").exists()
