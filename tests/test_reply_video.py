import logging
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from imageskin.app import CHAT_LOCKED, NO_SUCH_REPLY, create_app
from imageskin.chat import LlmError
from imageskin.prepare_job import PrepareJob, PrepareStatus
from imageskin.reply_video import ReplyVideos, VoiceReady
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


def test_the_old_video_stays_until_the_new_one_is_in_place(tmp_path: Path) -> None:
    videos = ReplyVideos(tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"))
    first = videos.render(Path("me.jpg"), 1, "Hello")
    assert first is not None
    seen: list[bool] = []

    def render(photo: Path, text: str, output: Path) -> None:
        seen.append(first.exists())  # the browser may still be playing it
        output.write_text(text)

    videos._render_clip = render
    videos.render(Path("me.jpg"), 3, "Again")
    assert seen == [True] and not first.exists()


def test_an_old_video_that_cant_be_removed_doesnt_fail_the_new_one(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    videos = ReplyVideos(tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"))
    first = videos.render(Path("me.jpg"), 1, "Hello")
    assert first is not None
    real_unlink = Path.unlink

    def in_use(path: Path, missing_ok: bool = False) -> None:
        if path == first:  # as on Windows, while the browser has it open
            raise PermissionError("The file is being used by another process")
        real_unlink(path, missing_ok)

    with patch.object(Path, "unlink", in_use):
        second = videos.render(Path("me.jpg"), 3, "Again")
    assert second is not None and second.read_text() == "me.jpg: Again"
    assert first.exists()
    assert "Could not remove an old reply video" in caplog.messages
    videos.render(Path("me.jpg"), 5, "Third")  # removed with the next reply instead
    assert not first.exists()


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


def test_sentences_are_rendered_in_order(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    said: list[str] = []

    def render(photo: Path, text: str, output: Path) -> None:
        said.append(text)
        tone_clip(0.5, output)

    videos = ReplyVideos(tmp_path, render, VoiceReady(lambda: None, lambda: "v"))
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    caplog.set_level(logging.INFO)
    clips(None)  # the LLM starts writing
    for sentence in ["**Hello** there.", "🎉", "See https://example.com now."]:
        clips(sentence)
    assert [clips.done] == [False]  # (a list, so mypy keeps checking what follows)
    clips.close()
    clips.wait(10)
    assert clips.done and clips.error is None
    assert said == ["Hello there.", "See the link in the text below now."]
    folder = tmp_path / "replies" / "clips-abc123ef"
    assert clips.clips == [folder / "1.mp4", folder / "2.mp4"]
    assert seconds_of(clips.clips[0]) == pytest.approx(0.5, abs=0.1)
    ready = [r for r in caplog.records if r.message == "Sentence clip ready"]
    assert [r.sentence for r in ready] == [1, 3]  # type: ignore[attr-defined]
    assert all(r.since_first_words_ms is not None for r in ready)  # type: ignore[attr-defined]


def test_each_clip_records_when_its_sentence_arrived_and_when_it_was_ready(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    videos = ReplyVideos(tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"))
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    caplog.set_level(logging.INFO)
    before = time.perf_counter()
    clips("One.")
    clips("🎉")  # nothing to say: no clip, no time
    clips("Two.")
    clips.close()
    clips.wait(10)
    assert len(clips.times) == len(clips.clips) == 2
    for t in clips.times:
        assert before <= t.sentence_at <= t.ready_at <= time.perf_counter()
    ready = [r for r in caplog.records if r.message == "Sentence clip ready"]
    assert all(r.since_sentence_ms >= 0 for r in ready)  # type: ignore[attr-defined]


def test_waiting_for_a_change_ends_with_the_next_clip_or_the_end(tmp_path: Path) -> None:
    go = threading.Event()

    def render(photo: Path, text: str, output: Path) -> None:
        go.wait(5)
        output.write_text(text)

    videos = ReplyVideos(tmp_path, render, VoiceReady(lambda: None, lambda: "v"))
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    clips("One.")
    start = time.perf_counter()
    clips.wait_for_change(known=0, timeout=0.2)  # nothing yet: waits the whole time
    assert 0.2 <= time.perf_counter() - start < 2 and clips.clips == []

    threading.Timer(0.2, go.set).start()
    start = time.perf_counter()
    clips.wait_for_change(known=0, timeout=5)  # the clip comes 0.2 s in
    assert time.perf_counter() - start < 2 and len(clips.clips) == 1

    clips.close()
    clips.wait_for_change(known=1, timeout=5)  # done, with no more clips
    assert clips.done
    clips.wait_for_change(known=5, timeout=5)  # returns at once when done


def test_waiting_for_a_change_ends_when_a_clip_fails(tmp_path: Path) -> None:
    def fail(photo: Path, text: str, output: Path) -> None:
        raise VideoError("ffmpeg is not installed")

    videos = ReplyVideos(tmp_path, fail, VoiceReady(lambda: None, lambda: "v"))
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    clips("One.")
    start = time.perf_counter()
    clips.wait_for_change(known=0, timeout=5)
    assert time.perf_counter() - start < 2 and clips.error == "ffmpeg is not installed"


def test_a_reply_with_no_sentences_is_done_at_once(tmp_path: Path) -> None:
    videos = ReplyVideos(tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"))
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    clips.close()
    clips.close()  # twice is fine
    assert clips.done and clips.clips == []


def test_a_failed_sentence_stops_the_clips_and_says_why(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def fail(photo: Path, text: str, output: Path) -> None:
        raise VideoError("ffmpeg is not installed")

    videos = ReplyVideos(tmp_path, fail, VoiceReady(lambda: None, lambda: "v"))
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    clips("One.")
    clips("Two.")
    clips.close()
    clips.wait(10)
    assert clips.done and clips.error == "ffmpeg is not installed"
    assert [r.message for r in caplog.records].count("Sentence clip failed") == 1


def test_a_cancelled_reply_stops_and_leaves_no_clips(tmp_path: Path) -> None:
    said: list[str] = []
    videos = ReplyVideos(tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"))
    videos.sentence_clips(Path("me.jpg"), "abc123ef").cancel()  # nothing to stop
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    with videos._lock:  # the engines are busy, so the sentences wait
        clips("One.")
        clips("Two.")
        clips._cancelled = True
    clips.cancel()
    assert said == [] and not clips.folder.exists()


def test_files_left_from_before_a_restart_are_removed(tmp_path: Path) -> None:
    old = tmp_path / "replies" / "clips-abc123ef"
    old.mkdir(parents=True)
    (old / "1.mp4").write_text("old")
    (tmp_path / "replies" / "3.rendering.mp4").write_bytes(b"half")
    (tmp_path / "replies" / "1.mp4").write_bytes(b"video")
    ReplyVideos(tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"))
    assert [p.name for p in (tmp_path / "replies").iterdir()] == ["1.mp4"]


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
        reply = client.post("/api/chat", json={"prompt": "Hi"}).json()
        assert reply == {"role": "assistant", "content": "You said **Hi**", "turn": 1}
        made = client.post("/api/chat/video", json={"turn": reply["turn"]})
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


REPLY_ID = "0123456789abcdef0123456789abcdef"


def test_the_api_serves_a_streamed_replys_clips_as_they_are_made(tmp_path: Path) -> None:
    said: list[str] = []

    def render(photo: Path, text: str, output: Path) -> None:
        said.append(text)
        tone_clip(0.5, output)

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        yield from ["Hi Larry. ", "How are ", "you?"]

    client = video_app(tmp_path, render, stream)
    clips_api = f"/api/chat/clips/{REPLY_ID}"
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        assert client.get(clips_api).status_code == 404  # not asked for yet
        sent = client.post("/api/chat", json={"prompt": "Hi", "reply_id": REPLY_ID})
        assert sent.json()["content"] == "Hi Larry. How are you?"
        status = client.get(clips_api).json()
        while not status["done"]:
            status = client.get(clips_api).json()
        assert [c["url"] for c in status["clips"]] == [f"{clips_api}/1", f"{clips_api}/2"]
        assert status["done"] is True and status["error"] is None
        # Each clip says when its sentence arrived and when it was ready, on the server's clock.
        for clip in status["clips"]:
            assert clip["sentence_at"] <= clip["ready_at"] <= status["now"]
        assert said == ["Hi Larry.", "How are you?"]
        clip = client.get(f"{clips_api}/2")
        assert clip.headers["content-type"] == "video/mp4" and clip.content[4:8] == b"ftyp"
        assert client.get(f"{clips_api}/3").status_code == 404

        other = "f" * 32
        client.post("/api/chat", json={"prompt": "Again", "reply_id": other})
        assert client.get(clips_api).status_code == 404  # only the latest reply's are kept
        assert not (tmp_path / "replies" / f"clips-{REPLY_ID}").exists()
        assert client.post("/api/chat", json={"prompt": "x", "reply_id": "../x"}).status_code == 422


def test_the_api_answers_as_soon_as_there_is_a_new_clip(tmp_path: Path) -> None:
    go = threading.Event()

    def render(photo: Path, text: str, output: Path) -> None:
        go.wait(5)
        output.write_bytes(b"mp4")

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        yield "One. Two."

    client = video_app(tmp_path, render, stream)
    clips_api = f"/api/chat/clips/{REPLY_ID}"
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Hi", "reply_id": REPLY_ID})
        # Nothing rendered yet: a short wait ends with nothing new.
        start = time.perf_counter()
        none_yet = client.get(f"{clips_api}?known=0&wait=0.2").json()
        assert 0.2 <= time.perf_counter() - start < 2 and none_yet["clips"] == []
        assert none_yet["done"] is False
        # Asked to wait for the first clip, the answer comes when it is ready, not later.
        threading.Timer(0.2, go.set).start()
        start = time.perf_counter()
        first = client.get(f"{clips_api}?known=0&wait=10").json()
        assert time.perf_counter() - start < 2 and len(first["clips"]) >= 1
        # Waits longer than allowed, or a count below zero, are refused.
        assert client.get(f"{clips_api}?known=0&wait=60").status_code == 422
        assert client.get(f"{clips_api}?known=-1").status_code == 422
        # Without `known`, the answer comes at once, as before.
        assert client.get(clips_api).status_code == 200


def test_the_engines_leave_the_llm_half_the_cores_while_it_writes(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="imageskin.cores")
    with patch("imageskin.cores.cores", return_value=4), patch("imageskin.cores.set_threads"):
        client = video_app(tmp_path, write_text)
        with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
            client.post("/api/chat", json={"prompt": "Hi"})
    threads = [r.threads for r in caplog.records if r.message == "Engine threads set"]  # type: ignore[attr-defined]
    assert threads == [4, 2, 4]  # all at start, half while the LLM writes, then all again


def test_a_reply_that_isnt_streamed_has_no_clips(tmp_path: Path) -> None:
    client = video_app(tmp_path, write_text)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Hi", "reply_id": REPLY_ID})
        assert client.get(f"/api/chat/clips/{REPLY_ID}").status_code == 404
        assert client.post("/api/chat/video", json={"turn": 1}).status_code == 200


def test_a_prompt_waiting_on_another_drops_that_ones_clips(tmp_path: Path) -> None:
    started, go = threading.Event(), threading.Event()

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        if messages[-1]["content"] == "First":
            started.set()
            go.wait(5)
            yield "One. Two."
        else:
            yield "Hi."

    def post(prompt: str, reply_id: str) -> None:
        client.post("/api/chat", json={"prompt": prompt, "reply_id": reply_id})

    client = video_app(tmp_path, write_text, stream)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        first = threading.Thread(target=post, args=("First", "a" * 8))
        first.start()
        assert started.wait(5)
        second = threading.Thread(target=post, args=("Second", "b" * 8))
        second.start()
        time.sleep(0.2)  # the second prompt is now waiting on the first
        go.set()
        first.join(5)
        second.join(5)
        assert client.get(f"/api/chat/clips/{'a' * 8}").status_code == 404
        assert client.get(f"/api/chat/clips/{'b' * 8}").status_code == 200
    assert not (tmp_path / "replies" / f"clips-{'a' * 8}").exists()


def test_the_api_drops_the_clips_of_a_failed_streamed_reply(tmp_path: Path) -> None:
    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        yield "Hi. "
        raise LlmError("The LLM stopped answering. Try again.")

    client = video_app(tmp_path, write_text, stream)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        failed = client.post("/api/chat", json={"prompt": "Hi", "reply_id": REPLY_ID})
        assert failed.status_code == 502
        assert client.get(f"/api/chat/clips/{REPLY_ID}").status_code == 404
    assert not any((tmp_path / "replies").glob("clips-*"))


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
