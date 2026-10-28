import logging
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from imageskin.app import CHAT_LOCKED, NO_SUCH_REPLY, PROMPT_STOPPED, create_app
from imageskin.chat import Conversation, LlmError
from imageskin.prepare_job import ClipSteps, PrepareJob, PrepareStatus, steps_clip
from imageskin.reply_video import ReplyVideos, SentenceClips, VoiceReady, text_steps
from imageskin.review import Review
from imageskin.ui_settings import save_ui_settings
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


def test_a_forgotten_voice_is_prepared_again() -> None:
    """R31: after Delete my data the next reply prepares the voice again, even with the same id."""
    prepared: list[int] = []
    ready = VoiceReady(lambda: prepared.append(1), lambda: "clone:abc")
    ready.ensure()
    ready.forget()
    ready.ensure()
    assert prepared == [1, 1]


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

    videos._steps = text_steps(render)
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


def idle_steps(made: list[str], fail: bool = False) -> ClipSteps:
    """Clip steps whose engine can make the idle video (R23)."""

    def idle(photo: Path, output: Path) -> None:
        made.append(photo.name)
        if fail:
            output.write_bytes(b"half")
            raise VideoError("ffmpeg stopped")
        output.write_bytes(b"idle")

    def render(photo: Path, wav: Path, output: Path) -> None:
        output.write_bytes(b"mp4")

    return ClipSteps(lambda text, wav: None, render, idle)


def test_warming_up_makes_the_idle_video_once_per_photo(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    made: list[str] = []
    videos = ReplyVideos(
        tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"), idle_steps(made)
    )
    assert videos.idle(Path("me.jpg")) is None
    caplog.set_level(logging.INFO)
    videos.warm_up(Path("me.jpg"))
    videos.warm_up(Path("me.jpg"))  # a second accept: kept
    assert made == ["me.jpg"] and "Idle video ready" in caplog.messages
    idle = videos.idle(Path("me.jpg"))
    assert idle is not None and idle.read_bytes() == b"idle"
    videos.warm_up(Path("you.jpg"))  # another photo prepared: its own, and the old one goes
    assert made == ["me.jpg", "you.jpg"]
    assert [p.name for p in (tmp_path / "replies" / "idle").iterdir()] == ["you.mp4"]
    videos.render(Path("you.jpg"), 1, "Hello")  # a reply's video leaves the idle video be
    videos.render(Path("you.jpg"), 3, "Hello")
    assert videos.idle(Path("you.jpg")) is not None


def test_an_idle_video_that_fails_is_logged_and_left_out(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    made: list[str] = []
    videos = ReplyVideos(
        tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"), idle_steps(made, fail=True)
    )
    videos.warm_up(Path("me.jpg"))
    assert "Could not make the idle video" in caplog.messages
    assert videos.idle(Path("me.jpg")) is None
    assert list((tmp_path / "replies" / "idle").iterdir()) == []  # nothing half made is kept


def test_an_old_idle_video_that_cant_be_removed_is_left_for_later(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    old = tmp_path / "replies" / "idle" / "me.mp4"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"idle")
    videos = ReplyVideos(
        tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"), idle_steps([])
    )
    real_unlink = Path.unlink

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if self == old:
            raise PermissionError("open in the browser")
        real_unlink(self, missing_ok)

    with patch.object(Path, "unlink", unlink):
        videos.warm_up(Path("you.jpg"))
    assert "Could not remove an old idle video" in caplog.messages
    assert videos.idle(Path("you.jpg")) is not None and old.exists()


def test_an_engine_without_an_idle_video_makes_none(tmp_path: Path) -> None:
    videos = ReplyVideos(tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"))
    videos.warm_up(Path("me.jpg"))
    assert videos.idle(Path("me.jpg")) is None


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
    clips.join_words = 0  # each sentence a clip of its own, however they queue
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
    clips.wait_for_change(known=0, timeout=5)  # listed as soon as it is being written (R22d)
    assert time.perf_counter() - start < 2 and len(clips.clips) == 1 and clips.rendered == 0

    start = time.perf_counter()
    clips.wait_for_change(known=1, timeout=0.2)  # nothing more yet: waits the whole time
    assert 0.2 <= time.perf_counter() - start < 2 and len(clips.clips) == 1

    clips("Two.")
    threading.Timer(0.2, go.set).start()
    start = time.perf_counter()
    clips.wait_for_change(known=1, timeout=5)  # the second comes once the first is whole
    assert time.perf_counter() - start < 2 and len(clips.clips) == 2 and clips.rendered >= 1

    clips.close()
    clips.wait_for_change(known=2, timeout=5)  # done, with no more clips
    assert clips.done and clips.rendered == 2
    clips.wait_for_change(known=5, timeout=5)  # returns at once when done


def test_waiting_for_a_change_ends_when_a_clip_fails(tmp_path: Path) -> None:
    def fail(photo: Path, text: str, output: Path) -> None:
        raise VideoError("ffmpeg is not installed")

    videos = ReplyVideos(tmp_path, fail, VoiceReady(lambda: None, lambda: "v"))
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    clips("One.")
    start = time.perf_counter()
    clips.wait_for_change(known=0, timeout=5)  # the clip is listed while it is written...
    clips.wait_for_change(known=1, timeout=5)  # ...and gone once it has failed
    assert time.perf_counter() - start < 2 and clips.error == "ffmpeg is not installed"
    assert clips.clips == [] and clips.times == [] and clips.rendered == 0


def test_a_clip_is_listed_while_it_is_written_and_followed_as_it_grows(tmp_path: Path) -> None:
    half_written = threading.Event()
    go = threading.Event()

    def render(photo: Path, text: str, output: Path) -> None:
        output.write_bytes(b"first half ")
        half_written.set()
        go.wait(5)
        with output.open("ab") as f:
            f.write(b"second half")

    videos = ReplyVideos(tmp_path, render, VoiceReady(lambda: None, lambda: "v"))
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    clips("One.")
    clips.close()
    assert half_written.wait(5)
    assert len(clips.clips) == 1 and clips.rendered == 0
    before, after = time.perf_counter(), clips.times[0].ready_at
    assert clips.times[0].sentence_at <= after <= before  # listed: when writing began

    chunks: list[bytes] = []
    found = clips.clip(1)
    assert found is not None and found[1] is False  # not whole yet
    follower = clips.follow(1, found[0], every=0.01)
    chunks.append(next(follower))  # what there is so far, before the clip is whole
    assert chunks == [b"first half "]
    threading.Timer(0.1, go.set).start()
    chunks.extend(follower)  # the rest as it is written, then the stream ends
    assert b"".join(chunks) == b"first half second half"
    clips.wait(5)
    assert clips.rendered == 1 and clips.done
    assert clips.clip(1) == (found[0], True) and clips.clip(2) is None
    assert list(clips.follow(1, found[0], every=0.01)) == [b"first half second half"]  # at once


def test_following_a_clip_that_fails_ends_with_what_there_was(tmp_path: Path) -> None:
    some_written = threading.Event()
    go = threading.Event()

    def render(photo: Path, text: str, output: Path) -> None:
        output.write_bytes(b"some")
        some_written.set()
        go.wait(5)
        raise VideoError("ffmpeg stopped")

    videos = ReplyVideos(tmp_path, render, VoiceReady(lambda: None, lambda: "v"))
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    clips("One.")
    clips.close()
    assert some_written.wait(5)
    follower = clips.follow(1, clips.folder / "1.mp4", every=0.01)
    assert next(follower) == b"some"
    go.set()
    assert list(follower) == []  # dropped: the stream ends
    clips.wait(5)
    assert clips.error == "ffmpeg stopped" and clips.clips == []
    assert clips.folder.exists() and not (clips.folder / "1.mp4").exists()


def test_a_clip_that_fails_before_its_stream_begins_ends_the_stream(tmp_path: Path) -> None:
    # A review finding: the clip was looked up again when the stream began, and was gone.
    some_written = threading.Event()
    go = threading.Event()

    def render(photo: Path, text: str, output: Path) -> None:
        output.write_bytes(b"some")
        some_written.set()
        go.wait(5)
        raise VideoError("ffmpeg stopped")

    videos = ReplyVideos(tmp_path, render, VoiceReady(lambda: None, lambda: "v"))
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    clips("One.")
    clips.close()
    assert some_written.wait(5)
    found = clips.clip(1)  # what the API looks up before it answers
    assert found is not None
    follower = clips.follow(1, found[0], every=0.01)  # not begun yet
    go.set()
    clips.wait(5)
    assert clips.clips == [] and clips.clip(1) is None
    assert list(follower) == []  # begun after the clip was dropped: it just ends


def test_a_clip_removed_just_before_its_stream_reads_it_ends_the_stream(tmp_path: Path) -> None:
    # A review finding: the clip could be dropped and removed between the stream seeing it
    # listed and opening its file.
    some_written = threading.Event()
    go = threading.Event()

    def render(photo: Path, text: str, output: Path) -> None:
        output.write_bytes(b"some")
        some_written.set()
        go.wait(5)
        raise VideoError("ffmpeg stopped")

    videos = ReplyVideos(tmp_path, render, VoiceReady(lambda: None, lambda: "v"))
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    clips("One.")
    clips.close()
    assert some_written.wait(5)
    found = clips.clip(1)
    assert found is not None
    real_open = Path.open

    def open_after_the_drop(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == found[0] and not go.is_set():  # seen as listed; dropped before it opens
            go.set()
            clips.wait(5)
        return real_open(path, *args, **kwargs)

    with patch.object(Path, "open", open_after_the_drop):
        chunks = list(clips.follow(1, found[0], every=0.01))
    assert chunks == [] and clips.clips == [] and not found[0].exists()


def test_a_failed_clip_a_browser_still_has_open_is_left_and_its_error_kept(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # A review finding: on Windows, removing a clip the browser is reading fails, and that
    # error replaced the video's own.
    def render(photo: Path, text: str, output: Path) -> None:
        output.write_bytes(b"some")
        raise VideoError("ffmpeg stopped")

    real_unlink = Path.unlink

    def unlink(path: Path, missing_ok: bool = False) -> None:
        if path.suffix == ".mp4":
            raise PermissionError("in use by another process")
        real_unlink(path, missing_ok=missing_ok)

    videos = ReplyVideos(tmp_path, render, VoiceReady(lambda: None, lambda: "v"))
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    with patch.object(Path, "unlink", unlink), caplog.at_level(logging.WARNING):
        clips("One.")
        clips.close()
        clips.wait(5)
    assert clips.error == "ffmpeg stopped" and clips.clips == []
    assert (clips.folder / "1.mp4").exists()  # left for the next reply
    assert "Could not remove a video cut short" in caplog.messages
    videos.sentence_clips(Path("me.jpg"), "fedcba98")  # the next reply removes it
    assert not clips.folder.exists()


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


def test_a_failed_clip_leaves_no_file(tmp_path: Path) -> None:
    def half_then_fail(photo: Path, text: str, output: Path) -> None:
        output.write_bytes(b"half")
        raise VideoError("ffmpeg stopped")

    videos = ReplyVideos(tmp_path, half_then_fail, VoiceReady(lambda: None, lambda: "v"))
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    clips("One.")
    clips.close()
    clips.wait(10)
    assert clips.error == "ffmpeg stopped" and clips.clips == []
    assert list(clips.folder.iterdir()) == []


def test_clips_that_cant_be_removed_are_logged_and_removed_with_the_next_reply(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    videos = ReplyVideos(tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"))
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    clips("One.")
    clips("Two.")
    clips.close()
    clips.wait(10)
    first, second = clips.clips
    real_unlink = Path.unlink

    def in_use(path: Path, missing_ok: bool = False) -> None:
        if path == first:  # as on Windows, while the browser has it open
            raise PermissionError("The file is being used by another process")
        real_unlink(path, missing_ok)

    with patch.object(Path, "unlink", in_use):
        clips.cancel()
    assert first.exists() and not second.exists()
    # Only this module's: a wiki job another test left running may warn meanwhile.
    [left] = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and r.name == "imageskin.reply_video"
    ]
    assert left.message == "Could not remove a reply's clip"
    assert left.clip == "clips-abc123ef/1.mp4"  # type: ignore[attr-defined]
    videos.sentence_clips(Path("me.jpg"), "0123abcd")  # removed with the next reply instead
    assert not clips.folder.exists()


def test_a_cancelled_reply_stops_and_leaves_no_clips(tmp_path: Path) -> None:
    said: list[str] = []
    videos = ReplyVideos(tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"))
    videos.sentence_clips(Path("me.jpg"), "abc123ef").cancel()  # nothing to stop
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    with videos._voice_lock:  # the voice engine is busy, so the sentences wait
        clips("One.")
        clips("Two.")
        clips._cancelled = True
    clips.cancel()
    assert said == [] and not clips.folder.exists()


def test_the_voice_waits_once_every_sentence_given_is_made(tmp_path: Path) -> None:
    """R100: the reply's text is cut at a clause only while every clip so far is made."""
    videos = ReplyVideos(tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"))
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    assert clips.voice_waiting()  # nothing given yet
    with videos._voice_lock:  # the engines are busy, so the sentence waits
        clips("One.")
        assert not clips.voice_waiting()
    for _ in range(200):
        if clips.voice_waiting():
            break
        time.sleep(0.01)
    assert clips.voice_waiting() and clips.rendered == 1
    clips("🎉")  # nothing to say aloud still counts as made
    clips.close()
    clips.wait(10)
    assert clips.voice_waiting()
    clips.cancel()
    assert not clips.voice_waiting()  # a stopped reply isn't cut any more


def test_a_reply_cancelled_while_it_is_spoken_renders_no_video(tmp_path: Path) -> None:
    """The regression for a review finding: a reply cancelled while its sentence was being
    spoken went on to render that sentence's video before the newer prompt could start."""
    speaking, go = threading.Event(), threading.Event()
    rendered: list[str] = []
    wavs: list[Path] = []

    def speak(text: str, wav: Path) -> None:
        speaking.set()
        go.wait(5)
        wav.write_text(text)
        wav.with_suffix(".json").write_text("{}")
        wavs.append(wav)

    def render(photo: Path, wav: Path, output: Path) -> None:
        rendered.append(wav.read_text())

    videos = ReplyVideos(
        tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"), ClipSteps(speak, render)
    )
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    clips("One.")
    assert speaking.wait(5)
    cancelling = threading.Thread(target=clips.cancel)
    cancelling.start()
    time.sleep(0.1)
    assert cancelling.is_alive()  # waiting for the voice step
    go.set()
    cancelling.join(5)
    assert not cancelling.is_alive() and rendered == [] and clips.clips == []
    assert wavs and not any(w.exists() or w.with_suffix(".json").exists() for w in wavs)


def test_each_clip_is_spoken_and_then_rendered(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The two steps (R22b) run in turn: on a 4-core CPU, speaking a sentence while the one
    before it is rendered slowed both down, so there is one thread."""
    steps_done: list[tuple[str, str]] = []

    def speak(text: str, wav: Path) -> None:
        wav.write_text(text)
        wav.with_suffix(".json").write_text("{}")
        steps_done.append(("voice", text))

    def render(photo: Path, wav: Path, output: Path) -> float | None:
        output.write_bytes(wav.read_bytes())
        steps_done.append(("video", wav.read_text()))
        return -20.0 if wav.read_text() == "One." else None  # the engine's measured lead

    videos = ReplyVideos(
        tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"), ClipSteps(speak, render)
    )
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    clips.join_words = 0  # each sentence a clip of its own, however they queue
    caplog.set_level(logging.INFO)
    for sentence in ["One.", "🎉", "Two."]:
        clips(sentence)
    clips.close()
    clips.wait(10)
    assert clips.done and clips.error is None
    assert steps_done == [
        ("voice", "One."),
        ("video", "One."),
        ("voice", "Two."),
        ("video", "Two."),
    ]
    assert [p.read_bytes() for p in clips.clips] == [b"One.", b"Two."]
    assert not list(clips.folder.glob("*.wav")) and not list(clips.folder.glob("*.json"))
    spoken = [r for r in caplog.records if r.message == "Sentence spoken"]
    assert [(r.sentence, r.chars) for r in spoken] == [(1, 4), (3, 4)]  # type: ignore[attr-defined]
    ready = [r for r in caplog.records if r.message == "Sentence clip ready"]
    assert [r.sentence for r in ready] == [1, 3]  # type: ignore[attr-defined]
    # Each clip's lead of the mouth over the voice (roadmap R128).
    assert [r.mouth_lead_ms for r in ready] == [-20.0, None]  # type: ignore[attr-defined]


def test_a_failed_voice_step_stops_the_clips_and_says_why(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    rendered: list[str] = []

    def speak(text: str, wav: Path) -> None:
        raise VideoError("the voice model is missing")

    def render(photo: Path, wav: Path, output: Path) -> None:
        rendered.append(wav.read_text())

    videos = ReplyVideos(
        tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"), ClipSteps(speak, render)
    )
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    clips("One.")
    clips("Two.")
    clips.close()
    clips.wait(10)
    assert clips.done and clips.error == "the voice model is missing" and rendered == []
    failed = [r for r in caplog.records if r.message == "Sentence clip failed"]
    assert [(r.sentence, r.step) for r in failed] == [(1, "voice")]  # type: ignore[attr-defined]


def test_the_two_steps_make_one_clip_for_the_prepare_job(tmp_path: Path) -> None:
    def speak(text: str, wav: Path) -> None:
        wav.write_text(text)
        wav.with_suffix(".json").write_text("{}")

    def render(photo: Path, wav: Path, output: Path) -> None:
        assert wav.with_suffix(".json").is_file()
        output.write_text(f"{photo.name}: {wav.read_text()}")

    steps_clip(ClipSteps(speak, render))(Path("me.jpg"), "Hello.", tmp_path / "hello.mp4")
    assert (tmp_path / "hello.mp4").read_text() == "me.jpg: Hello."


def test_the_thread_that_runs_the_engines_is_told_first(tmp_path: Path) -> None:
    """Before each clip, on the thread that renders it (R22a: PyTorch's count is per thread)."""
    told: list[str] = []

    def before_engines() -> None:
        told.append(threading.current_thread().name)

    videos = ReplyVideos(
        tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"), before_engines=before_engines
    )
    videos.warm_up(Path("me.jpg"))
    videos.render(Path("me.jpg"), 1, "Hello.")
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    clips("One.")
    clips("🎉")  # nothing to say: the engines aren't used
    clips("Two.")
    clips.close()
    clips.wait(10)
    main = threading.current_thread().name
    assert told == [main, main, "sentence-clips", "sentence-clips"]


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


def video_app(
    tmp_path: Path,
    render: object,
    stream: object = None,
    steps: ClipSteps | None = None,
    **kw: Any,  # more of create_app's, such as another ask_llm (R96a)
) -> TestClient:
    kw.setdefault("ask_llm", lambda messages: f"You said **{messages[-1]['content']}**")
    client = TestClient(
        create_app(
            tmp_path,
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=render,  # type: ignore[arg-type]
            stream_llm=stream,  # type: ignore[arg-type]
            clip_steps=steps,
            **kw,
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
        assert reply.pop("timings")["llm"] is None  # where the time went (R96)
        assert reply == {
            "role": "assistant",
            "content": "You said **Hi**",
            "turn": 1,
            "streamed": False,
            "lesson": None,  # no lesson going (R41h)
            "choices": [],
            "quiz": None,
            "assessment": None,
        }
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


def test_the_sample_keeps_the_photos_size_and_only_reply_clips_are_scaled_down(
    tmp_path: Path,
) -> None:
    # A review finding: the sample went through the reply clips' scaled-down engine too.
    made: list[int | None] = []
    rendered: list[int | None] = []
    movements: list[str] = []  # the face movement each clip is rendered with (R128a)

    def steps(
        home: Path,
        engine: object,
        voice: str = "",
        max_side: int | None = None,
        progressive: bool = False,
        face_movement: Callable[[], str] = lambda: "unset",
    ) -> object:
        made.append(max_side)
        assert progressive == (max_side is not None)  # only reply clips play while written

        def speak(text: str, wav: Path) -> None:
            wav.write_bytes(b"wav")

        def render(photo: Path, wav: Path, output: Path) -> None:
            rendered.append(max_side)
            movements.append(face_movement())
            tone_clip(0.2, output)

        return ClipSteps(speak, render)

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        yield from ["Hi Larry. ", "How are you?"]

    with patch("imageskin.app.photoreal_steps", steps):
        client = video_app(tmp_path, None, stream)
    assert sorted(made, key=str) == [720, None]  # an engine each, for the sample and replies
    photo = tmp_path / "me.jpg"
    job = client.app.state.prepare_job  # type: ignore[attr-defined]
    job._status = PrepareStatus("running", face_movement="normal")  # prepared with Normal
    job._render_clip(photo, "Hello.", tmp_path / "sample.mp4")
    assert rendered == [None]  # the sample, at the photo's own size
    # Chosen after the sample was made: replies keep the prepared one until Prepare again.
    save_ui_settings(tmp_path, {"face_movement": "slight"})
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Hi", "reply_id": REPLY_ID})
        while not client.get(f"/api/chat/clips/{REPLY_ID}").json()["done"]:
            time.sleep(0.01)
        client.post("/api/chat/video", json={"turn": 1})
    assert rendered[1:] == [720, 720, 720]  # two reply clips and a reply in one video
    assert movements == ["normal"] * 4


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


def test_replies_are_warmed_up_when_the_sample_is_accepted(tmp_path: Path) -> None:
    """A first-time setup accepts its sample without a restart: the warm-up runs then (a review
    finding on R22a), so the first prompt is not cold."""
    rendered: list[str] = []
    client = video_app(tmp_path, lambda photo, text, output: rendered.append(text))
    assert rendered == []  # nothing accepted when the app started
    assert client.post("/api/review", json={"decision": "accept"}).status_code == 200
    client.app.state.reply_warm_up.join(5)  # type: ignore[attr-defined]
    assert rendered == ["Hello."]


def test_a_change_of_person_during_a_warm_up_is_warmed_up_after_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Larry's test of R32a: a default person chosen while the last one's warm-up still ran kept
    the last one's idle video, as the second warm-up was dropped."""
    warming, finish = threading.Event(), threading.Event()
    photos: list[str] = []

    def render(photo: Path, text: str, output: Path) -> None:
        photos.append(photo.name)
        warming.set()
        finish.wait(5)

    client = video_app(tmp_path, render)
    assert client.post("/api/review", json={"decision": "accept"}).status_code == 200
    assert warming.wait(5)
    first = client.app.state.reply_warm_up  # type: ignore[attr-defined]
    other = client.post("/api/uploads/photos", files={"file": ("other.jpg", JPG)}).json()
    done = PrepareStatus("done", photo_id=other["id"])
    with caplog.at_level(logging.INFO), patch.object(PrepareJob, "status", return_value=done):
        assert client.post("/api/review", json={"decision": "accept"}).status_code == 200
        # Prompts still wait for the same thread.
        assert client.app.state.reply_warm_up is first  # type: ignore[attr-defined]
        finish.set()
        first.join(5)
    assert len(photos) == 2 and photos[0] != photos[1]  # again, for the new photo
    assert "Warming up replies again for the person chosen meanwhile" in caplog.messages


class HoldAt(logging.Handler):
    """Holds the thread that logs `message` until the test lets it go, after telling the test."""

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message, self.reached, self.go = message, threading.Event(), threading.Event()

    # handle(), not emit(): emit runs under the handler's lock, which would hold every other
    # thread's log lines too.
    def handle(self, record: logging.LogRecord) -> bool:
        if record.getMessage() == self.message and not self.reached.is_set():
            self.reached.set()
            self.go.wait(5)
        return True

    def emit(self, record: logging.LogRecord) -> None:
        pass


def test_a_person_chosen_as_the_last_warm_up_ends_gets_a_warm_up_of_their_own(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Review on PR #122: a person chosen after the worker decided to stop, while its thread was
    still ending, was neither warmed up by it nor by a new one."""
    photos: list[str] = []
    client = video_app(tmp_path, lambda photo, text, output: photos.append(photo.name))
    hold = HoldAt("Reply warm-up done")
    caplog.set_level(logging.INFO, logger="imageskin.app")
    logging.getLogger("imageskin.app").addHandler(hold)
    try:
        assert client.post("/api/review", json={"decision": "accept"}).status_code == 200
        assert hold.reached.wait(5)  # stopped, but its thread still alive
        first = client.app.state.reply_warm_up  # type: ignore[attr-defined]
        assert first.is_alive()
        other = client.post("/api/uploads/photos", files={"file": ("other.jpg", JPG)}).json()
        done = PrepareStatus("done", photo_id=other["id"])
        with patch.object(PrepareJob, "status", return_value=done):
            assert client.post("/api/review", json={"decision": "accept"}).status_code == 200
            second = client.app.state.reply_warm_up  # type: ignore[attr-defined]
            assert second is not first  # a worker of its own
            hold.go.set()
            second.join(5)
            first.join(5)
    finally:
        logging.getLogger("imageskin.app").removeHandler(hold)
    assert len(photos) == 2 and photos[0] != photos[1]


def test_two_quick_changes_warm_up_only_the_last_person_once_more(tmp_path: Path) -> None:
    """A to B to C during A's warm-up: C is warmed up once after it, B never."""
    warming, finish = threading.Event(), threading.Event()
    photos: list[str] = []

    def render(photo: Path, text: str, output: Path) -> None:
        photos.append(photo.name)
        warming.set()
        finish.wait(5)

    client = video_app(tmp_path, render)
    assert client.post("/api/review", json={"decision": "accept"}).status_code == 200
    assert warming.wait(5)
    first = client.app.state.reply_warm_up  # type: ignore[attr-defined]
    for name in ("b.jpg", "c.jpg"):
        chosen = client.post("/api/uploads/photos", files={"file": (name, JPG)}).json()
        done = PrepareStatus("done", photo_id=chosen["id"])
        patch.object(PrepareJob, "status", return_value=done).start()
        assert client.post("/api/review", json={"decision": "accept"}).status_code == 200
    c_photo = UploadStore(tmp_path).path("photos", chosen["id"])
    assert c_photo is not None
    finish.set()
    first.join(5)
    assert client.app.state.reply_warm_up is first  # type: ignore[attr-defined]
    assert len(photos) == 2 and photos[1] == c_photo.name


def test_the_api_serves_the_idle_video_once_the_warm_up_made_it(tmp_path: Path) -> None:
    made: list[str] = []
    client = video_app(tmp_path, None, steps=idle_steps(made))
    assert client.get("/api/chat/idle").status_code == 404  # nothing accepted: no warm-up yet
    assert client.post("/api/review", json={"decision": "accept"}).status_code == 200
    idle = client.get("/api/chat/idle")  # waits for the warm-up that makes it
    assert idle.status_code == 200 and idle.content == b"idle" and len(made) == 1
    assert idle.headers["content-type"] == "video/mp4"


def test_the_first_prompt_after_accepting_waits_for_the_warm_up(tmp_path: Path) -> None:
    """The regression for a review finding: a prompt sent as soon as the sample is accepted
    used to reach the LLM while its warm-up was still reading the system prompt, and the
    engines while they rendered their first word."""
    order: list[str] = []
    warming, finish = threading.Event(), threading.Event()

    def warm_up_llm() -> None:
        warming.set()
        finish.wait(5)
        order.append("LLM warmed up")

    def ask(messages: list[dict[str, str]]) -> str:
        order.append("asked")
        return "Hi."

    client = TestClient(
        create_app(
            tmp_path,
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=lambda photo, text, output: order.append(f"rendered {text}"),
            ask_llm=ask,
            warm_up_llm=warm_up_llm,
        )
    )
    client.app.state.reply_warm_up.join(5)  # type: ignore[attr-defined]
    client.post("/api/consent", json={"agreed": True})
    photo = client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)}).json()
    done = PrepareStatus("done", photo_id=photo["id"])
    patch.object(PrepareJob, "status", return_value=done).start()
    patch.object(UploadStore, "voice_sample", return_value=VoiceSample(2, 40, 35, None)).start()
    assert order == []
    assert client.post("/api/review", json={"decision": "accept"}).status_code == 200
    assert warming.wait(5)  # the warm-up is under way when the prompt comes
    # Accepting again meanwhile keeps the warm-up that is running as the one prompts wait
    # for, rather than starting another that would do nothing (a review finding).
    assert client.post("/api/review", json={"decision": "accept"}).status_code == 200
    answers: list[int] = []
    replies: list[dict[str, Any]] = []

    def send() -> None:
        sent = client.post("/api/chat", json={"prompt": "Hi"})
        answers.append(sent.status_code)
        replies.append(sent.json())

    prompt = threading.Thread(target=send)
    prompt.start()
    time.sleep(0.3)
    assert order == ["rendered Hello."] and answers == []  # the prompt waits for the LLM's
    time.sleep(0.7)
    assert order == ["rendered Hello."] and answers == []  # ...however long it takes (no cap)
    finish.set()
    prompt.join(5)
    assert answers == [200]
    assert order == ["rendered Hello.", "LLM warmed up", "asked"]  # and warmed up once
    # Each part of the warm-up is timed for time-startup (R96c).
    parts = {p["name"] for p in client.get("/api/startup").json()["parts"]}
    assert {"app made", "reply warm-up", "LLM warm-up", "voice and video warm-up"} <= parts
    # R134c: the wait is a step of the thinking, with the warm-up's part it waited for.
    steps = {s["step"]: s for s in replies[0]["timings"]["steps"]}
    wait = steps["waiting for the warm-up"]
    assert wait["duration_ms"] >= 900 and wait["start_ms"] >= 0
    llm = steps["warm-up: LLM reading the system prompt"]
    assert wait["start_ms"] <= llm["start_ms"] <= llm["end_ms"] <= wait["end_ms"]
    assert llm["duration_ms"] >= 900  # the LLM's warm-up is what it waited for


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
        assert sent.json()["streamed"] is True
        status = client.get(clips_api).json()
        while not status["done"]:
            status = client.get(clips_api).json()
        assert [c["url"] for c in status["clips"]] == [f"{clips_api}/1", f"{clips_api}/2"]
        assert status["done"] is True and status["error"] is None
        # Each clip says when its sentence arrived and when it was ready, on the server's clock.
        for clip in status["clips"]:
            assert clip["sentence_at"] <= clip["ready_at"] <= status["now"]
            # R96: and when its voice began and when its video was whole.
            assert clip["sentence_at"] <= clip["started_at"] <= clip["ready_at"]
            assert clip["ready_at"] <= clip["whole_at"] <= status["now"]
        # R96: the reply comes with where its time went, on the same clock.
        times = sent.json()["timings"]
        assert times["waited_turn_ms"] >= 0 and times["llm"] is None
        assert times["received_at"] <= times["prompt_sent_at"] <= times["first_token_at"]
        assert times["first_token_at"] <= times["first_sentence_at"] <= times["last_token_at"]
        assert times["last_token_at"] <= times["answered_at"]
        assert status["clips"][0]["sentence_at"] >= times["first_sentence_at"]
        # R134c: every step of the thinking, with its start, end and duration.
        # Under load, a wait for the LLM to be free can come first.
        steps = [s["step"] for s in times["steps"] if not s["step"].startswith("waiting")]
        assert steps[:4] == [
            "searching the PDFs and the wiki",
            "LLM reading the prompt",
            "LLM writing the first sentence",
            "LLM writing the rest of the reply",
        ]
        for step in times["steps"]:
            assert 0 <= step["start_ms"] <= step["end_ms"]
            assert step["duration_ms"] == pytest.approx(step["end_ms"] - step["start_ms"], abs=0.2)
        assert said == ["Hi Larry.", "How are you?"]
        clip = client.get(f"{clips_api}/2")
        assert clip.headers["content-type"] == "video/mp4" and clip.content[4:8] == b"ftyp"
        assert client.get(f"{clips_api}/3").status_code == 404

        other = "f" * 32
        client.post("/api/chat", json={"prompt": "Again", "reply_id": other})
        assert client.get(clips_api).status_code == 404  # only the latest reply's are kept
        assert not (tmp_path / "replies" / f"clips-{REPLY_ID}").exists()
        assert client.post("/api/chat", json={"prompt": "x", "reply_id": "../x"}).status_code == 422


def test_the_first_clips_voice_and_video_are_steps_of_the_thinking(tmp_path: Path) -> None:
    """R134c: when the first sentence's clip has started by the time the reply is written, its
    wait for the voice and its voice and first video are steps too."""
    rendering = threading.Event()

    def render(photo: Path, text: str, output: Path) -> None:
        rendering.set()
        tone_clip(0.5, output)

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        yield "Hi Larry. Bye"  # the first sentence ends where the next begins
        assert rendering.wait(5)  # the first clip's video is being written
        yield " now."

    client = video_app(tmp_path, render, stream)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        sent = client.post("/api/chat", json={"prompt": "Hi", "reply_id": REPLY_ID})
    steps = {s["step"]: s for s in sent.json()["timings"]["steps"]}
    waited = steps["first sentence waiting for the voice"]
    spoken = steps["first sentence spoken and its video started"]
    assert waited["end_ms"] == spoken["start_ms"] <= spoken["end_ms"]
    assert waited["start_ms"] >= steps["LLM writing the first sentence"]["start_ms"]


def test_a_prompt_behind_another_has_its_wait_as_a_step(tmp_path: Path) -> None:
    """R134c: the time a prompt waits for the LLM to be free is a step of its thinking."""
    asking, answer = threading.Event(), threading.Event()

    def ask(messages: list[dict[str, str]]) -> str:
        if not asking.is_set():
            asking.set()
            assert answer.wait(5)
        return "Hi."

    client = video_app(tmp_path, lambda photo, text, output: None, ask_llm=ask)
    replies: list[dict[str, Any]] = []
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        first = threading.Thread(target=lambda: client.post("/api/chat", json={"prompt": "Hi"}))
        first.start()
        assert asking.wait(5)
        second = threading.Thread(
            target=lambda: replies.append(client.post("/api/chat", json={"prompt": "Yo"}).json())
        )
        second.start()
        time.sleep(0.2)
        answer.set()
        first.join(5)
        second.join(5)
    [waited] = [s for s in replies[0]["timings"]["steps"] if s["step"].startswith("waiting for")]
    assert waited["step"] == "waiting for the LLM to be free" and waited["duration_ms"] >= 150


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
        # The first clip is listed as soon as it is being written (R22d), so the answer
        # comes at once; its second is not yet, so a short wait for it ends with nothing new.
        start = time.perf_counter()
        first = client.get(f"{clips_api}?known=0&wait=5").json()
        assert time.perf_counter() - start < 2 and len(first["clips"]) == 1
        start = time.perf_counter()
        none_yet = client.get(f"{clips_api}?known=1&wait=0.2").json()
        assert 0.2 <= time.perf_counter() - start < 2 and len(none_yet["clips"]) == 1
        assert none_yet["done"] is False
        # Asked to wait for the second clip, the answer comes when it is listed, not later.
        threading.Timer(0.2, go.set).start()
        start = time.perf_counter()
        second = client.get(f"{clips_api}?known=1&wait=10").json()
        assert time.perf_counter() - start < 2 and len(second["clips"]) == 2
        # Waits longer than allowed, or a count below zero, are refused.
        assert client.get(f"{clips_api}?known=0&wait=60").status_code == 422
        assert client.get(f"{clips_api}?known=-1").status_code == 422
        # Without `known`, the answer comes at once, as before.
        assert client.get(clips_api).status_code == 200


def test_the_api_streams_a_clip_while_it_is_still_being_written(tmp_path: Path) -> None:
    half_written = threading.Event()
    go = threading.Event()

    def render(photo: Path, text: str, output: Path) -> None:
        output.write_bytes(b"first half ")
        half_written.set()
        go.wait(5)
        with output.open("ab") as f:
            f.write(b"second half")

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        yield "One."

    client = video_app(tmp_path, render, stream)
    clips_api = f"/api/chat/clips/{REPLY_ID}"
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Hi", "reply_id": REPLY_ID})
        assert half_written.wait(5)
        assert len(client.get(clips_api).json()["clips"]) == 1
        threading.Timer(0.3, go.set).start()
        start = time.perf_counter()
        with client.stream("GET", f"{clips_api}/1") as r:
            assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"
            assert "content-length" not in r.headers  # as much as there is, then the rest
            body = b"".join(r.iter_bytes())  # (the test client gathers the chunks)
        assert body == b"first half second half"  # the rest followed once it was written
        assert 0.3 <= time.perf_counter() - start < 2
        # Whole, the clip is served as a file, with its length.
        whole = client.get(f"{clips_api}/1")
        assert whole.content == b"first half second half" and "content-length" in whole.headers


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
        sent = client.post("/api/chat", json={"prompt": "Hi", "reply_id": REPLY_ID})
        assert sent.json()["streamed"] is False
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


def test_a_newer_prompt_takes_the_clips_of_a_reply_still_being_rendered(tmp_path: Path) -> None:
    """As when another tab sends a prompt: the first reply's clips go, and its browser knows
    from `streamed` not to ask for the whole reply as one video instead."""
    rendering, go = threading.Event(), threading.Event()

    def render(photo: Path, text: str, output: Path) -> None:
        if text == "One.":
            rendering.set()
            go.wait(5)
        write_text(photo, text, output)

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        yield "One. Two." if messages[-1]["content"] == "First" else "Hi."

    answers: dict[str, dict[str, object]] = {}

    def post(prompt: str, reply_id: str) -> None:
        sent = client.post("/api/chat", json={"prompt": prompt, "reply_id": reply_id})
        answers[prompt] = sent.json()

    client = video_app(tmp_path, render, stream)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        post("First", "a" * 8)  # answered while its first clip is still being rendered
        assert rendering.wait(5) and answers["First"]["streamed"] is True
        second = threading.Thread(target=post, args=("Second", "b" * 8))
        second.start()
        time.sleep(0.2)  # the second prompt is now waiting on the first reply's clip
        assert client.get(f"/api/chat/clips/{'a' * 8}").status_code == 404
        go.set()
        second.join(5)
        assert client.get(f"/api/chat/clips/{'b' * 8}").status_code == 200
    assert not (tmp_path / "replies" / f"clips-{'a' * 8}").exists()


def test_a_waiting_clips_request_does_not_answer_with_clips_a_newer_prompt_took(
    tmp_path: Path,
) -> None:
    """The regression for a review finding: a request waiting for the next clip used to answer
    with it when it was rendered, though a newer prompt had taken the reply's clips meanwhile,
    so the browser was given a clip whose file was being removed."""
    rendering, go = threading.Event(), threading.Event()

    def render(photo: Path, text: str, output: Path) -> None:
        if text == "One.":
            rendering.set()
            go.wait(5)
        write_text(photo, text, output)

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        yield "One. Two." if messages[-1]["content"] == "First" else "Hi."

    answers: dict[str, int] = {}

    def post(prompt: str, reply_id: str) -> None:
        answers[prompt] = client.post(
            "/api/chat", json={"prompt": prompt, "reply_id": reply_id}
        ).status_code

    def wait_for_clips() -> None:
        # The first clip is listed while it is written (R22d): wait for the second, or the end.
        answers["waiting"] = client.get(f"/api/chat/clips/{'a' * 8}?known=1&wait=10").status_code

    client = video_app(tmp_path, render, stream)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        post("First", "a" * 8)
        assert rendering.wait(5)
        waiting = threading.Thread(target=wait_for_clips)
        waiting.start()  # waits while the first clip is still being rendered
        second = threading.Thread(target=post, args=("Second", "b" * 8))
        second.start()
        # Until the second prompt has taken the first reply's clips: a fixed 0.2 s wasn't
        # always enough on CI.
        for _ in range(250):
            if client.get(f"/api/chat/clips/{'a' * 8}").status_code == 404:
                break
            time.sleep(0.02)
        go.set()  # the first clip is rendered now; the reply ends, and wakes the waiting request
        waiting.join(5)
        second.join(5)
    assert answers == {"First": 200, "waiting": 404, "Second": 200}


def test_stopping_a_reply_ends_its_clips_but_not_its_text(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Roadmap R19: Stop drops the reply's clips, the one being rendered included, while the
    LLM's text still comes."""
    rendering, go = threading.Event(), threading.Event()
    rendered: list[str] = []

    def render(photo: Path, text: str, output: Path) -> None:
        rendering.set()
        go.wait(5)
        write_text(photo, text, output)
        rendered.append(text)

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        yield from ["One. ", "Two. ", "Three."]

    caplog.set_level(logging.INFO, logger="imageskin.app")
    client = video_app(tmp_path, render, stream)
    clips_api = f"/api/chat/clips/{REPLY_ID}"
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        sent = client.post("/api/chat", json={"prompt": "Count", "reply_id": REPLY_ID})
        assert sent.json()["content"] == "One. Two. Three."  # the text is all there
        assert rendering.wait(5)
        start = time.perf_counter()
        stopped = client.post(f"{clips_api}/stop")
        assert stopped.json() == {"stopped": True}
        assert time.perf_counter() - start < 2  # answered without waiting for the render
        assert client.get(clips_api).status_code == 404
        go.set()
        folder = tmp_path / "replies" / f"clips-{REPLY_ID}"
        deadline = time.perf_counter() + 5
        while folder.exists() and time.perf_counter() < deadline:
            time.sleep(0.02)
        assert not folder.exists()
        assert rendered == ["One."]  # the clip under way finished; Two and Three never began
        # Stopped again, or a reply with clips no more: nothing to stop.
        assert client.post(f"{clips_api}/stop").json() == {"stopped": False}
        assert client.post("/api/chat/clips/XYZ12345/stop").status_code == 422
    messages = [r.message for r in caplog.records]
    assert "Reply stopped" in messages
    deadline = time.perf_counter() + 5
    while "Reply clips stopped" not in [r.message for r in caplog.records]:
        assert time.perf_counter() < deadline
        time.sleep(0.02)
    [done] = [r for r in caplog.records if r.message == "Reply clips stopped"]
    assert done.duration_ms >= 0  # type: ignore[attr-defined]


def test_stop_answers_a_request_waiting_for_the_next_clip_at_once(tmp_path: Path) -> None:
    """The regression for a review finding: a request waiting for the next clip waited until
    the clip being rendered was done, or its 10 seconds ran out, after Stop."""
    rendering, go = threading.Event(), threading.Event()

    def render(photo: Path, text: str, output: Path) -> None:
        rendering.set()
        go.wait(5)
        write_text(photo, text, output)

    client = video_app(tmp_path, render, lambda messages: iter(["One. Two."]))
    clips_api = f"/api/chat/clips/{REPLY_ID}"
    answers: dict[str, float] = {}

    def wait_for_clips() -> None:
        start = time.perf_counter()
        status = client.get(f"{clips_api}?known=1&wait=10").status_code
        answers["status"], answers["after"] = status, time.perf_counter() - start

    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Count", "reply_id": REPLY_ID})
        assert rendering.wait(5)
        waiting = threading.Thread(target=wait_for_clips)
        waiting.start()
        time.sleep(0.2)  # waiting for clip 2, while clip 1 is still being rendered
        client.post(f"{clips_api}/stop")
        waiting.join(5)
        go.set()
    assert answers["status"] == 404 and answers["after"] < 2


def test_stop_skips_the_video_step_of_a_reply_spoken_in_one_video(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The regression for a review finding: Stop only discarded a reply's one video once it
    was made, holding the engines (and the chat page) for the whole render."""
    speaking, go = threading.Event(), threading.Event()
    rendered: list[str] = []

    def speak(text: str, wav: Path) -> None:
        speaking.set()
        go.wait(5)
        wav.write_text(text)

    def render(photo: Path, wav: Path, output: Path) -> None:
        rendered.append(wav.read_text())
        output.write_text("video")

    caplog.set_level(logging.INFO, logger="imageskin.reply_video")
    client = video_app(tmp_path, write_text, steps=ClipSteps(speak, render))
    answers: dict[str, object] = {}

    def ask_for_video() -> None:
        answers["video"] = client.post(
            "/api/chat/video", json={"turn": 1, "reply_id": REPLY_ID}
        ).json()

    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Hi", "reply_id": REPLY_ID})  # not streamed
        making = threading.Thread(target=ask_for_video)
        making.start()
        assert speaking.wait(5)
        stopped = client.post(f"/api/chat/clips/{REPLY_ID}/stop")
        assert stopped.json() == {"stopped": True}
        go.set()
        making.join(5)
        assert answers["video"] == {"video": None} and rendered == []
        assert not (tmp_path / "replies" / "1.mp4").exists()
        # Stopped again once it is over: nothing to stop. The next reply's video is made.
        assert client.post(f"/api/chat/clips/{REPLY_ID}/stop").json() == {"stopped": False}
        other = "f" * 32
        made = client.post("/api/chat/video", json={"turn": 1, "reply_id": other}).json()
        assert made == {"video": "/api/chat/videos/1"} and rendered == ["You said Hi"]
    [log] = [r for r in caplog.records if r.message == "Reply video stopped"]
    assert log.step == "after voice"  # type: ignore[attr-defined]


def test_a_video_stopped_during_its_video_step_is_dropped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The regression for a review finding: a Stop during the video step let the finished
    video be published as the reply's, replacing the one before it."""
    rendering, go = threading.Event(), threading.Event()

    def render(photo: Path, wav: Path, output: Path) -> None:
        output.write_text("half")
        rendering.set()
        go.wait(5)
        output.write_text("video")

    caplog.set_level(logging.INFO, logger="imageskin.reply_video")
    client = video_app(tmp_path, write_text, steps=ClipSteps(write_text_wav, render))
    earlier = tmp_path / "replies" / "0.mp4"  # the reply before, still playable
    earlier.parent.mkdir(parents=True, exist_ok=True)
    earlier.write_text("earlier")
    answers: dict[str, object] = {}

    def ask_for_video() -> None:
        answers["video"] = client.post(
            "/api/chat/video", json={"turn": 1, "reply_id": REPLY_ID}
        ).json()

    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Hi", "reply_id": REPLY_ID})
        making = threading.Thread(target=ask_for_video)
        making.start()
        assert rendering.wait(5)
        assert client.post(f"/api/chat/clips/{REPLY_ID}/stop").json() == {"stopped": True}
        go.set()
        making.join(5)
    assert answers["video"] == {"video": None}
    assert sorted(p.name for p in (tmp_path / "replies").iterdir()) == ["0.mp4"]
    messages = [r.message for r in caplog.records]
    assert "Rendered reply video" not in messages
    [log] = [r for r in caplog.records if r.message == "Reply video stopped"]
    assert log.step == "after video"  # type: ignore[attr-defined]


def write_text_wav(text: str, wav: Path) -> None:
    wav.write_text(text)


def test_a_video_stopped_before_it_is_asked_for_is_not_made(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="imageskin.reply_video")
    said: list[str] = []

    def speak(text: str, wav: Path) -> None:
        said.append(text)

    def render(photo: Path, wav: Path, output: Path) -> None:
        output.write_text("video")

    client = video_app(tmp_path, write_text, steps=ClipSteps(speak, render))
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Hi", "reply_id": REPLY_ID})
        client.post(f"/api/chat/clips/{REPLY_ID}/stop")
        made = client.post("/api/chat/video", json={"turn": 1, "reply_id": REPLY_ID}).json()
    assert made == {"video": None} and said == []
    [log] = [r for r in caplog.records if r.message == "Reply video stopped"]
    assert log.step == "before voice"  # type: ignore[attr-defined]


def test_a_prompt_stopped_before_it_arrives_is_not_answered(tmp_path: Path) -> None:
    """Larry's test of PR #129: Stop stops the thinking too, even when it reaches the server
    before the prompt does."""
    rendered: list[str] = []

    def render(photo: Path, text: str, output: Path) -> None:
        rendered.append(text)
        write_text(photo, text, output)

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        yield "One. Two."

    client = video_app(tmp_path, render, stream)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        stopped = client.post(f"/api/chat/clips/{REPLY_ID}/stop")
        assert stopped.json() == {"stopped": False}
        sent = client.post("/api/chat", json={"prompt": "Count", "reply_id": REPLY_ID})
        assert sent.status_code == 409 and sent.json()["detail"] == PROMPT_STOPPED
        assert client.get("/api/chat").json()["turns"] == []  # the prompt is dropped
        assert client.get(f"/api/chat/clips/{REPLY_ID}").status_code == 404
        # Only that once: the same id sent again is answered and spoken as usual.
        again = client.post("/api/chat", json={"prompt": "Again", "reply_id": REPLY_ID})
        assert again.json()["content"] == "One. Two."
        assert client.get(f"/api/chat/clips/{REPLY_ID}").status_code == 200
    assert rendered[:1] == ["One."]


def test_stop_cuts_off_the_llm_while_it_is_thinking(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Larry's test of PR #129: Stop while the reply is being written ends the LLM's work, and
    the prompt is dropped with the reply it would have had."""
    thinking, go = threading.Event(), threading.Event()

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        thinking.set()
        go.wait(5)  # a provider's stream: the next piece is where it is cut off
        yield "One. "
        yield "Two."

    caplog.set_level(logging.INFO, logger="imageskin.app")
    client = video_app(tmp_path, write_text, stream)
    answers: dict[str, Any] = {}

    def post() -> None:
        sent = client.post("/api/chat", json={"prompt": "Count", "reply_id": REPLY_ID})
        answers["status"], answers["detail"] = sent.status_code, sent.json()["detail"]

    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        asking = threading.Thread(target=post)
        asking.start()
        assert thinking.wait(5)
        stopped = client.post(f"/api/chat/clips/{REPLY_ID}/stop")
        assert stopped.json() == {"stopped": True}
        go.set()
        asking.join(5)
        assert answers == {"status": 409, "detail": PROMPT_STOPPED}
        assert client.get("/api/chat").json()["turns"] == []
        assert client.get(f"/api/chat/clips/{REPLY_ID}").status_code == 404
        # The next prompt is answered as usual.
        go.set()
        sent = client.post("/api/chat", json={"prompt": "Again", "reply_id": "b" * 8})
        assert sent.json()["content"] == "One. Two."
    [log] = [r for r in caplog.records if r.message == "Reply stopped"]
    assert log.answering is True  # type: ignore[attr-defined]
    [log] = [r for r in caplog.records if r.message == "Prompt stopped"]
    assert log.duration_ms >= 0  # type: ignore[attr-defined]


def test_a_stop_after_the_reply_is_kept_stops_only_its_clips(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Review on PR #130: a Stop while the reply was being saved said it had stopped the prompt,
    which was kept. Once the reply is kept, Stop stops only its clips, and says so."""
    saving, go = threading.Event(), threading.Event()
    save = Conversation._save

    def held(self: Conversation) -> None:
        saving.set()
        go.wait(5)
        save(self)

    caplog.set_level(logging.INFO, logger="imageskin.app")
    client = video_app(tmp_path, write_text, lambda messages: iter(["One. Two."]))
    answers: dict[str, Any] = {}

    def post() -> None:
        sent = client.post("/api/chat", json={"prompt": "Count", "reply_id": REPLY_ID})
        answers["status"], answers["content"] = sent.status_code, sent.json().get("content")

    with (
        patch("imageskin.app.load_review", return_value=Review(accepted=True)),
        patch.object(Conversation, "_save", held),
    ):
        asking = threading.Thread(target=post)
        asking.start()
        assert saving.wait(5)  # kept, and being saved
        assert client.post(f"/api/chat/clips/{REPLY_ID}/stop").json() == {"stopped": True}
        go.set()
        asking.join(5)
        turns = client.get("/api/chat").json()["turns"]
    assert answers == {"status": 200, "content": "One. Two."}
    assert [t["content"] for t in turns] == ["Count", "One. Two."]
    [log] = [r for r in caplog.records if r.message == "Reply stopped"]
    assert log.answering is False and log.clips is not None  # type: ignore[attr-defined]


def test_a_prompt_stopped_while_it_waits_for_another_is_not_answered(tmp_path: Path) -> None:
    """Stop reaches a prompt waiting for the one before it to be answered."""
    thinking, go = threading.Event(), threading.Event()
    asked: list[str] = []

    def stream(messages: list[dict[str, str]]) -> Iterator[str]:
        asked.append(messages[-1]["content"])
        thinking.set()
        go.wait(5)
        yield "Done."

    client = video_app(tmp_path, write_text, stream)
    answers: dict[str, int] = {}

    def post(prompt: str, reply_id: str) -> None:
        sent = client.post("/api/chat", json={"prompt": prompt, "reply_id": reply_id})
        answers[prompt] = sent.status_code

    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        first = threading.Thread(target=post, args=("First", "a" * 8))
        first.start()
        assert thinking.wait(5)
        second = threading.Thread(target=post, args=("Second", "b" * 8))
        second.start()
        time.sleep(0.2)  # the second waits for the first
        assert client.post(f"/api/chat/clips/{'b' * 8}/stop").json() == {"stopped": True}
        go.set()
        first.join(5)
        second.join(5)
    assert answers == {"First": 200, "Second": 409}
    assert len(asked) == 1 and "First" in asked[0]  # the second never reached the LLM


def test_only_so_many_early_stops_are_remembered(tmp_path: Path) -> None:
    client = video_app(tmp_path, write_text, lambda messages: iter(["One."]))
    with (
        patch("imageskin.app.load_review", return_value=Review(accepted=True)),
        patch("imageskin.app.STOPPED_EARLY_MAX", 2),
    ):
        for reply_id in ["a" * 8, "b" * 8, "c" * 8]:  # the third forgets the first two
            client.post(f"/api/chat/clips/{reply_id}/stop")
        client.post("/api/chat", json={"prompt": "Hi", "reply_id": "a" * 8})
        assert client.get(f"/api/chat/clips/{'a' * 8}").status_code == 200
        sent = client.post("/api/chat", json={"prompt": "Hi", "reply_id": "c" * 8})
        assert sent.status_code == 409


def test_a_stop_that_fails_is_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    rendering, go = threading.Event(), threading.Event()

    def render(photo: Path, text: str, output: Path) -> None:
        rendering.set()
        go.wait(5)
        write_text(photo, text, output)

    client = video_app(tmp_path, render, lambda messages: iter(["One. Two."]))
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Count", "reply_id": REPLY_ID})
        assert rendering.wait(5)
        with patch.object(SentenceClips, "cancel", side_effect=OSError("disk gone")):
            client.post(f"/api/chat/clips/{REPLY_ID}/stop")
            deadline = time.perf_counter() + 5
            while not [r for r in caplog.records if r.levelno == logging.ERROR]:
                assert time.perf_counter() < deadline
                time.sleep(0.02)
        go.set()
    [error] = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert error.message == "Could not stop a reply's clips"
    assert error.exc_info is not None and "disk gone" in str(error.exc_info[1])


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


def test_the_chat_is_told_the_photo_and_its_shown_size(tmp_path: Path) -> None:
    """R41d: the chat shapes the person's frame from this before drawing it, so it never
    changes size once shown."""
    client = video_app(tmp_path, None)
    photo_id = client.get("/api/uploads/photos").json()[0]["id"]
    path = UploadStore(tmp_path).path("photos", photo_id)
    assert path is not None
    Image.new("RGB", (1280, 720)).save(path, "JPEG")  # a real photo in place of the stand-in
    assert client.get("/api/chat/photo").json() == {
        "url": f"/api/uploads/photos/{photo_id}",
        "width": 1280,
        "height": 720,
        "idle": f"/api/chat/idle?photo={path.stem}",
    }


def test_the_chat_photo_without_a_readable_size_or_a_photo(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client = video_app(tmp_path, None)  # its photo is a JPEG header with nothing after it
    answer = client.get("/api/chat/photo").json()
    assert answer["url"].startswith("/api/uploads/photos/")
    assert answer["width"] is None and answer["height"] is None
    assert "Could not read the photo's size" in caplog.text
    patch.object(PrepareJob, "status", return_value=PrepareStatus("idle")).start()
    assert client.get("/api/chat/photo").json() == {
        "url": None,
        "width": None,
        "height": None,
        "idle": None,
    }


def test_holding_the_engines_waits_for_a_reply_and_readies_the_voice(tmp_path: Path) -> None:
    prepared: list[int] = []
    before: list[int] = []
    videos = ReplyVideos(
        tmp_path,
        write_text,
        VoiceReady(lambda: prepared.append(1), lambda: "v"),
        before_engines=lambda: before.append(1),
    )
    with videos.engines():
        assert prepared == [1] and before == [1]
        # A reply waits until they are let go.
        reply = threading.Thread(target=videos.render, args=(tmp_path / "me.jpg", 1, "Hi."))
        reply.start()
        reply.join(0.2)
        assert reply.is_alive()
    reply.join(5)
    assert videos.path(1).read_text() == "me.jpg: Hi."
    assert prepared == [1]  # ready already, so not prepared again


# --- Clear conversation removes the replies' videos (roadmap R27b) ---


def test_clearing_removes_a_reply_video_already_made(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="imageskin.app")
    client = video_app(tmp_path, write_text)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Hi"})
        assert client.post("/api/chat/video", json={"turn": 1}).json()["video"]
        assert client.get("/api/chat/videos/1").status_code == 200
        assert client.delete("/api/chat").json() == {"cleared": 2}
        assert client.get("/api/chat/videos/1").status_code == 404
    [log] = [r for r in caplog.records if r.message == "Reply videos cleared"]
    assert log.videos == 1 and log.streamed_replies == 0  # type: ignore[attr-defined]


def test_a_reply_video_being_made_when_cleared_is_never_published(tmp_path: Path) -> None:
    rendering, go = threading.Event(), threading.Event()

    def render(photo: Path, wav: Path, output: Path) -> None:
        output.write_text("half")
        rendering.set()
        assert go.wait(5)
        output.write_text("video")

    client = video_app(tmp_path, write_text, steps=ClipSteps(write_text_wav, render))
    answers: dict[str, object] = {}

    def ask_for_video() -> None:  # no reply id: the browser's id isn't needed to stop it
        answers["video"] = client.post("/api/chat/video", json={"turn": 1}).json()

    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Hi"})
        making = threading.Thread(target=ask_for_video)
        making.start()
        assert rendering.wait(5)
        assert client.delete("/api/chat").json() == {"cleared": 2}  # without waiting for it
        go.set()
        making.join(5)
        assert answers["video"] == {"video": None}
        assert client.get("/api/chat/videos/1").status_code == 404
        # The cleared reply can't be asked for any more.
        assert client.post("/api/chat/video", json={"turn": 1}).status_code == 404
    assert not list((tmp_path / "replies").glob("*.mp4"))


def test_clearing_stops_a_streamed_replys_clips(tmp_path: Path) -> None:
    rendering, go = threading.Event(), threading.Event()

    def render(photo: Path, text: str, output: Path) -> None:
        rendering.set()
        assert go.wait(5)
        write_text(photo, text, output)

    client = video_app(tmp_path, render, lambda messages: iter(["One. Two."]))
    clips_api = f"/api/chat/clips/{REPLY_ID}"
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Count", "reply_id": REPLY_ID})
        assert rendering.wait(5)
        assert client.delete("/api/chat").json() == {"cleared": 2}
        assert client.get(clips_api).status_code == 404
        go.set()
    folder = tmp_path / "replies" / f"clips-{REPLY_ID}"
    deadline = time.perf_counter() + 5
    while folder.exists() and time.perf_counter() < deadline:
        time.sleep(0.02)
    assert not folder.exists()


def test_a_reply_video_that_cant_be_removed_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    videos = ReplyVideos(tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"))
    videos.render(tmp_path / "me.jpg", 1, "Hi.")
    (videos.folder / "2.rendering.mp4").write_text("being written")  # left to its render
    assert videos.video(1) == videos.path(1)
    with patch.object(Path, "unlink", side_effect=PermissionError("in use")):
        assert videos.clear() == 0
    assert "Could not remove a reply video" in caplog.text
    assert videos.path(1).is_file() and videos.video(1) is None  # left, but not served
    assert videos.clear() == 1
    assert [p.name for p in videos.folder.glob("*.mp4")] == ["2.rendering.mp4"]


def test_a_reply_video_left_by_a_clear_is_not_served(tmp_path: Path) -> None:
    client = video_app(tmp_path, write_text)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Hi"})
        client.post("/api/chat/video", json={"turn": 1})
        with patch.object(Path, "unlink", side_effect=PermissionError("in use")):
            assert client.delete("/api/chat").json() == {"cleared": 2}
        assert (tmp_path / "replies" / "1.mp4").is_file()  # open in a browser, as on Windows
        assert client.get("/api/chat/videos/1").status_code == 404
        # The new conversation's reply at the same turn is served once made.
        client.post("/api/chat", json={"prompt": "Again"})
        assert client.get("/api/chat/videos/1").status_code == 404
        assert client.post("/api/chat/video", json={"turn": 1}).json()["video"]
        assert client.get("/api/chat/videos/1").text.endswith("You said Again")


def test_a_reply_video_asked_for_while_clearing_is_never_published(tmp_path: Path) -> None:
    """The regression for a review finding: a video asked for after Clear had stopped the ones
    being made, but before it cleared the conversation, read the old reply and was published
    after Clear had removed the videos."""
    rendering, go = threading.Event(), threading.Event()

    def render(photo: Path, wav: Path, output: Path) -> None:
        rendering.set()
        assert go.wait(5)
        output.write_text("video")

    client = video_app(tmp_path, write_text, steps=ClipSteps(write_text_wav, render))
    answers: dict[str, object] = {}

    def ask_for_video() -> None:
        answers["video"] = client.post("/api/chat/video", json={"turn": 1}).json()

    making = threading.Thread(target=ask_for_video)
    original = Conversation.clear

    def clear_once_the_video_is_under_way(conversation: Conversation) -> int:
        making.start()  # after Clear stopped the videos being made, before the conversation
        assert rendering.wait(5)
        return original(conversation)

    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        client.post("/api/chat", json={"prompt": "Hi"})
        with patch.object(Conversation, "clear", clear_once_the_video_is_under_way):
            assert client.delete("/api/chat").json() == {"cleared": 2}
        go.set()
        making.join(5)
        assert answers["video"] == {"video": None}
        assert client.get("/api/chat/videos/1").status_code == 404
    assert not list((tmp_path / "replies").glob("*.mp4"))


# --- A steady pace in long replies (roadmap R130) ---


def wav_steps(said: list[str], gates: dict[str, threading.Event] | None = None) -> ClipSteps:
    """Steps whose voice writes a second of a tone, with Kokoro's silence around it, and
    whose video writes a stand-in clip. Speaking a text with a gate waits for it first."""
    from test_pauses import write_speech

    def speak(text: str, wav: Path) -> None:
        if gates and text in gates:
            gates[text].wait(10)
        said.append(text)
        write_speech(wav, 0.3, 1.0, 0.4)

    def render(photo: Path, wav: Path, output: Path) -> None:
        output.write_bytes(b"clip")

    return ClipSteps(speak, render)


def made(clips: SentenceClips, n: int) -> None:
    for _ in range(500):
        if clips.rendered >= n:
            return
        time.sleep(0.01)
    raise AssertionError(f"{n} clips not made")


def test_sentences_queued_while_the_voice_is_busy_are_one_clip(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """R129 found a large fixed cost per clip on the hosted machine, so fewer, longer clips."""
    said: list[str] = []
    first = threading.Event()
    videos = ReplyVideos(
        tmp_path,
        write_text,
        VoiceReady(lambda: None, lambda: "v"),
        wav_steps(said, {"Hello there Larry,": first}),
    )
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    caplog.set_level(logging.INFO)
    clips("Hello there Larry,")  # the first clause, spoken on its own (R22b)
    for sentence in ["it is a fine day.", "The sun is out.", "- a list item", "Then more."]:
        clips(sentence)
    first.set()
    clips.close()
    clips.wait(10)
    assert clips.done and clips.error is None
    assert said == [
        "Hello there Larry,",
        "it is a fine day. The sun is out.",
        "a list item",  # a list item is spoken on its own
        "Then more.",
    ]
    ready = [r for r in caplog.records if r.message == "Sentence clip ready"]
    assert [(r.sentence, r.sentences_joined) for r in ready] == [  # type: ignore[attr-defined]
        (1, 1),
        (2, 2),
        (4, 1),
        (5, 1),
    ]
    assert clips.voice_waiting()  # every sentence counted as made


def test_sentences_join_only_up_to_the_word_limit() -> None:
    from imageskin.reply_video import JOIN_WORDS, joins

    assert joins(["One two."], "Three four.")
    assert not joins(["word " * JOIN_WORDS], "More.")
    assert not joins(["Run this:"], "```\necho\n```")
    assert not joins(["Intro."], "## A heading")


def test_each_clip_is_cut_to_its_pause_and_the_reply_s_pace_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    said: list[str] = []
    videos = ReplyVideos(
        tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"), wav_steps(said)
    )
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    caplog.set_level(logging.INFO)
    clips("Hello there.")
    clips.close()
    clips.wait(10)
    spoken = next(r for r in caplog.records if r.message == "Sentence spoken")
    assert spoken.cut_start_ms == 250 and spoken.cut_end_ms == 100  # type: ignore[attr-defined]
    paced = next(r for r in caplog.records if r.message == "Reply paced")
    assert paced.clips == 1 and paced.words == 2 and paced.gaps == []  # type: ignore[attr-defined]
    assert paced.held_ms < 100  # type: ignore[attr-defined]  # nothing measured yet: not held
    assert list(videos.recent_gaps) == [0]


def test_playback_is_held_by_the_gaps_the_last_replies_had(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    said: list[str] = []
    second = threading.Event()
    videos = ReplyVideos(
        tmp_path,
        write_text,
        VoiceReady(lambda: None, lambda: "v"),
        wav_steps(said, {"Two.": second}),
    )
    videos.recent_gaps.extend([0.4, 0.5, 9.0])  # the median: 0.5 s
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    clips.join_words = 0
    caplog.set_level(logging.INFO)
    clips("One.")
    clips("Two.")
    made(clips, 1)
    assert clips.hold_s == 0.5
    if time.perf_counter() - clips.times[0].ready_at < 0.4:
        assert clips.listed() == 0  # held
    clips.wait_for_change(0, 3)  # the hold ends while it waits
    assert clips.listed() == 1
    released = next(r for r in caplog.records if r.message == "Reply playback released")
    assert released.held_ms >= 500 and released.hold_s == 0.5  # type: ignore[attr-defined]
    time.sleep(1.5)  # the second clip is late: a gap the next reply is held by
    second.set()
    clips.close()
    clips.wait(10)
    paced = next(r for r in caplog.records if r.message == "Reply paced")
    assert paced.hold_s == 0.5 and paced.held_ms >= 500  # type: ignore[attr-defined]
    assert len(videos.recent_gaps) == 4 and videos.recent_gaps[-1] > 0.3


def test_a_reply_done_before_its_hold_ends_plays_at_once(tmp_path: Path) -> None:
    videos = ReplyVideos(tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"), wav_steps([]))
    videos.recent_gaps.append(60.0)
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    assert clips.hold_s == 15.0
    clips("One.")
    clips.close()
    clips.wait(10)
    assert clips.listed() == 1


def test_a_reply_kept_whole_is_never_held(tmp_path: Path) -> None:
    videos = ReplyVideos(tmp_path, write_text, VoiceReady(lambda: None, lambda: "v"))
    videos.recent_gaps.append(10.0)
    clips = videos.sentence_clips(Path("me.jpg"), "abc123ef")
    kept = tmp_path / "kept.mp4"
    kept.write_bytes(b"clip")
    clips.replay([kept])  # R130a's clips, made before
    assert clips.listed() == 1
