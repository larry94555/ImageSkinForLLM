"""What the sites take turns with (R61d): at most a set number keep the clone loaded, and
Prepare and PDF reading run one site at a time."""

import io
import logging
import threading
import time
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from test_prepare_job import FakeStore, face_in_steps, write_clip

from imageskin.accent import OWN, Accent, AccentEngine
from imageskin.across_sites import WAITING, CloneBudget, SiteClone, Turns
from imageskin.app import create_app, make_engines
from imageskin.config import ConfigError, load_settings
from imageskin.content import ContentStore
from imageskin.pdf_reading import Piece, Progress, Reading
from imageskin.prepare_job import PrepareJob, clip_voice
from imageskin.prepare_job import Progress as PrepareProgress
from imageskin.reading_job import ReadingJob, ReadingStatus
from imageskin.uploads import PhotoResult, UploadStore
from imageskin.voice import Speech, VoiceError

PDF = b"%PDF-1.7\n" + b"x" * 100 + b"\n%%EOF\n"


class Clone:
    """An accent engine that says which voice and accent it speaks in, and forgets them when
    unloaded, as the real clone does."""

    def __init__(self) -> None:
        self.voice: str | None = None
        self.accent: Accent = OWN
        self.base: str | None = None
        self.prepared: list[tuple[str, Accent]] = []
        self.unloaded = 0

    def prepare(self, voice: str, accent: Accent) -> None:
        self.prepared.append((voice, accent))
        self.voice, self.accent = voice, accent

    def speak(self, voice: str, text: str) -> Speech:
        learned = self.voice or voice  # the real clone learns the voice it is given, own accent
        return Speech(f"{learned}/{self.accent}:{text}".encode(), 24000, [], [])

    def forget_voice(self) -> None:
        self.voice, self.accent = None, OWN
        self.unloaded += 1

    def check_voice_sample(self, voice: str) -> None:
        pass


def site_clones(budget: CloneBudget, names: str) -> dict[str, tuple[SiteClone, Clone]]:
    made = {}
    for name in names:
        clone = Clone()
        made[name] = (budget.engine(cast(AccentEngine, clone), name), clone)
    return made


def test_the_third_sites_speech_unloads_the_least_recently_used_clone(
    caplog: pytest.LogCaptureFixture,
) -> None:
    budget = CloneBudget(2)
    sites = site_clones(budget, "abc")
    accents: dict[str, Accent] = {"a": "british", "b": OWN, "c": "american"}
    with caplog.at_level(logging.INFO, logger="imageskin.across_sites"):
        for name, (engine, _) in sites.items():
            engine.prepare(f"{name}.wav", accents[name])
        assert budget.loaded() == ["b", "c"]
        assert sites["a"][1].unloaded == 1 and sites["b"][1].unloaded == 0
        unloaded = [r for r in caplog.records if r.message == "Clone unloaded"]
        assert [r.__dict__["site"] for r in unloaded] == ["a"]
        assert unloaded[0].__dict__["idle_s"] >= 0

        # Site a speaks again in its own voice and accent, and b, now the least recent, goes.
        assert sites["a"][0].speak("a.wav", "Hi").pcm == b"a.wav/british:Hi"
    assert sites["a"][1].prepared == [("a.wav", "british")] * 2
    assert budget.loaded() == ["c", "a"] and sites["b"][1].unloaded == 1
    assert "Clone loaded again" in caplog.text
    assert sites["c"][0].speak("c.wav", "Yes").pcm == b"c.wav/american:Yes"
    assert sites["c"][1].prepared == [("c.wav", "american")]  # never unloaded


class Resident:
    """Counts the clones in memory at once, as the real models would use it."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.now = 0
        self.most = 0

    def counted(self, clone: Clone) -> Clone:
        prepare, forget = clone.prepare, clone.forget_voice

        def load(voice: str, accent: Accent) -> None:
            with self.lock:
                if clone.voice is None:
                    self.now += 1
                    self.most = max(self.most, self.now)
            prepare(voice, accent)

        def unload() -> None:
            forget()
            with self.lock:
                self.now -= 1

        clone.prepare, clone.forget_voice = load, unload  # type: ignore[method-assign]
        return clone


def test_the_next_site_loads_only_once_the_clone_it_replaces_is_unloaded() -> None:
    # Codex's review of PR #273: the budget counts the clones really in memory.
    budget = CloneBudget(1)
    sites = site_clones(budget, "ab")
    memory = Resident()
    for _, clone in sites.values():
        memory.counted(clone)
    a, b = sites["a"][0], sites["b"][0]
    a.prepare("a.wav", OWN)
    unloading, finish = threading.Event(), threading.Event()
    forget = sites["a"][1].forget_voice

    def slow_unload() -> None:
        unloading.set()
        assert finish.wait(5)
        forget()

    sites["a"][1].forget_voice = slow_unload  # type: ignore[method-assign]
    prepared = threading.Thread(target=b.prepare, args=("b.wav", OWN))
    prepared.start()
    assert unloading.wait(5)
    time.sleep(0.05)
    assert sites["b"][1].prepared == []  # b waits for a's memory to be freed
    assert budget.loaded() == ["a"]
    finish.set()
    prepared.join(5)
    assert sites["b"][1].prepared == [("b.wav", OWN)]
    assert budget.loaded() == ["b"] and memory.most == 1 and memory.now == 1


def test_a_clone_speaking_is_unloaded_once_it_has_finished() -> None:
    budget = CloneBudget(1)
    sites = site_clones(budget, "ab")
    speaking, done = threading.Event(), threading.Event()
    speak = sites["a"][1].speak

    def slow(voice: str, text: str) -> Speech:
        speaking.set()
        assert done.wait(5)
        return speak(voice, text)

    sites["a"][1].speak = slow  # type: ignore[method-assign]
    a = threading.Thread(target=sites["a"][0].speak, args=("a.wav", "Hi"))
    a.start()
    assert speaking.wait(5)
    b = threading.Thread(target=sites["b"][0].prepare, args=("b.wav", OWN))
    b.start()
    time.sleep(0.05)
    assert sites["a"][1].unloaded == 0 and sites["b"][1].prepared == []
    done.set()
    a.join(5)
    b.join(5)
    assert sites["a"][1].unloaded == 1 and budget.loaded() == ["b"]


def test_delete_my_data_forgets_the_voice_and_leaves_the_budget() -> None:
    budget = CloneBudget(2)
    engine, clone = site_clones(budget, "a")["a"]
    engine.prepare("a.wav", "british")
    assert engine.base is None and engine.accent == "british"
    engine.check_voice_sample("a.wav")
    engine.forget_voice()
    assert budget.loaded() == [] and clone.unloaded == 1
    assert engine.speak("new.wav", "Hi").pcm == b"new.wav/own:Hi"  # nothing learned again
    assert clone.prepared == [("a.wav", "british")]


def test_a_clone_that_fails_to_unload_stays_counted_and_is_tried_again(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Codex's review of PR #273: a clone not freed is never left out of the count.
    budget = CloneBudget(1)
    sites = site_clones(budget, "ab")
    forget = sites["a"][1].forget_voice
    sites["a"][1].forget_voice = MagicMock(side_effect=RuntimeError("busy"))  # type: ignore[method-assign]
    sites["a"][0].prepare("a.wav", "british")
    with caplog.at_level(logging.ERROR), pytest.raises(VoiceError, match="voice memory is full"):
        sites["b"][0].prepare("b.wav", OWN)
    assert "Clone not unloaded" in caplog.text and "Clone not loaded" in caplog.text
    assert budget.loaded() == ["a"] and sites["b"][1].prepared == []
    # Site a still speaks, not unloaded, so not learned again.
    assert sites["a"][0].speak("a.wav", "Hi").pcm == b"a.wav/british:Hi"
    assert sites["a"][1].prepared == [("a.wav", "british")]
    # Once it can be freed, the next site's clone loads in its place.
    sites["a"][1].forget_voice = forget  # type: ignore[method-assign]
    sites["b"][0].prepare("b.wav", OWN)
    assert budget.loaded() == ["b"] and sites["a"][1].unloaded == 1


def test_a_clone_that_fails_to_unload_makes_way_for_the_next_least_recently_used() -> None:
    budget = CloneBudget(2)
    sites = site_clones(budget, "abc")
    sites["a"][1].forget_voice = MagicMock(side_effect=RuntimeError("busy"))  # type: ignore[method-assign]
    for name in "abc":
        sites[name][0].prepare(f"{name}.wav", OWN)
    assert budget.loaded() == ["a", "c"] and sites["b"][1].unloaded == 1


def test_the_budget_keeps_at_least_one_clone() -> None:
    with pytest.raises(ValueError):
        CloneBudget(0)


def test_clones_loaded_is_set_in_the_config(tmp_path: Path) -> None:
    assert load_settings(None).clones_loaded == 2
    config = tmp_path / "config.toml"
    config.write_text("clones_loaded = 3\n")
    assert load_settings(config).clones_loaded == 3
    assert make_engines(tmp_path, face_checks=False, clones_loaded=3).clones.max_loaded == 3
    for wrong in ("0", "true", '"2"'):
        config.write_text(f"clones_loaded = {wrong}\n")
        with pytest.raises(ConfigError, match="clones_loaded"):
            load_settings(config)


def test_the_site_keeps_its_clone_in_the_budget(tmp_path: Path) -> None:
    budget = CloneBudget(2)
    with (
        patch("imageskin.chatterbox_engine.check_installed"),
        patch("imageskin.pocket_engine.usable", return_value=False),
    ):
        step, engine, voice, kind = clip_voice(
            tmp_path / "voice-sample.wav",
            lambda: OWN,
            MagicMock(),
            MagicMock(),
            lambda clone: budget.engine(clone, "a"),
        )
    assert isinstance(engine, SiteClone) and engine.site == "a" and kind == "clone"
    assert isinstance(engine._clone, AccentEngine)


def test_jobs_of_other_sites_take_turns_in_the_order_they_asked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    turns = Turns(poll_s=0.01)
    order: list[str] = []
    started = threading.Event()
    release = threading.Event()
    waited: list[str] = []

    def job(name: str, site: str, hold: bool = False) -> None:
        with turns.turn(name, site, lambda: waited.append(name)):
            order.append(name)
            if hold:
                started.set()
                assert release.wait(5)

    with caplog.at_level(logging.INFO, logger="imageskin.across_sites"):
        first = threading.Thread(target=job, args=("a1", "a", True))
        first.start()
        assert started.wait(5) and turns.holder() == "a"
        later = []
        # Site a's next job waits too, as other sites asked first.
        for name in ("b1", "c1", "a2"):
            t = threading.Thread(target=job, args=(name, name[0]))
            t.start()
            later.append(t)
            deadline = time.monotonic() + 5
            while name not in waited:
                assert time.monotonic() < deadline
                time.sleep(0.005)
        release.set()
        for t in [first, *later]:
            t.join(5)
    assert order == ["a1", "b1", "c1", "a2"]
    assert {"b1", "c1", "a2"} <= set(waited) and "a1" not in waited
    done = [r for r in caplog.records if r.__dict__.get("done")]
    assert {r.__dict__["job"] for r in done} == {"b1", "c1", "a2"}
    assert all(r.__dict__["waited_ms"] > 0 and r.__dict__["site"] for r in done)
    assert turns.holder() is None


def test_a_sites_own_jobs_run_together() -> None:
    turns = Turns(poll_s=0.01)
    with turns.turn("prepare", "a", lambda: pytest.fail("no wait")):
        with turns.turn("pdf-reading", "a", lambda: pytest.fail("no wait")):
            assert turns.holder() == "a"
        assert turns.holder() == "a"
    assert turns.holder() is None


def test_a_job_that_stops_waiting_leaves_the_queue(caplog: pytest.LogCaptureFixture) -> None:
    turns = Turns(poll_s=0.01)

    def give_up() -> None:
        raise KeyError("removed")

    with turns.turn("prepare", "a", lambda: None):
        with caplog.at_level(logging.INFO), pytest.raises(KeyError):
            with turns.turn("pdf-reading", "b", give_up):
                pytest.fail("never runs")
    assert "Stopped waiting for another site" in caplog.text
    with turns.turn("pdf-reading", "c", lambda: pytest.fail("no wait")):
        assert turns.holder() == "c"


def prepare_job(home: Path, turns: Turns, site: str, face: Any = face_in_steps) -> PrepareJob:
    home.mkdir(parents=True)
    return PrepareJob(
        home,
        cast(UploadStore, FakeStore(home)),
        lambda: None,
        face,
        write_clip,
        turns=turns,
        site=site,
    )


def test_prepare_and_pdf_reading_on_two_sites_run_one_after_the_other(tmp_path: Path) -> None:
    turns = Turns(poll_s=0.01)
    lock = threading.Lock()
    running: list[str] = []
    most = [0]
    seen_waiting: dict[str, Any] = {}

    def busy(name: str) -> None:
        with lock:
            running.append(name)
            most[0] = max(most[0], len({n[0] for n in running}))
        time.sleep(0.1)
        with lock:
            running.remove(name)

    def face(site: str) -> Any:
        def prepare_face(photo: Path, progress: PrepareProgress) -> None:
            busy(site + "-prepare")
            face_in_steps(photo, progress)

        return prepare_face

    def read(site: str) -> Any:
        def read_pdf(path: Path, progress: Progress) -> Reading:
            busy(site + "-reading")
            return Reading("text", 1, [Piece(1, "paragraph", f"From {site}.")], [])

        return read_pdf

    jobs = {s: prepare_job(tmp_path / s / "prep", turns, s, face(s)) for s in "ab"}
    stores = {s: ContentStore(tmp_path / s) for s in "ab"}
    readings = {s: ReadingJob(stores[s], read(s), turns=turns, site=s) for s in "ab"}
    pdfs = {s: stores[s].add(f"{s}.pdf", io.BytesIO(PDF)) for s in "ab"}
    for s in "ab":
        jobs[s].start()
        readings[s].queue(pdfs[s])
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and len(seen_waiting) < 1:
        for s in "ab":
            steps = jobs[s].status().steps or []
            if steps[0].activity == WAITING:
                seen_waiting["prepare-" + s] = True
            if readings[s].statuses().get(pdfs[s].id, ReadingStatus("done")).activity == WAITING:
                seen_waiting["reading-" + s] = True
        time.sleep(0.005)
    for s in "ab":
        jobs[s].wait(10)
        readings[s].wait(10)

    assert seen_waiting  # the site that waited said so
    assert most[0] == 1  # never two sites at once
    for s, other in (("a", "b"), ("b", "a")):
        assert jobs[s].status().state == "done"
        assert (tmp_path / s / "prep" / "clips" / "sample.mp4").is_file()
        assert not (tmp_path / other / "content" / "read" / f"{pdfs[s].id}.json").exists()
        assert readings[s].statuses()[pdfs[s].id].state == "done"
        assert readings[s].reading(pdfs[s].id)["pieces"][0]["text"] == f"From {s}."  # type: ignore[index]
        assert stores[other].get(pdfs[s].id) is None


def test_prepare_cancelled_while_it_waits_is_cancelled(tmp_path: Path) -> None:
    turns = Turns(poll_s=0.01)
    job = prepare_job(tmp_path / "a", turns, "a")
    with turns.turn("prepare", "b", lambda: None):
        job.start()
        deadline = time.monotonic() + 5
        while (job.status().steps or [])[0].activity != WAITING:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        job.cancel()
        job.wait(5)
    status = job.status()
    assert status.state == "cancelled" and not status.cancelling
    assert all(s.activity is None for s in status.steps or [])


def test_a_pdf_removed_while_it_waits_is_not_read(tmp_path: Path) -> None:
    turns = Turns(poll_s=0.01)
    store = ContentStore(tmp_path)
    job = ReadingJob(store, lambda p, progress: pytest.fail("not read"), turns=turns)
    pdf = store.add("a.pdf", io.BytesIO(PDF))
    with turns.turn("prepare", "other", lambda: None):
        job.queue(pdf)
        deadline = time.monotonic() + 5
        while job.statuses()[pdf.id] != ReadingStatus("waiting", activity=WAITING):
            assert time.monotonic() < deadline
            time.sleep(0.01)
        store.remove(pdf.id)
        job.forget(pdf.id)
        job.wait(5)
    assert job.statuses() == {} and job.reading(pdf.id) is None


def test_two_sites_apps_share_the_turns_and_the_clone_budget(tmp_path: Path) -> None:
    engines = make_engines(tmp_path / "service", face_checks=False)
    apps = [
        create_app(
            tmp_path / name,
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=lambda photo, text, output: None,
            ask_llm=MagicMock(),
            engines=engines,
            site=name,
        )
        for name in "ab"
    ]
    for app, name in zip(apps, "ab", strict=True):
        assert app.state.prepare_job._turns is engines.turns
        assert app.state.prepare_job._site == name
        assert app.state.readings._turns is engines.turns


def test_two_sites_waiting_for_room_never_load_more_than_the_budget() -> None:
    budget = CloneBudget(1)
    sites = site_clones(budget, "abc")
    memory = Resident()
    for _, clone in sites.values():
        memory.counted(clone)
    sites["a"][0].prepare("a.wav", OWN)
    unloading, finish = threading.Event(), threading.Event()
    forget = sites["a"][1].forget_voice

    def slow_unload() -> None:
        unloading.set()
        assert finish.wait(5)
        forget()

    sites["a"][1].forget_voice = slow_unload  # type: ignore[method-assign]
    b = threading.Thread(target=sites["b"][0].prepare, args=("b.wav", OWN))
    b.start()
    assert unloading.wait(5)
    c = threading.Thread(target=sites["c"][0].prepare, args=("c.wav", OWN))
    c.start()  # waits while a is being unloaded for b
    time.sleep(0.05)
    finish.set()
    b.join(5)
    c.join(5)
    assert sites["b"][1].prepared and sites["c"][1].prepared
    assert memory.most == 1 and len(budget.loaded()) == 1
