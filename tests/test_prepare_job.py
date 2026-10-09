import json
import logging
import threading
from dataclasses import asdict
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from imageskin.accent import Accent, AccentEngine
from imageskin.app import create_app
from imageskin.prepare_job import (
    CLIPS,
    NO_PHOTO,
    PrepareError,
    PrepareJob,
    PrepareStatus,
    Progress,
    Step,
    clip_voice,
    cloned_voice,
    fresh_steps,
    kokoro_voice,
    percent,
    photoreal_clip,
    photoreal_face,
    voice_fingerprint,
)
from imageskin.uploads import PhotoChoice, PhotoResult, UploadStore, VoiceSample
from imageskin.video import VideoError
from imageskin.voice import VoiceError

PHOTO_ID = "a" * 32


class FakeStore:
    """The parts of UploadStore the job uses: a chosen photo and a voice sample."""

    def __init__(self, folder: Path) -> None:
        self.photo = folder / "me.jpg"
        self.photo.write_bytes(b"photo")
        self.chosen: str | None = PHOTO_ID
        self.problem: str | None = None
        self.voice_sample_file = folder / "voice-sample.wav"
        self.voice_sample_file.write_bytes(b"first recordings")

    def photo_choice(self) -> PhotoChoice:
        return PhotoChoice(self.chosen)

    def voice_sample(self) -> VoiceSample:
        return VoiceSample(2, 40, 35, self.problem)

    def path(self, kind: str, upload_id: str) -> Path | None:
        return self.photo if upload_id == PHOTO_ID else None


def face_in_steps(photo: Path, progress: Progress) -> None:
    progress("models", 0, 1)
    progress("models", 1, 1)
    progress("shapes", 10, 10)
    progress("shapes", 10, 10)  # said twice, logged once
    for i in range(5):
        progress("loop", i, 4)
    progress("align", 0, 1)
    progress("align", 1, 1)


def write_clip(photo: Path, text: str, output: Path) -> None:
    output.write_text(text)


def make_job(
    tmp_path: Path,
    face: object = face_in_steps,
    voice: object = lambda: None,
    clip: object = write_clip,
    kind: str = "kokoro",
    accent: list[Accent] | None = None,  # a one-item list, so a test can change it
) -> tuple[PrepareJob, FakeStore]:
    store = FakeStore(tmp_path)
    chosen = accent or ["own"]
    job = PrepareJob(
        tmp_path,
        cast(UploadStore, store),
        voice,  # type: ignore[arg-type]
        face,  # type: ignore[arg-type]
        clip,  # type: ignore[arg-type]
        kind,
        lambda: chosen[0],
    )
    return job, store


def first_voice_id(tmp_path: Path, kind: str = "kokoro") -> str:
    """The voice_id of FakeStore's voice sample, as a job saved before a restart has it."""
    sample = tmp_path / "voice-sample.wav"
    sample.write_bytes(b"first recordings")
    return f"{kind}:{voice_fingerprint(sample)}"


def test_prepares_the_voice_then_the_face_and_saves_the_result(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    job, _ = make_job(tmp_path)
    assert job.status().state == "idle"
    with caplog.at_level(logging.INFO):
        started = job.start()
        job.wait(5)
    assert started.state == "running" and started.photo_id == PHOTO_ID
    status = job.status()
    assert status.state == "done" and status.percent == 100 and status.error is None
    assert status.steps is not None
    keys = [s.key for s in status.steps]
    assert keys == ["voice", "models", "shapes", "loop", "align", "clips"]
    assert all(s.done == s.total for s in status.steps)
    # Mouth shapes from before: done, with no time, since nothing was rendered.
    assert [s.seconds is None for s in status.steps] == [False, False, True, False, False, False]
    assert caplog.text.count("Prepare step finished") == 5
    assert caplog.text.count("Rendered clip") == 3
    assert caplog.text.count("Prepare step already done") == 1
    assert "Prepare job finished" in caplog.text
    saved = json.loads((tmp_path / "prepare.json").read_text())
    assert saved["state"] == "done" and saved["finished_at"]


def test_reports_progress_and_time_left_while_it_runs(tmp_path: Path) -> None:
    reached, release = threading.Event(), threading.Event()

    def slow_face(photo: Path, progress: Progress) -> None:
        progress("models", 1, 1)
        progress("shapes", 10, 10)
        progress("loop", 50, 200)  # resumed: 50 frames were there already
        progress("loop", 52, 200)
        reached.set()
        release.wait(5)

    job, _ = make_job(tmp_path, slow_face)
    job.start()
    assert reached.wait(5)
    assert job.start().state == "running"  # a second click just reports on it
    status = job.status()
    loop = next(s for s in (status.steps or []) if s.key == "loop")
    assert (loop.done, loop.total) == (52, 200) and loop.left_s is not None
    assert loop.seconds is None
    assert 0 < status.percent < 100
    release.set()
    job.wait(5)
    assert job.status().state == "done"


def test_needs_a_photo_and_enough_voice(tmp_path: Path) -> None:
    job, store = make_job(tmp_path)
    store.chosen = None
    with pytest.raises(PrepareError, match=NO_PHOTO):
        job.start()
    store.chosen = PHOTO_ID
    store.problem = "Add more recordings."
    with pytest.raises(PrepareError, match="Add more recordings."):
        job.start()
    assert job.status().state == "idle"


def test_a_failure_says_why(tmp_path: Path) -> None:
    def no_ffmpeg(photo: Path, progress: Progress) -> None:
        raise VideoError("ffmpeg was not found")

    job, _ = make_job(tmp_path, no_ffmpeg)
    job.start()
    job.wait(5)
    status = job.status()
    assert status.state == "failed" and status.error == "ffmpeg was not found"
    voice = (status.steps or [])[0]
    assert voice.done == 1  # the voice step had finished


def test_an_unexpected_error_is_reported_and_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def broken() -> None:
        raise RuntimeError("boom")

    job, _ = make_job(tmp_path, voice=broken)
    with caplog.at_level(logging.ERROR):
        job.start()
        job.wait(5)
    error = job.status().error or ""
    assert error.startswith("Something went wrong: boom.")
    assert "Traceback" in caplog.text


def test_a_removed_photo_fails_the_job(tmp_path: Path) -> None:
    job, store = make_job(tmp_path)
    store.photo = tmp_path / "gone.jpg"
    store.path = lambda kind, upload_id: None  # type: ignore[method-assign]
    job.start()
    job.wait(5)
    assert job.status().error == "The photo to prepare was removed. Choose another one."


def test_a_job_stopped_by_a_restart_carries_on(tmp_path: Path) -> None:
    steps = [asdict(s) for s in fresh_steps()]
    steps[3]["done"], steps[3]["total"] = 80, 200
    saved = {"state": "running", "photo_id": PHOTO_ID, "percent": 40, "steps": steps}
    (tmp_path / "prepare.json").write_text(json.dumps(saved))
    job, _ = make_job(tmp_path)
    status = job.status()  # how far it had got shows until the steps report again
    assert status.state == "running" and status.percent == 40
    assert status.steps is not None and status.steps[3].done == 80
    job.resume()
    job.wait(5)
    assert job.status().state == "done"


def test_resume_does_nothing_when_no_job_was_running(tmp_path: Path) -> None:
    job, _ = make_job(tmp_path)
    job.resume()
    job.wait(5)
    assert job.status().state == "idle"


def test_a_new_photo_needs_preparing_again(tmp_path: Path) -> None:
    job, store = make_job(tmp_path)
    job.start()
    job.wait(5)
    store.chosen = "b" * 32
    assert job.status().state == "idle"


def test_too_little_speech_after_preparing_needs_preparing_again(tmp_path: Path) -> None:
    job, store = make_job(tmp_path)
    job.start()
    job.wait(5)
    assert job.status().state == "done"
    store.problem = "Add more recordings."  # recordings removed afterwards
    assert job.status().state == "idle"
    store.problem = None
    assert job.status().state == "done"


def test_new_recordings_need_preparing_again(tmp_path: Path) -> None:
    job, store = make_job(tmp_path)
    job.start()
    job.wait(5)
    assert job.status().voice_id == f"kokoro:{voice_fingerprint(store.voice_sample_file)}"
    assert job.status().state == "done" and job.clip("sample") is not None
    # A recording added or removed: the clips spoke in the voice learned from the old ones.
    store.voice_sample_file.write_bytes(b"other recordings")
    assert job.status().state == "idle" and job.clip("sample") is None
    store.voice_sample_file.write_bytes(b"first recordings")  # back as they were
    assert job.status().state == "done"


def test_a_job_saved_before_the_voice_was_tracked_needs_preparing_again(tmp_path: Path) -> None:
    steps = [{**asdict(s), "done": 1} for s in fresh_steps()]
    saved = {"state": "done", "photo_id": PHOTO_ID, "percent": 100, "steps": steps}
    (tmp_path / "prepare.json").write_text(json.dumps(saved))  # its clips are in Kokoro's voice
    job, _ = make_job(tmp_path)
    assert job.status().state == "idle"


def test_voice_fingerprint(tmp_path: Path) -> None:
    sample = tmp_path / "voice-sample.wav"
    assert voice_fingerprint(sample) is None
    sample.write_bytes(b"one")
    first = voice_fingerprint(sample)
    sample.write_bytes(b"two")
    assert first and len(first) == 16 and voice_fingerprint(sample) != first


def test_a_state_file_from_other_steps_loads_consistently(tmp_path: Path) -> None:
    old_steps = [{"key": "face", "label": "Old step", "done": 1, "total": 1}]
    saved = {"state": "done", "photo_id": PHOTO_ID, "percent": 100, "steps": old_steps}
    (tmp_path / "prepare.json").write_text(json.dumps(saved))
    job, _ = make_job(tmp_path)
    assert job.status() == PrepareStatus("idle")

    (tmp_path / "prepare.json").write_text(json.dumps({**saved, "state": "running"}))
    job, _ = make_job(tmp_path)
    running = job.status()
    assert running.state == "running" and running.percent == 0
    assert [s.done for s in running.steps or []] == [0] * 6
    job.resume()
    job.wait(5)
    assert job.status().state == "done"


def test_an_unreadable_state_file_is_ignored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "prepare.json").write_text("{not json")
    with caplog.at_level(logging.ERROR):
        job, _ = make_job(tmp_path)
    assert job.status().state == "idle"
    assert "Could not read the prepare job state" in caplog.text


def test_percent_is_weighted_by_how_long_each_step_takes() -> None:
    steps = fresh_steps()
    assert percent(steps) == 0
    voice_done = [Step("voice", "", 1, 1)] + steps[1:]
    loop_half = steps[:3] + [Step("loop", "", 100, 200)] + steps[4:]
    # Of the 510 weighted seconds, the voice is 40 and the idle video 250.
    assert (percent(voice_done), percent(loop_half)) == (7, 24)


def test_default_voice_step_says_a_word() -> None:
    engine = MagicMock()
    kokoro_voice(engine)()
    engine.speak.assert_called_once_with("af_heart", "Hello.")


def test_cloned_voice_step_learns_the_voice_from_the_sample(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    engine = MagicMock(base="bm_lewis")
    with caplog.at_level(logging.INFO):
        cloned_voice(engine, tmp_path / "voice-sample.wav", lambda: "british")()
    engine.prepare.assert_called_once_with(str(tmp_path / "voice-sample.wav"), "british")
    record = next(r for r in caplog.records if r.getMessage() == "Voice ready: the person's own")
    assert vars(record)["accent"] == "british" and vars(record)["base"] == "bm_lewis"


def test_clips_speak_in_the_cloned_voice_when_chatterbox_is_installed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from imageskin.chatterbox_engine import ChatterboxEngine

    sample = tmp_path / "voice-sample.wav"
    with (
        caplog.at_level(logging.INFO),
        patch("imageskin.chatterbox_engine.check_installed"),
        patch.object(ChatterboxEngine, "learn_voice") as learn,
    ):
        step, engine, voice, kind = clip_voice(tmp_path, sample, lambda: "own")
        step()
    assert isinstance(engine, AccentEngine) and (voice, kind) == (str(sample), "clone")
    learn.assert_called_once_with(str(sample))
    assert "the person's own voice, cloned with Chatterbox Turbo" in caplog.text


def test_clips_speak_in_kokoro_when_chatterbox_is_missing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from imageskin.kokoro_engine import KokoroEngine

    missing = VoiceError("chatterbox not installed; see 'Your own voice' in the README")
    with (
        caplog.at_level(logging.WARNING),
        patch("imageskin.chatterbox_engine.check_installed", side_effect=missing),
    ):
        _, engine, voice, kind = clip_voice(tmp_path, tmp_path / "voice-sample.wav", lambda: "own")
    assert isinstance(engine, KokoroEngine) and (voice, kind) == ("af_heart", "kokoro")
    record = next(r for r in caplog.records if r.levelname == "WARNING")
    assert "Kokoro voice" in record.getMessage() and "README" in vars(record)["reason"]


def test_default_face_step_builds_the_photoreal_library(tmp_path: Path) -> None:
    def progress(step: str, done: int, total: int) -> None:
        pass

    with (
        patch("imageskin.prepare_job.find_ffmpeg") as ffmpeg,
        patch("imageskin.photoreal_library.prepare_library") as prepare,
    ):
        photoreal_face(tmp_path)(tmp_path / "me.jpg", progress)
    ffmpeg.assert_called_once()
    prepare.assert_called_once_with(tmp_path / "me.jpg", tmp_path, progress=progress)


JPG = b"\xff\xd8\xff\xe0" + b"\0" * 100


def test_the_api_starts_the_job_and_reports_on_it(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            tmp_path,
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=face_in_steps,
            render_clip=write_clip,
        )
    )
    assert client.get("/api/prepare").status_code == 403  # consent first
    client.post("/api/consent", json={"agreed": True})
    assert client.get("/api/prepare").json()["state"] == "idle"
    refused = client.post("/api/prepare")
    assert refused.status_code == 409 and refused.json()["detail"] == NO_PHOTO

    client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)})
    with patch.object(UploadStore, "voice_sample", return_value=VoiceSample(2, 40, 35, None)):
        assert client.post("/api/prepare").json()["state"] == "running"
        client.app.state.prepare_job.wait(5)  # type: ignore[attr-defined]
        done = client.get("/api/prepare").json()
        sample = client.get("/api/prepare/clips/sample")
        goodbye = client.get("/api/prepare/clips/goodbye")
        other = client.get("/api/prepare/clips/other")
        part = client.get("/api/prepare/clips/sample", headers={"Range": "bytes=0-3"})
    assert done["state"] == "done" and done["percent"] == 100
    assert [s["done"] for s in done["steps"]][:5] == [1, 1, 10, 4, 1]
    assert sample.status_code == 200 and sample.headers["content-type"] == "video/mp4"
    # Seekable: the browser asks for parts of the video.
    assert part.status_code == 206 and part.text == "This"
    assert part.headers["content-range"] == f"bytes 0-3/{len(sample.content)}"
    assert sample.text.startswith("This is a test.")
    assert goodbye.text == "Goodbye." and other.status_code == 422
    # No voice sample any more: the clips were made from old uploads, so they are not served.
    missing = client.get("/api/prepare/clips/sample")
    assert missing.status_code == 404 and "Prepare" in missing.json()["detail"]


def test_renders_the_sample_and_the_fixed_lines_after_the_face(tmp_path: Path) -> None:
    said: list[str] = []

    def clip(photo: Path, text: str, output: Path) -> None:
        said.append(text)
        write_clip(photo, text, output)

    job, store = make_job(tmp_path, clip=clip)
    assert job.clip("sample") is None  # nothing prepared yet
    job.start()
    job.wait(5)
    assert said == [text for _, text in CLIPS]
    assert said[:2] == ["Goodbye.", "Welcome back."]
    sample = job.clip("sample")
    assert sample == tmp_path / "clips" / "sample.mp4"
    assert sample.read_text().startswith("This is a test. How do I sound?")
    assert not list((tmp_path / "clips").glob("*.rendering.mp4"))
    clips = next(s for s in job.status().steps or [] if s.key == "clips")
    assert clips.done == clips.total > 3  # counted in words

    # Preparing again (say for another photo) renders every clip afresh.
    said.clear()
    job.start()
    job.wait(5)
    assert len(said) == 3


def test_a_restart_keeps_the_clips_already_rendered(tmp_path: Path) -> None:
    steps = [asdict(s) for s in fresh_steps()]
    for s in steps[:5]:
        s["done"] = s["total"]
    saved = {
        "state": "running",
        "photo_id": PHOTO_ID,
        "voice_id": first_voice_id(tmp_path),
        "percent": 95,
        "steps": steps,
    }
    (tmp_path / "prepare.json").write_text(json.dumps(saved))
    (tmp_path / "clips").mkdir()
    (tmp_path / "clips" / "goodbye.mp4").write_text("kept")
    (tmp_path / "clips" / "sample.rendering.mp4").write_text("cut short")
    said: list[str] = []

    def clip(photo: Path, text: str, output: Path) -> None:
        said.append(text)
        write_clip(photo, text, output)

    job, _ = make_job(tmp_path, clip=clip)
    job.resume()
    job.wait(5)
    assert said[0] == "Welcome back." and len(said) == 2
    assert (tmp_path / "clips" / "goodbye.mp4").read_text() == "kept"
    assert job.status().state == "done"


@pytest.mark.parametrize("saved_voice", ["kokoro:0123456789abcdef", None])
def test_a_restart_in_another_voice_renders_every_clip_again(
    tmp_path: Path, saved_voice: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    # Stopped mid-way, then the recordings changed (or saved before voices were tracked).
    steps = [asdict(s) for s in fresh_steps()]
    saved = {"state": "running", "photo_id": PHOTO_ID, "voice_id": saved_voice, "steps": steps}
    (tmp_path / "prepare.json").write_text(json.dumps(saved))
    (tmp_path / "clips").mkdir()
    (tmp_path / "clips" / "goodbye.mp4").write_text("old voice")
    job, store = make_job(tmp_path)
    with caplog.at_level(logging.INFO):
        job.resume()
        job.wait(5)
    assert (tmp_path / "clips" / "goodbye.mp4").read_text() == "Goodbye."
    assert job.status().state == "done"
    assert job.status().voice_id == f"kokoro:{voice_fingerprint(store.voice_sample_file)}"
    assert "Voice changed; rendering the clips again" in caplog.text


def test_a_kokoro_prepare_needs_preparing_again_once_the_clone_is_installed(
    tmp_path: Path,
) -> None:
    job, _ = make_job(tmp_path)
    job.start()
    job.wait(5)
    assert job.status().state == "done"
    later, _ = make_job(tmp_path, kind="clone")  # the server restarted with Chatterbox
    assert later.status().state == "idle" and later.clip("sample") is None


def test_another_accent_needs_preparing_again(tmp_path: Path) -> None:
    accent: list[Accent] = ["own"]
    job, store = make_job(tmp_path, kind="clone", accent=accent)
    job.start()
    job.wait(5)
    fingerprint = voice_fingerprint(store.voice_sample_file)
    assert job.status().voice_id == f"clone:{fingerprint}"  # as saved before accents (R25b)
    accent[0] = "british"
    assert job.status().state == "idle" and job.clip("sample") is None
    job.start()
    job.wait(5)
    assert job.status().state == "done" and job.status().voice_id == f"clone-british:{fingerprint}"
    accent[0] = "own"
    assert job.status().state == "idle"


def test_kokoro_ignores_the_accent(tmp_path: Path) -> None:
    accent: list[Accent] = ["own"]
    job, _ = make_job(tmp_path, accent=accent)
    job.start()
    job.wait(5)
    accent[0] = "american"
    assert job.status().state == "done"


def test_a_clip_that_fails_fails_the_job_and_is_not_served(tmp_path: Path) -> None:
    def broken(photo: Path, text: str, output: Path) -> None:
        output.write_text("half")
        raise VideoError("ffmpeg failed")

    job, _ = make_job(tmp_path, clip=broken)
    job.start()
    job.wait(5)
    assert job.status().error == "ffmpeg failed"
    assert job.clip("goodbye") is None
    assert not (tmp_path / "clips" / "goodbye.mp4").exists()


def test_default_clip_speaks_and_renders_photoreal_with_the_shared_voice(
    tmp_path: Path,
) -> None:
    from imageskin.voice import Speech

    voice = MagicMock()
    voice.speak.return_value = Speech(b"\0\0" * 2400, 24000, [])
    with patch("imageskin.photoreal.PhotorealEngine") as engine:
        render = photoreal_clip(tmp_path, voice)
        render(tmp_path / "me.jpg", "Goodbye.", tmp_path / "goodbye.mp4")
        render(tmp_path / "me.jpg", "Welcome back.", tmp_path / "welcome.mp4")
    assert [c.args for c in voice.speak.call_args_list] == [
        ("af_heart", "Goodbye."),
        ("af_heart", "Welcome back."),
    ]
    engine.assert_called_once_with(tmp_path)  # the library is loaded once for all clips
    video = engine.return_value
    video.prepare.assert_called_once_with(tmp_path / "me.jpg")
    assert video.render.call_count == 2
    lib, wav, output = video.render.call_args.args
    assert lib is video.prepare.return_value and output == tmp_path / "welcome.mp4"


def test_clips_can_speak_in_another_voice(tmp_path: Path) -> None:
    from imageskin.voice import Speech

    voice = MagicMock()
    voice.speak.return_value = Speech(b"\0\0" * 2400, 24000, [])
    with patch("imageskin.photoreal.PhotorealEngine"):
        photoreal_clip(tmp_path, voice, "voice-sample.wav")(
            tmp_path / "me.jpg", "Goodbye.", tmp_path / "goodbye.mp4"
        )
    voice.speak.assert_called_once_with("voice-sample.wav", "Goodbye.")


def test_the_voice_check_and_the_clips_share_one_voice_engine(tmp_path: Path) -> None:
    speaks: list[object] = []

    def speak(self: object, voice: str, text: str) -> None:
        speaks.append(self)
        raise RuntimeError("stop here")

    no_clone = patch("imageskin.chatterbox_engine.check_installed", side_effect=VoiceError("no"))
    with patch("imageskin.kokoro_engine.KokoroEngine.speak", speak), no_clone:
        job = create_app(tmp_path, check_photo=lambda p: PhotoResult([], 80)).state.prepare_job
        with pytest.raises(RuntimeError):
            job._prepare_voice()
        with pytest.raises(RuntimeError), patch("imageskin.photoreal.PhotorealEngine"):
            job._render_clip(tmp_path / "me.jpg", "Goodbye.", tmp_path / "goodbye.mp4")
    assert len(speaks) == 2 and speaks[0] is speaks[1]


def test_choosing_another_accent_prepares_the_sample_again(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clone = (lambda: None, MagicMock(), "voice-sample.wav", "clone")
    with patch("imageskin.app.clip_voice", return_value=clone):
        app = create_app(
            tmp_path,
            check_photo=lambda p: PhotoResult([], 80),
            prepare_face=face_in_steps,
            render_clip=write_clip,
        )
    client = TestClient(app)
    job = cast(PrepareJob, app.state.prepare_job)
    assert client.get("/api/accent").status_code == 403  # consent first
    client.post("/api/consent", json={"agreed": True})
    assert client.get("/api/accent").json() == {"accent": "own", "available": True}
    assert client.put("/api/accent", json={"accent": "martian"}).status_code == 422
    # Before anything is prepared, the choice is only saved.
    assert client.put("/api/accent", json={"accent": "american"}).json()["accent"] == "american"
    assert job.status().state == "idle"

    client.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)})
    store = UploadStore(tmp_path)
    store.voice_sample_file.parent.mkdir(parents=True, exist_ok=True)
    store.voice_sample_file.write_bytes(b"recordings")
    with patch.object(UploadStore, "voice_sample", return_value=VoiceSample(2, 40, 35, None)):
        client.post("/api/prepare")
        job.wait(5)
        assert "clone-american" in str(job.status().voice_id)
        with caplog.at_level(logging.INFO):
            again = client.put("/api/accent", json={"accent": "british"})
        assert again.json() == {"accent": "british", "available": True}
        assert job.status().state == "running"  # the sample is made again, in the new accent
        assert "Accent changed; preparing the sample again" in caplog.text
        job.wait(5)
        assert job.status().state == "done" and "clone-british" in str(job.status().voice_id)
        with patch.object(PrepareJob, "start", side_effect=PrepareError(NO_PHOTO)):
            client.put("/api/accent", json={"accent": "own"})
    assert "Could not prepare again" in caplog.text
    assert TestClient(create_app(tmp_path)).get("/api/accent").json()["accent"] == "own"


def test_the_accent_engine_shares_the_clone_and_the_speaker_model(tmp_path: Path) -> None:
    from imageskin.prepare_job import accent_engine

    clone = MagicMock()
    with (
        patch("imageskin.chatterbox_engine.TurboConverter") as converter,
        patch("imageskin.speaker_checks.SpeakerChecker.voice_print") as voice_print,
    ):
        engine = accent_engine(tmp_path, clone)
        engine._make_converter()
        engine._voice_print(np.zeros(3))
    converter.assert_called_once_with(clone.cloner.return_value)
    assert voice_print.call_args.args[1] == 24000
    assert engine._kokoro("b")._load.args == ("b",)  # type: ignore[attr-defined]
