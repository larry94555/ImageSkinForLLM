import logging
import subprocess
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from imageskin.app import CHAT_LOCKED, NO_SUCH_REPLY, create_app
from imageskin.chat import LlmError
from imageskin.prepare_job import PrepareJob, PrepareStatus
from imageskin.reply_video import ReplyVideos, VoiceReady, concat
from imageskin.review import Review
from imageskin.uploads import PhotoResult, UploadStore, VoiceSample
from imageskin.video import VideoError

# --- The voice, ready once per voice ---


def test_the_voice_is_prepared_once_per_voice(caplog: pytest.LogCaptureFixture) -> None:
    prepared: list[str] = []
    voice = {"id": "clone:abc"}
    ready = VoiceReady(lambda: prepared.append(voice["id"]), lambda: voice["id"])

    caplog.set_level(logging.INFO)
    ready.ensure()  # after a restart: not prepared yet in this run
    ready.ensure()
    assert prepared == ["clone:abc"]
    assert "Voice made ready for replies" in caplog.messages

    voice["id"] = "clone-british:abc"  # another accent
    ready.ensure()
    assert prepared == ["clone:abc", "clone-british:abc"]


def test_a_voice_without_an_id_is_prepared_once_too() -> None:
    prepared: list[int] = []
    ready = VoiceReady(lambda: prepared.append(1), lambda: None)
    ready.ensure()
    ready.ensure()
    assert prepared == [1]


def test_the_prepare_jobs_voice_step_counts_as_ready() -> None:
    prepared: list[int] = []
    ready = VoiceReady(lambda: prepared.append(1), lambda: "kokoro:abc")
    ready()  # Prepare's voice step
    ready.ensure()
    assert prepared == [1]


# --- Rendering a reply ---


def write_text(photo: Path, text: str, output: Path) -> None:
    output.write_text(f"{photo.name}: {text}")


def test_a_reply_is_spoken_without_markdown_and_only_the_latest_is_kept(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    videos = ReplyVideos(tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"))
    caplog.set_level(logging.INFO)
    first = videos.render(Path("me.jpg"), 1, "**Hello** there")
    assert first == tmp_path / "replies" / "1.mp4"
    assert first.read_text() == "me.jpg: Hello there"
    second = videos.render(Path("me.jpg"), 3, "See https://example.com")
    assert second is not None
    assert second.read_text() == "me.jpg: See the link in the text below"
    assert not first.exists()
    assert "Rendered reply video" in caplog.messages


def test_a_reply_with_nothing_to_say_has_no_video(tmp_path: Path) -> None:
    rendered: list[str] = []
    videos = ReplyVideos(
        tmp_path, lambda p, t, o: rendered.append(t), VoiceReady(lambda: None, lambda: "v")
    )
    assert videos.render(Path("me.jpg"), 1, "🎉🎉") is None
    assert rendered == []


def test_a_failed_video_is_logged_and_left_no_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def fail(photo: Path, text: str, output: Path) -> None:
        output.write_text("half")
        raise VideoError("ffmpeg is not installed")

    videos = ReplyVideos(tmp_path, fail, VoiceReady(lambda: None, lambda: "v"))
    with pytest.raises(VideoError):
        videos.render(Path("me.jpg"), 1, "Hello")
    assert list((tmp_path / "replies").iterdir()) == []
    assert "Reply video failed" in caplog.messages


def test_warming_up_makes_the_voice_ready_and_renders_a_word(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    prepared: list[int] = []
    rendered: list[str] = []
    videos = ReplyVideos(
        tmp_path,
        lambda photo, text, output: rendered.append(text),
        VoiceReady(lambda: prepared.append(1), lambda: "v"),
    )
    caplog.set_level(logging.INFO)
    videos.warm_up(Path("me.jpg"))
    assert prepared == [1] and rendered == ["Hello."]
    assert "Replies warmed up" in caplog.messages
    assert not (tmp_path / "replies").exists()  # the word is thrown away


def test_a_failed_warm_up_is_logged_only(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    def fail(photo: Path, text: str, output: Path) -> None:
        raise VideoError("ffmpeg is not installed")

    videos = ReplyVideos(tmp_path, fail, VoiceReady(lambda: None, lambda: "v"))
    videos.warm_up(Path("me.jpg"))
    assert "Could not warm up replies" in caplog.messages


# --- Sentence by sentence (R21) ---


def tone_clip(seconds: float, output: Path) -> None:
    """A real MP4 like the engines write: H.264 video with AAC sound."""
    cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i"]
    cmd += [f"color=c=gray:s=64x64:d={seconds}", "-f", "lavfi", "-i", f"sine=d={seconds}"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(output)]
    subprocess.run(cmd, check=True)


def seconds_of(video: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0"]
    return float(subprocess.run([*cmd, str(video)], capture_output=True, check=True).stdout)


def test_sentences_are_rendered_in_order_and_joined(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    said: list[str] = []

    def render(photo: Path, text: str, output: Path) -> None:
        said.append(text)
        tone_clip(0.5 * len(said), output)

    videos = ReplyVideos(tmp_path, render, VoiceReady(lambda: None, lambda: "v"))
    clips = videos.sentence_clips(Path("me.jpg"))
    caplog.set_level(logging.INFO)
    clips(None)  # the LLM starts writing
    for sentence in ["**Hello** there.", "🎉", "See https://example.com now."]:
        clips(sentence)
    clips.close()
    video = videos.join(3, clips)
    assert said == ["Hello there.", "See the link in the text below now."]
    assert video == tmp_path / "replies" / "3.mp4"
    assert seconds_of(video) == pytest.approx(1.5, abs=0.1)
    assert list((tmp_path / "replies").iterdir()) == [video]  # the clips are removed
    ready = [r for r in caplog.records if r.message == "Sentence clip ready"]
    assert [r.sentence for r in ready] == [1, 3]  # type: ignore[attr-defined]
    assert all(r.since_first_words_ms is not None for r in ready)  # type: ignore[attr-defined]
    assert "Joined reply video" in caplog.messages


def test_a_streamed_reply_with_nothing_to_say_has_no_video(tmp_path: Path) -> None:
    videos = ReplyVideos(tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"))
    clips = videos.sentence_clips(Path("me.jpg"))
    clips("🎉")
    assert videos.join(1, clips) is None


def test_a_failed_sentence_fails_the_reply_video(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def fail(photo: Path, text: str, output: Path) -> None:
        raise VideoError("ffmpeg is not installed")

    videos = ReplyVideos(tmp_path, fail, VoiceReady(lambda: None, lambda: "v"))
    clips = videos.sentence_clips(Path("me.jpg"))
    clips("One.")
    clips("Two.")
    with pytest.raises(VideoError, match="not installed"):
        videos.join(1, clips)
    assert [r.message for r in caplog.records].count("Sentence clip failed") == 1
    assert "Reply video failed" in caplog.messages


def test_a_cancelled_reply_stops_and_leaves_no_clips(tmp_path: Path) -> None:
    said: list[str] = []
    videos = ReplyVideos(tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"))
    clips = videos.sentence_clips(Path("me.jpg"))
    clips.cancel()  # before any sentence: nothing to stop
    clips = videos.sentence_clips(Path("me.jpg"))
    with videos._lock:  # the engines are busy, so the sentences wait
        clips("One.")
        clips("Two.")
        clips._cancelled = True
    clips.cancel()
    assert said == [] and not clips.folder.exists()


def test_clips_that_cant_be_joined_say_why(tmp_path: Path) -> None:
    broken = tmp_path / "broken.mp4"
    broken.write_text("not a video")
    with pytest.raises(VideoError, match="could not join"):
        concat([broken], tmp_path / "out.mp4")
    assert not (tmp_path / "out.mp4").exists()


# --- The API ---

JPG = b"\xff\xd8\xff\xe0" + b"\0" * 100


def video_app(tmp_path: Path, render: object, stream: object = None) -> TestClient:
    client = TestClient(
        create_app(
            tmp_path,
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=render,  # type: ignore[arg-type]
            ask_llm=lambda messages: f"You said **{messages[-1]['content']}**",
            stream_llm=stream,  # type: ignore[arg-type]
        )
    )
    client.app.state.reply_warm_up.join(5)  # type: ignore[attr-defined]
    client.post("/api/consent", json={"agreed": True})
    photo = client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)}).json()
    done = PrepareStatus("done", photo_id=photo["id"])
    patch.object(PrepareJob, "status", return_value=done).start()
    patch.object(UploadStore, "voice_sample", return_value=VoiceSample(2, 40, 35, None)).start()
    return client


@pytest.fixture(autouse=True)
def stop_patches() -> Iterator[None]:
    yield
    patch.stopall()


def test_the_api_speaks_a_reply_and_serves_its_video(tmp_path: Path) -> None:
    spoken: list[str] = []

    def render(photo: Path, text: str, output: Path) -> None:
        spoken.append(text)
        output.write_bytes(b"mp4")

    client = video_app(tmp_path, render)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Hi"})
        made = client.post("/api/chat/video", json={"turn": 1})
        assert made.json() == {"video": "/api/chat/videos/1"}
        assert spoken == ["You said Hi"]
        video = client.get("/api/chat/videos/1")
        assert video.content == b"mp4" and video.headers["content-type"] == "video/mp4"
        assert client.get("/api/chat/videos/7").status_code == 404
        for turn in (0, 2, -1):  # a prompt, and turns not in the conversation
            missing = client.post("/api/chat/video", json={"turn": turn})
            assert missing.status_code == 404 and missing.json()["detail"] == NO_SUCH_REPLY

    with patch("imageskin.app.load_review", return_value=Review(accepted=False)):
        locked = client.post("/api/chat/video", json={"turn": 1})
    assert locked.status_code == 403 and locked.json()["detail"] == CHAT_LOCKED


def test_replies_are_warmed_up_at_start_once_a_sample_is_accepted(tmp_path: Path) -> None:
    first = video_app(tmp_path, write_text)  # makes the photo; nothing accepted at its start
    assert not (tmp_path / "replies").exists()
    rendered: list[str] = []
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        app = create_app(
            tmp_path,
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=lambda photo, text, output: rendered.append(text),
            ask_llm=lambda messages: "",
        )
        app.state.reply_warm_up.join(5)
    assert rendered == ["Hello."]
    first.close()


def test_the_api_joins_a_streamed_replys_sentence_clips(tmp_path: Path) -> None:
    said: list[str] = []

    def render(photo: Path, text: str, output: Path) -> None:
        said.append(text)
        tone_clip(0.5, output)

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        yield from ["Hi Larry. ", "How are ", "you?"]

    client = video_app(tmp_path, render, stream)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        reply = client.post("/api/chat", json={"prompt": "Hi"}).json()
        assert reply["content"] == "Hi Larry. How are you?"
        made = client.post("/api/chat/video", json={"turn": 1})
        assert made.json() == {"video": "/api/chat/videos/1"}
        assert said == ["Hi Larry.", "How are you?"]  # never the whole reply again
        assert seconds_of(tmp_path / "replies" / "1.mp4") == pytest.approx(1.0, abs=0.1)

        client.post("/api/chat", json={"prompt": "Again"})  # its video is never asked for
        client.post("/api/chat", json={"prompt": "And again"})
        assert client.post("/api/chat/video", json={"turn": 5}).status_code == 200
        assert said[-2:] == ["Hi Larry.", "How are you?"]
        # The unasked-for reply's clips were dropped, and only the latest video is kept.
        assert [p.name for p in (tmp_path / "replies").iterdir()] == ["5.mp4"]


def test_the_api_drops_the_clips_of_a_failed_streamed_reply(tmp_path: Path) -> None:
    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        yield "Hi. "
        raise LlmError("The LLM stopped answering. Try again.")

    client = video_app(tmp_path, write_text, stream)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        failed = client.post("/api/chat", json={"prompt": "Hi"})
    assert failed.status_code == 502
    assert not any((tmp_path / "replies").glob("rendering-*"))


def test_the_api_says_why_a_video_failed(tmp_path: Path) -> None:
    def fail(photo: Path, text: str, output: Path) -> None:
        raise VideoError("ffmpeg is not installed")

    client = video_app(tmp_path, fail)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Hi"})
        failed = client.post("/api/chat/video", json={"turn": 1})
    assert failed.status_code == 502 and failed.json()["detail"] == "ffmpeg is not installed"


def test_the_api_says_when_the_photo_was_removed(tmp_path: Path) -> None:
    client = video_app(tmp_path, write_text)
    patch.object(PrepareJob, "status", return_value=PrepareStatus("done", "gone")).start()
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Hi"})
        removed = client.post("/api/chat/video", json={"turn": 1})
    assert removed.status_code == 409
