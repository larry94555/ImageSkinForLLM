"""Repeat: the latest reply said again, with no LLM call (roadmap R156)."""

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from test_reply_video import JPG, REPLY_ID, stop_patches, video_app  # noqa: F401 (a fixture)

from imageskin.prepare_job import PrepareJob, PrepareStatus
from imageskin.reply_video import ReplyVideos, SentenceClips, VoiceReady
from imageskin.review import Review
from imageskin.sentences import clips_of

AGAIN_ID = "a" * 32


def test_a_whole_reply_is_cut_into_clips_as_a_streamed_one_is() -> None:
    assert clips_of("It falls from clouds. It is wet.") == ["It falls from clouds.", "It is wet."]
    assert clips_of("") == []


def written(photo: Path, text: str, output: Path) -> None:
    output.write_text(text)


def sentence_clips(tmp_path: Path) -> SentenceClips:
    videos = ReplyVideos(tmp_path, written, VoiceReady(lambda: None, lambda: "v"))
    return videos.sentence_clips(tmp_path / "me.jpg", REPLY_ID)


def test_the_clips_are_whole_only_once_all_are_rendered_and_none_stopped(tmp_path: Path) -> None:
    clips = sentence_clips(tmp_path)
    clips("Hi there.")
    assert clips.whole() is None  # not done yet
    clips.close()
    clips.wait(5)
    made = clips.whole()
    assert made is not None and [p.read_text() for p in made] == ["Hi there."]
    made[0].unlink()  # a clip gone: not whole
    assert clips.whole() is None
    stopped = sentence_clips(tmp_path / "stopped")
    stopped("Hi.")
    stopped.cancel()
    assert stopped.whole() is None


def chat_app(tmp_path: Path, asked: list[str], rendered: list[str], streamed: bool = True) -> Any:
    def render(photo: Path, text: str, output: Path) -> None:
        rendered.append(text)
        output.write_text(text)

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        asked.append(messages[-1]["content"])
        yield from ["It falls from clouds. ", "It is wet."]

    def ask(messages: list[dict[str, str]]) -> str:
        asked.append(messages[-1]["content"])
        return "It falls from clouds. It is wet."

    return video_app(tmp_path, render, stream if streamed else None, ask_llm=ask)


def follow(client: Any, reply_id: str) -> list[str]:
    """The clips' contents, once every clip is made."""
    api = f"/api/chat/clips/{reply_id}"
    status = client.get(api).json()
    while not status["done"]:
        status = client.get(api, params={"known": len(status["clips"])}).json()
    assert status["error"] is None
    return [client.get(c["url"]).text for c in status["clips"]]


def test_the_latest_reply_is_said_again_from_its_clips(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    asked: list[str] = []
    rendered: list[str] = []
    client = chat_app(tmp_path, asked, rendered)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        sent = client.post("/api/chat", json={"prompt": "Why rain?", "reply_id": REPLY_ID})
        assert sent.json()["streamed"] is True
        first = follow(client, REPLY_ID)
        assert first == ["It falls from clouds.", "It is wet."]
        before = client.get("/api/chat").json()["turns"]
        with caplog.at_level(logging.INFO, logger="imageskin.app"):
            again = client.post("/api/chat/repeat", json={"reply_id": AGAIN_ID})
        assert again.status_code == 200
        assert again.json() == {"turn": 1, "streamed": True}
        assert follow(client, AGAIN_ID) == first
        assert len(asked) == 1 and len(rendered) == 2  # no LLM call, nothing rendered again
        assert client.get("/api/chat").json()["turns"] == before  # the conversation is unchanged
        logged = next(r for r in caplog.records if r.message == "Reply repeated")
        assert logged.__dict__["from"] == "clips" and logged.clips == 2  # type: ignore[attr-defined]
        assert client.get(f"/api/chat/clips/{REPLY_ID}").status_code == 404  # the old ones go
        # Repeated again, from the clips just played.
        assert client.post("/api/chat/repeat", json={"reply_id": "b" * 32}).status_code == 200
        assert follow(client, "b" * 32) == first and len(rendered) == 2


def test_after_the_person_changes_the_reply_is_spoken_again_by_the_new_one(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Larry's test of PR #266: after another avatar was chosen, Repeat showed the person who
    first said the reply, from its clips. Now it is spoken again by the one in the chat."""
    photos: list[str] = []

    def render(photo: Path, text: str, output: Path) -> None:
        photos.append(photo.name)
        output.write_text(text)

    client = video_app(tmp_path, render, lambda m: iter(["It falls from clouds. ", "It is wet."]))
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Why rain?", "reply_id": REPLY_ID})
        follow(client, REPLY_ID)
        first = set(photos)
        # Another person in the chat: here another photo of one's own.
        other = client.post("/api/uploads/photos", files={"file": ("you.jpg", JPG)}).json()
        patch.object(PrepareJob, "status", return_value=PrepareStatus("done", other["id"])).start()
        with caplog.at_level(logging.INFO, logger="imageskin.app"):
            again = client.post("/api/chat/repeat", json={"reply_id": AGAIN_ID})
        assert again.status_code == 200
        assert follow(client, AGAIN_ID) == ["It falls from clouds.", "It is wet."]
        assert len(photos) == 4 and set(photos[2:]).isdisjoint(first)  # made on the new photo
        assert any(r.message == "Repeat spoken again: the person changed" for r in caplog.records)
        logged = next(r for r in caplog.records if r.message == "Reply repeated")
        assert logged.__dict__["from"] == "text"


def test_a_reply_whose_clips_are_gone_is_spoken_again_from_its_text(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    asked: list[str] = []
    rendered: list[str] = []
    client = chat_app(tmp_path, asked, rendered, streamed=False)  # one video, no clips kept
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        sent = client.post("/api/chat", json={"prompt": "Why rain?", "reply_id": REPLY_ID})
        assert sent.json()["streamed"] is False
        with caplog.at_level(logging.INFO, logger="imageskin.app"):
            again = client.post("/api/chat/repeat", json={"reply_id": AGAIN_ID})
        assert again.status_code == 200
        assert follow(client, AGAIN_ID) == ["It falls from clouds.", "It is wet."]
        assert len(asked) == 1  # no LLM call
        logged = next(r for r in caplog.records if r.message == "Reply repeated")
        assert logged.__dict__["from"] == "text"


def test_there_is_nothing_to_repeat_before_the_first_reply(tmp_path: Path) -> None:
    client = chat_app(tmp_path, [], [])
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        refused = client.post("/api/chat/repeat", json={"reply_id": AGAIN_ID})
    assert refused.status_code == 409
    assert refused.json()["detail"] == "There is no reply to repeat yet."


def test_a_repeat_can_be_stopped(tmp_path: Path) -> None:
    client = chat_app(tmp_path, [], [])
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Why rain?", "reply_id": REPLY_ID})
        follow(client, REPLY_ID)
        client.post("/api/chat/repeat", json={"reply_id": AGAIN_ID})
        stopped = client.post(f"/api/chat/clips/{AGAIN_ID}/stop")
    assert stopped.json() == {"stopped": True}


def test_a_repeat_that_cant_copy_the_clips_says_so_and_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client = chat_app(tmp_path, [], [])
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Why rain?", "reply_id": REPLY_ID})
        follow(client, REPLY_ID)
        with (
            patch.object(SentenceClips, "replay", side_effect=OSError("disk full")),
            caplog.at_level(logging.ERROR, logger="imageskin.app"),
        ):
            failed = client.post("/api/chat/repeat", json={"reply_id": AGAIN_ID})
        assert failed.status_code == 500
        assert failed.json()["detail"] == "The reply couldn't be repeated."
        assert client.get(f"/api/chat/clips/{AGAIN_ID}").status_code == 404
    assert any(r.message == "Could not repeat the reply" for r in caplog.records)


def test_a_repeat_stopped_before_it_came_is_not_said(tmp_path: Path) -> None:
    rendered: list[str] = []
    client = chat_app(tmp_path, [], rendered)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Why rain?", "reply_id": REPLY_ID})
        first = follow(client, REPLY_ID)
        # Stop wins the race: it reaches the server before the repeat does (Codex's review).
        assert client.post(f"/api/chat/clips/{AGAIN_ID}/stop").json() == {"stopped": False}
        refused = client.post("/api/chat/repeat", json={"reply_id": AGAIN_ID})
        assert refused.status_code == 409 and refused.json()["detail"] == "Stopped."
        assert client.get(f"/api/chat/clips/{AGAIN_ID}").status_code == 404  # nothing made
        assert follow(client, REPLY_ID) == first  # the reply's clips are still there
        # The marker was taken: the same id is said when asked again.
        assert client.post("/api/chat/repeat", json={"reply_id": AGAIN_ID}).status_code == 200
        assert follow(client, AGAIN_ID) == first


def test_a_reply_spoken_again_from_its_text_says_the_same_words(tmp_path: Path) -> None:
    """Links and code are said the same way as the first time (Codex's review)."""
    rendered: list[str] = []

    def render(photo: Path, text: str, output: Path) -> None:
        rendered.append(text)
        output.write_text(text)

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        yield "See [the docs](https://example.com/rain) for more. "
        yield "Run this:\n\n```python\nprint('rain')\n```\n\nThat's it."

    client = video_app(tmp_path, render, stream)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Why rain?", "reply_id": REPLY_ID})
        follow(client, REPLY_ID)
        said = list(rendered)
        made = list((tmp_path / "replies" / f"clips-{REPLY_ID}").glob("*.mp4"))
        assert made
        for clip in made:
            clip.unlink()  # gone, as after a restart: spoken again from the text
        client.post("/api/chat/repeat", json={"reply_id": AGAIN_ID})
        follow(client, AGAIN_ID)
    again = rendered[len(said) :]
    assert " ".join(again).split() == " ".join(said).split()
    assert not any("https://" in t or "print(" in t for t in again)
