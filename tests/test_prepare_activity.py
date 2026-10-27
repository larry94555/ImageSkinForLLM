"""Prepare shows it is still working (roadmap R134b): what each step is doing, the time so far,
a notice when a step is slow, and a job no longer worked on shown as stopped."""

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from test_prepare_job import PHOTO_ID, make_job

from imageskin import liveportrait
from imageskin.download import MB
from imageskin.liveportrait import FACE_MODEL_SIZE, HF_FILES, ensure_models
from imageskin.photoreal_library import liveportrait_factory
from imageskin.prepare_job import (
    STEPS,
    PrepareJob,
    PrepareStatus,
    Progress,
    Step,
    fresh_steps,
    percent,
    remaining,
    share,
)

USUAL = {key: weight for key, _, weight in STEPS}


def step(status: PrepareStatus, key: str) -> Step:
    return next(s for s in status.steps or [] if s.key == key)


def held_face(reached: threading.Event, release: threading.Event) -> object:
    def face(photo: Path, progress: Progress) -> None:
        progress("models", 0, 1, "Checking the face models")
        progress("models", 0, 1, "Downloading the face models: 12 of 500 MB")
        reached.set()
        release.wait(5)
        progress("models", 1, 1)

    return face


def test_each_step_says_what_it_is_doing_while_it_runs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    reached, release = threading.Event(), threading.Event()
    job, _ = make_job(tmp_path, held_face(reached, release))
    with caplog.at_level(logging.DEBUG, logger="imageskin.prepare_job"):
        job.start()
        assert reached.wait(5)
        models = step(job.status(), "models")
        assert models.activity == "Downloading the face models: 12 of 500 MB"
        assert models.elapsed_s is not None and not models.slow
        # Only the activity changed, so the saved state still has the step's first line.
        saved = json.loads((tmp_path / "prepare.json").read_text())
        assert saved["steps"][1]["activity"] == "Checking the face models"
        release.set()
        job.wait(5)
    done = job.status()
    assert done.state == "done"
    assert all(s.activity is None and s.elapsed_s is None and not s.slow for s in done.steps or [])
    lines = [vars(r).get("activity") for r in caplog.records if r.message == "Prepare activity"]
    assert "Loading the voice model" in lines  # Kokoro speaks
    assert "Downloading the face models: 12 of 500 MB" in lines
    assert "Making the sample video" in lines


def test_the_cloned_voice_says_it_learns_the_voice(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    job, _ = make_job(tmp_path, kind="clone")
    with caplog.at_level(logging.DEBUG, logger="imageskin.prepare_job"):
        job.start()
        job.wait(5)
    lines = [vars(r).get("activity") for r in caplog.records]
    assert "Loading the voice models and learning the voice from your recordings" in lines


def test_the_beat_gives_the_time_left_and_moves_the_percentage(tmp_path: Path) -> None:
    reached, release = threading.Event(), threading.Event()

    def voice() -> None:
        reached.set()
        release.wait(5)

    job, _ = make_job(tmp_path, voice=voice)
    with patch("imageskin.prepare_job.BEAT_S", 60):  # beats only when the test says
        job.start()
        assert reached.wait(5)
        start = job._clock["voice"][0]
        job._beat(start + 10)
        early = job.status()
        job._beat(start + 30)
        later = job.status()
        job._beat(start + USUAL["voice"] + 5)  # past its usual time: still counting down
        past = job.status()
        release.set()
        job.wait(5)
    rest = sum(USUAL.values()) - USUAL["voice"]
    # Nothing has finished yet, so each step is expected to take its usual time.
    assert step(early, "voice").left_s == USUAL["voice"] - 10
    assert early.left_s == USUAL["voice"] - 10 + rest
    assert step(later, "voice").left_s == USUAL["voice"] - 30
    past_left = step(past, "voice").left_s
    assert past_left == round(remaining(USUAL["voice"], USUAL["voice"] + 5))
    assert past_left is not None and 0 < past_left < USUAL["voice"] - 30
    assert past.left_s == past_left + rest
    assert 0 < early.percent < later.percent < past.percent
    assert not step(later, "voice").slow
    assert job.status().left_s is None  # finished


def test_a_counted_step_has_left_what_its_pace_says_at_this_runs_pace(tmp_path: Path) -> None:
    reached, release = threading.Event(), threading.Event()

    def face(photo: Path, progress: Progress) -> None:
        progress("models", 0, 1)
        progress("models", 1, 1)
        progress("shapes", 0, 10)
        progress("shapes", 2, 10)
        reached.set()
        release.wait(5)

    job, _ = make_job(tmp_path, face)
    with patch("imageskin.prepare_job.BEAT_S", 60):
        job.start()
        assert reached.wait(5)
        # Counting began at 100 s, and 2 of 10 shapes were done by 110 s: 5 s each.
        job._clock["shapes"] = (100.0, 0)
        job._counted["shapes"] = 110.0
        job._beat(112.0)
        status = job.status()
        release.set()
        job.wait(5)
    assert step(status, "shapes").left_s == 5 * 8 - 2
    # The voice and models steps took almost no time: the steps after at the quickest pace.
    rest = (USUAL["loop"] + USUAL["align"] + USUAL["clips"]) * 0.5
    assert status.left_s == 38 + rest


def test_pace_compares_finished_steps_with_their_usual_times() -> None:
    steps = fresh_steps()
    assert PrepareJob._pace(steps) == 1.0  # nothing finished yet
    voice = Step("voice", "", 1, 1, seconds=2 * USUAL["voice"])
    models = Step("models", "", 1, 1, seconds=None)  # done before this run: not counted
    assert PrepareJob._pace([voice, models, *steps[2:]]) == 2.0
    quick = Step("voice", "", 1, 1, seconds=0.1)
    assert PrepareJob._pace([quick, *steps[1:]]) == 0.5  # says little about the long steps


def test_a_step_with_nothing_new_for_twice_its_usual_time_is_slow(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    reached, release = threading.Event(), threading.Event()
    job, _ = make_job(tmp_path, held_face(reached, release))
    with patch("imageskin.prepare_job.BEAT_S", 60), caplog.at_level(logging.WARNING):
        job.start()
        assert reached.wait(5)
        late = job._changed + 2 * USUAL["models"] + 1
        job._beat(late)
        job._beat(late + 1)  # logged once
        slow = job.status()
        job._progress("models", 0, 1, "Loading the face models")  # something new
        again = job.status()
        release.set()
        job.wait(5)
    assert step(slow, "models").slow and not step(again, "models").slow
    records = [r for r in caplog.records if r.message == "Prepare step slow"]
    assert len(records) == 1 and vars(records[0])["step"] == "models"
    assert vars(records[0])["quiet_s"] > 2 * USUAL["models"]


def test_a_job_no_longer_worked_on_shows_as_stopped_and_try_again_carries_on(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    steps = [asdict(s) for s in fresh_steps()]
    steps[0]["done"] = 1
    saved = {"state": "running", "photo_id": PHOTO_ID, "percent": 10, "steps": steps}
    (tmp_path / "prepare.json").write_text(json.dumps(saved))
    job, _ = make_job(tmp_path)  # never resumed: its thread is gone
    stopped = job.status()
    assert stopped.state == "running" and stopped.stopped
    with caplog.at_level(logging.WARNING):
        job.start()
        job.wait(5)
    assert "Prepare job had stopped; carrying on" in caplog.text
    finished = job.status()
    assert finished.state == "done" and not finished.stopped


def test_a_running_job_is_not_stopped(tmp_path: Path) -> None:
    reached, release = threading.Event(), threading.Event()
    job, _ = make_job(tmp_path, held_face(reached, release))
    job.start()
    assert reached.wait(5)
    assert not job.status().stopped
    assert job.start().state == "running"  # a second click just reports on it
    release.set()
    job.wait(5)


def test_share_of_a_step_that_cannot_count_its_work() -> None:
    assert share(Step("voice", "", 0, 1), 40) == 0
    assert share(Step("voice", "", 0, 1, elapsed_s=40), 40) == pytest.approx(
        0.9 * (1 - 1 / 2.718281828)
    )
    assert share(Step("voice", "", 0, 1, elapsed_s=10_000), 40) <= 0.9  # never past 90%
    assert share(Step("loop", "", 5, 10, elapsed_s=100), 70) == 0.5  # counted work as counted
    assert percent([Step("voice", "", 0, 1, elapsed_s=40), *fresh_steps()[1:]]) > 0


def test_the_face_models_download_reports_each_mb(tmp_path: Path) -> None:
    said: list[str] = []

    def download(
        url: str, dest: Path, size: int, sha: str, progress: Callable[[int, int], None]
    ) -> None:
        tell = progress
        tell(MB // 2, size)
        tell(min(size, 3 * MB), size)
        tell(min(size, 3 * MB) + 1, size)  # still the same MB: not said again

    with (
        patch.object(liveportrait, "fetch_code"),
        patch.object(liveportrait, "download", side_effect=download),
    ):
        ensure_models(tmp_path, said.append)
    total = (sum(size for _, size, _ in HF_FILES) + FACE_MODEL_SIZE) // MB
    assert said[0] == "Checking the face models"
    assert said[1] == f"Downloading the face models: 0 of {total} MB"
    assert len(said) == len(set(said))
    assert all(line.endswith(f"of {total} MB") for line in said[1:])


def test_the_beat_does_nothing_once_the_job_has_finished(tmp_path: Path) -> None:
    job, _ = make_job(tmp_path)
    job.start()
    job.wait(5)
    before = job.status()
    job._beat(10_000)
    assert job.status() == before


def test_the_portrait_factory_reports_the_download_then_the_loading(tmp_path: Path) -> None:
    said: list[str] = []
    with (
        patch.object(liveportrait, "ensure_models") as ensure,
        patch.object(liveportrait, "Portrait") as portrait,
    ):
        liveportrait_factory(tmp_path, said.append)(tmp_path / "me.jpg")
    lp_dir = tmp_path / "models" / "LivePortrait"
    ensure.assert_called_once_with(lp_dir, said.append)
    portrait.assert_called_once_with(lp_dir, tmp_path / "me.jpg")
    assert said == ["Loading the face models"]


def test_prepare_again_leaves_out_the_face_steps_kept_from_before(tmp_path: Path) -> None:
    """Prepare again on a slow host (PR #174 testing): the face is kept, so the time left is the
    clips only, not the face steps at the slow voice's pace as well (about 25 minutes)."""
    reached, release = threading.Event(), threading.Event()

    def kept_face(photo: Path, progress: Progress) -> None:
        for key in ("models", "shapes", "loop", "align"):
            progress(key, 1, 1)  # as prepare_library says of a library kept from before

    def clip(photo: Path, text: str, out: Path) -> None:
        reached.set()
        release.wait(5)
        out.write_bytes(b"mp4")

    job, _ = make_job(tmp_path, kept_face, clip=clip)
    with patch("imageskin.prepare_job.BEAT_S", 60):
        job.start()
        assert reached.wait(5)
        with job._lock:  # the voice took 5 times its usual time
            steps = [
                replace(s, seconds=5.0 * USUAL["voice"]) if s.key == "voice" else s
                for s in job._status.steps or []
            ]
            job._status = replace(job._status, steps=steps)
        start = job._clock["clips"][0]
        job._beat(start + 10)
        status = job.status()
        release.set()
        job.wait(5)
    assert all(step(status, k).seconds is None for k in ("models", "shapes", "loop", "align"))
    assert status.left_s == USUAL["clips"] * 5 - 10  # the clips only
    assert status.percent == 100 * (5 * USUAL["voice"] + 10) // (5 * USUAL["voice"] + 500)


def test_remaining_counts_down_then_ever_more_slowly_never_reaching_0() -> None:
    assert remaining(100, 0) == 100
    assert remaining(100, 75) == 25  # a second a second until its last quarter
    lefts = [remaining(100, t) for t in range(76, 400)]
    assert all(0 < b < a for a, b in zip([25.0, *lefts], lefts, strict=False))
    assert remaining(20, 10) == 10  # at least 10 s of tail
    assert remaining(20, 11) < 9.1
    assert remaining(0, 5) == 0  # nothing to do


def test_prepare_again_expects_each_step_to_take_its_time_from_last_run(tmp_path: Path) -> None:
    """Larry on PR #177: at 10% the page stood still for over a minute. The voice took much
    longer on the hosted machine than its usual 40 s, so its time left went and the percentage
    hardly moved. Prepare again now expects each step to take what it took last time."""
    reached, release = threading.Event(), threading.Event()

    def voice() -> None:
        reached.set()
        release.wait(5)

    job, _ = make_job(tmp_path, voice=voice)
    last = {"voice": 200.0, "models": 0.0, "shapes": 0.0, "loop": 0.0, "align": 0.0, "clips": 150.0}
    saved = asdict(PrepareStatus("done", PHOTO_ID, job.voice_id(), steps=fresh_steps(), times=last))
    (tmp_path / "prepare.json").write_text(json.dumps(saved), encoding="utf-8")
    job = PrepareJob(
        tmp_path, job._store, voice, job._prepare_face, job._render_clip, "kokoro", job._accent
    )
    with patch("imageskin.prepare_job.BEAT_S", 60):
        job.start()
        assert reached.wait(5)
        start = job._clock["voice"][0]
        seen = []
        for t in range(0, 200, 5):  # every 5 s, as Larry asked
            job._beat(start + t)
            seen.append(job.status())
        release.set()
        job.wait(5)
    assert seen[0].left_s == 350  # 200 s of voice and 150 s of clips
    assert [s.left_s for s in seen[:30]] == list(range(350, 200, -5))
    percents = [s.percent for s in seen]
    assert percents == sorted(percents) and percents[-1] >= 50  # half the time has gone
    assert len(set(percents)) > 30  # it moves every 5 s or so, it doesn't stand still
    assert not any(step(s, "voice").slow for s in seen)
    times = job.status().times or {}
    assert set(times) == {key for key, _, _ in STEPS}  # this run's times, for the next one


def test_steps_with_nothing_to_do_last_time_are_expected_again_for_another_photo(
    tmp_path: Path,
) -> None:
    job, store = make_job(tmp_path)
    saved = asdict(
        PrepareStatus(
            "done",
            "another-photo",
            job.voice_id(),
            steps=fresh_steps(),
            times={"voice": 9, "loop": 0},
        )
    )
    (tmp_path / "prepare.json").write_text(json.dumps(saved), encoding="utf-8")
    job = PrepareJob(tmp_path, job._store, job._prepare_voice, job._prepare_face, job._render_clip)
    with patch.object(job, "_run_in_background"):
        started = job.start()
    assert started.times == {"voice": 9}  # the new photo's loop is made, not kept


def running_job(tmp_path: Path, times: dict[str, float]) -> PrepareJob:
    """A job told it is running, with no thread, so a test calls _progress itself."""
    job, _ = make_job(tmp_path)
    job._status = PrepareStatus("running", PHOTO_ID, steps=fresh_steps(), times=times)
    return job


def test_a_step_carried_on_after_a_restart_saves_its_whole_time(tmp_path: Path) -> None:
    """Codex's review on PR #177: 80% of the clips were there before a restart and the last 20%
    took 30 s, so the next prepare, which makes them all again, should expect 150 s, not 30."""
    job = running_job(tmp_path, {"clips": 400.0})
    # A clock of the job's own that only moves when the test says: the time module every
    # thread shares stays as it is, and saving prepare.json takes no time on it.
    now = [1000.0]
    clock = SimpleNamespace(perf_counter=lambda: now[0])
    with patch("imageskin.prepare_job.time", clock):
        job._progress("clips", 80, 100)  # what was on disk when it carried on
        now[0] += 30
        job._progress("clips", 100, 100)
    assert (job.status().times or {})["clips"] == 150.0


def test_a_step_with_nothing_to_do_last_time_is_expected_again_once_it_has_work(
    tmp_path: Path,
) -> None:
    """Codex's review on PR #177: the face was kept last time (0 s), but new mouth settings make
    the shapes again; a ready-made voice took no time, but now recordings are learned."""
    job = running_job(tmp_path, {"shapes": 0.0, "voice": 0.2, "loop": 0.0, "clips": 90.0})
    job._progress("voice", 0, 1)
    job._progress("shapes", 0, 14)
    job._progress("loop", 40, 40)  # still nothing to do: kept at 0
    times = job.status().times or {}
    assert "shapes" not in times and "voice" not in times
    assert times["loop"] == 0.0 and times["clips"] == 90.0
    job._beat(time.perf_counter())
    voice_left = step(job.status(), "voice").left_s
    assert voice_left is not None and voice_left > USUAL["voice"] - 5  # its usual time, not 0


def test_another_voice_is_timed_afresh(tmp_path: Path) -> None:
    job, _ = make_job(tmp_path)
    times = {"voice": 0.0, "models": 30.0, "clips": 20.0}
    saved = PrepareStatus("done", PHOTO_ID, voice_id="preset:af_heart", steps=fresh_steps())
    job._status = replace(saved, times=times)
    with patch.object(job, "_run_in_background"):
        started = job.start()
    assert started.times == {"models": 30.0}  # the voice and the clips it speaks are new
