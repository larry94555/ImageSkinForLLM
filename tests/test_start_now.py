"""Start now with a default person (roadmap R24c)."""

import functools
import http.server
import json
import logging
import shutil
import threading
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from test_default_people import fake_library

from imageskin import default_people as dp
from imageskin import start_now as sn
from imageskin.app import create_app
from imageskin.download import DownloadError, sha256_of
from imageskin.prepare_job import ClipSteps, PrepareError, remaining
from imageskin.reply_video import ReplyVideos, VoiceReady
from imageskin.voice import Speech

CHOICE = sn.Choice("female", "British", "animated", "Professor")


@pytest.fixture
def pack(tmp_path: Path) -> Path:
    """A real, small pack of the person CHOICE names."""
    return make_pack(tmp_path, b"picture bytes")


def make_pack(tmp_path: Path, picture_bytes: bytes, served: str = "served") -> Path:
    library = tmp_path / f"lib-{served}"
    fake_library(library, np.random.default_rng(1))
    picture = tmp_path / f"pic-{served}.png"
    picture.write_bytes(picture_bytes)
    person = next(p for p in dp.people() if p.name == CHOICE.name)
    out = tmp_path / served / f"{CHOICE.name}.zip"
    out.parent.mkdir()
    dp.pack(person, picture, library, out)
    return out


class Fetcher:
    """Stands in for download(): copies the served pack, telling progress on the way."""

    def __init__(self, pack: Path, error: Exception | None = None) -> None:
        self.pack = pack
        self.error = error
        self.urls: list[str] = []
        self.kwargs: dict[str, Any] = {}

    def __call__(self, url: str, dest: Path, size: int, sha256: str, **kwargs: Any) -> None:
        self.urls.append(url)
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        assert size == self.pack.stat().st_size and sha256 == sha256_of(self.pack)
        kwargs["progress"](size // 2, size)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.pack, dest)


def renderer(said: list[str]) -> sn.RenderClip:
    def render(picture: Path, text: str, output: Path) -> None:
        assert picture.is_file()
        said.append(text)
        output.write_bytes(b"mp4")

    return render


def packs_of(pack: Path) -> dict[str, dict[str, Any]]:
    return {CHOICE.name: {"bytes": pack.stat().st_size, "sha256": sha256_of(pack)}}


def started(home: Path, pack: Path, **kwargs: Any) -> sn.StartNow:
    kwargs.setdefault("fetch", Fetcher(pack))
    kwargs.setdefault("render_clip", renderer([]))
    return sn.StartNow(home, packs=packs_of(pack), base_url="https://x/rel", **kwargs)


def test_a_choice_names_the_person_and_the_voice() -> None:
    assert CHOICE.name == "animated_female_professor"
    assert CHOICE.voice == ("b", "bf_emma")
    assert CHOICE.problem() is None
    assert "Duke" in (sn.Choice("female", "British", "animated", "Duke").problem() or "")
    assert sn.Choice("male", "Irish", "animated", "Boss").problem()


def test_a_choice_can_pick_its_second_face() -> None:
    """R24c2: 24 of the 36 choices have a second face, which names its own person."""
    second = sn.Choice("female", "British", "animated", "Professor", face=2)
    assert second.problem() is None and second.name == "animated_female_professor_2"
    assert sn.faces("female", "animated", "Professor") == {
        1: "animated_female_professor",
        2: "animated_female_professor_2",
    }
    assert sn.faces("female", "animated", "Boss") == {1: "animated_female_boss"}
    one_face = sn.Choice("female", "British", "animated", "Boss", face=2)
    assert one_face.problem() == "There is no face 2 for that choice."
    assert sn.Choice("female", "British", "animated", "Professor", face=3).problem()
    assert sum(len(sn.faces(*c)) == 2 for c in combinations()) == 24


def combinations() -> list[tuple[str, str, str]]:
    return [(g, r, role) for g in dp.GENDERS for r in dp.REALISMS for role in dp.ROLES]


def test_every_face_has_a_thumbnail_that_ships_with_the_app() -> None:
    faces = Path(__file__).parents[1] / "web" / "public" / "faces"
    assert {f.stem for f in faces.glob("*.jpg")} == {p.name for p in dp.people()}


def test_the_face_picked_is_kept_and_an_older_choice_has_the_first(
    tmp_path: Path, pack: Path
) -> None:
    person = started(tmp_path, pack)
    person._save(sn.Choice("female", "British", "animated", "Professor", face=2))
    assert person.chosen() == sn.Choice("female", "British", "animated", "Professor", 2)
    (tmp_path / sn.CHOICE_FILE).write_text(
        json.dumps({"gender": "female", "accent": "British", "realism": "animated", "role": "Boss"})
    )
    assert person.chosen() == sn.Choice("female", "British", "animated", "Boss", 1)


def test_every_person_has_a_pack_of_at_most_50_mb() -> None:
    packs = sn.load_packs()
    assert set(packs) == {p.name for p in dp.people()}
    assert all(
        0 < p["bytes"] <= dp.MAX_PACK_BYTES and len(p["sha256"]) == 64 for p in packs.values()
    )


def test_start_downloads_unpacks_and_says_the_lines(
    tmp_path: Path, pack: Path, caplog: pytest.LogCaptureFixture
) -> None:
    said: list[str] = []
    fetch = Fetcher(pack)
    ready = threading.Event()
    start = started(tmp_path, pack, fetch=fetch, render_clip=renderer(said), on_ready=ready.set)
    assert start.chosen() is None and start.picture() is None and start.voice() is None
    with caplog.at_level(logging.INFO, logger="imageskin.start_now"):
        first = start.start(CHOICE)
        start.wait(10)
    assert first.state == "downloading" and first.person == CHOICE.name
    # Ready, with about the chat's usual time left for its video (R176).
    assert start.status() == sn.StartStatus("ready", CHOICE.name, 100, left_s=10)
    assert ready.is_set()
    assert fetch.urls == [f"https://x/rel/{CHOICE.name}.zip"]
    assert fetch.kwargs["retries"] == 1  # the user is waiting: give up soon, Try again resumes
    assert start.chosen() == CHOICE
    assert start.picture() == tmp_path / "default-people" / f"{CHOICE.name}.png"
    assert start.voice() == ("b", "bf_emma")
    assert said == ["Goodbye.", "Welcome back."]
    assert start.clip("goodbye") is not None and start.clip("welcome-back") is not None
    assert start.clip("sample") is None
    # Kept, so the library can be unpacked again after Delete my data without a download.
    assert (tmp_path / "default-people" / "downloads" / f"{CHOICE.name}.zip").is_file()
    for message in ("Downloaded default person", "Rendered default person's line"):
        assert message in caplog.text
    record = next(r for r in caplog.records if r.getMessage() == "Default person ready")
    assert vars(record)["duration_s"] >= 0


def test_a_person_downloaded_before_is_ready_at_once(tmp_path: Path, pack: Path) -> None:
    first = started(tmp_path, pack)
    first.start(CHOICE)
    first.wait(10)
    fetch = Fetcher(pack)
    again = started(tmp_path, pack, fetch=fetch, render_clip=renderer([]))
    (tmp_path / sn.CHOICE_FILE).unlink()
    assert again.start(CHOICE).state == "ready"
    assert fetch.urls == [] and again.chosen() == CHOICE


def test_the_other_accent_needs_only_its_lines(tmp_path: Path, pack: Path) -> None:
    first = started(tmp_path, pack)
    first.start(CHOICE)
    first.wait(10)
    fetch, said = Fetcher(pack), list[str]()
    again = started(tmp_path, pack, fetch=fetch, render_clip=renderer(said))
    american = sn.Choice("female", "American", "animated", "Professor")
    again.start(american)
    again.wait(10)
    assert again.status().state == "ready" and fetch.urls == []
    assert said == ["Goodbye.", "Welcome back."] and again.voice() == ("a", "af_heart")


def test_a_changed_voice_says_the_lines_again_at_start_up(
    tmp_path: Path, pack: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    first = started(tmp_path, pack)
    with caplog.at_level(logging.INFO):
        first.start(CHOICE)
        first.wait(10)
    chosen = next(r for r in caplog.records if r.getMessage() == "Default voice chosen")
    assert vars(chosen)["person"] == CHOICE.name and vars(chosen)["voice"] == "bf_emma"
    # Nothing to do while the lines are there in the person's voice, or nobody is chosen.
    assert first.refresh() is False
    assert started(tmp_path / "nobody", pack).refresh() is False

    # A new version of the app gives the person another voice (R24e).
    monkeypatch.setattr(sn, "voice_of", lambda name, accent: ("b", "bf_emma,af_kore"))
    fetch, said = Fetcher(pack), list[str]()
    again = started(tmp_path, pack, fetch=fetch, render_clip=renderer(said))
    assert again.clip("goodbye") is None  # not yet in the new voice
    assert again.refresh() is True
    again.wait(10)
    assert again.status().state == "ready" and fetch.urls == []
    assert said == ["Goodbye.", "Welcome back."] and again.voice() == ("b", "bf_emma,af_kore")
    goodbye = again.clip("goodbye")
    assert goodbye is not None and goodbye.parent.name.endswith("_british_bf_emma+af_kore")


def test_refreshing_the_lines_keeps_the_avatar_in_the_users_own_voice(
    tmp_path: Path, pack: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = started(tmp_path, pack)
    first.start(CHOICE)
    first.wait(10)
    first.set_own_voice(True)  # R24d
    monkeypatch.setattr(sn, "voice_of", lambda name, accent: ("b", "bf_emma,af_kore"))
    claims: list[str] = []
    again = started(
        tmp_path,
        pack,
        claim=lambda: claims.append("claim"),
        release=lambda: claims.append("release"),
    )
    assert again.refresh() is True
    again.wait(10)
    assert again.status().state == "ready" and claims == ["claim", "release"]
    assert again.own_voice() is True and again.chosen() == CHOICE
    assert again.clip("goodbye") is not None


def remade(tmp_path: Path) -> Path:
    """The same person's pack made again with a new face, as R24b4 did for four people."""
    return make_pack(tmp_path, b"the new face", served="remade")


def test_a_remade_pack_replaces_the_old_face_before_the_person_is_ready(
    tmp_path: Path, pack: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Codex's review of PR #165: the old picture, library and lines were taken as ready.
    first = started(tmp_path, pack)
    first.start(CHOICE)
    first.wait(10)
    second_face = tmp_path / "default-people" / "lines" / f"{CHOICE.name}_2_british_bf_emma"
    second_face.mkdir()
    new = remade(tmp_path)
    fetch, said = Fetcher(new), list[str]()
    again = started(tmp_path, new, fetch=fetch, render_clip=renderer(said))
    with caplog.at_level(logging.INFO):
        assert again.start(CHOICE).state == "downloading"
        again.wait(10)
    assert again.status().state == "ready" and len(fetch.urls) == 1
    picture = again.picture()
    assert picture is not None and picture.read_bytes() == b"the new face"
    assert said == ["Goodbye.", "Welcome back."]  # said again by the new face
    assert second_face.is_dir()  # the second face's lines are its own
    assert any(r.getMessage() == "Default person's pack changed" for r in caplog.records)
    assert started(tmp_path, new, fetch=fetch).start(CHOICE).state == "ready"
    assert len(fetch.urls) == 1


def test_a_remade_pack_is_got_at_start_up_keeping_the_choice(tmp_path: Path, pack: Path) -> None:
    first = started(tmp_path, pack)
    first.start(CHOICE)
    first.wait(10)
    first.set_own_voice(True)
    new = remade(tmp_path)
    fetch, said = Fetcher(new), list[str]()
    again = started(tmp_path, new, fetch=fetch, render_clip=renderer(said))
    assert again.refresh() is True
    again.wait(10)
    assert again.status().state == "ready" and len(fetch.urls) == 1
    assert again.own_voice() is True and again.chosen() == CHOICE
    picture = again.picture()
    assert picture is not None and picture.read_bytes() == b"the new face"
    assert said == ["Goodbye.", "Welcome back."] and again.refresh() is False


@pytest.mark.parametrize("held_open", [False, True])
def test_a_remade_pack_has_its_idle_video_made_again_from_the_new_face(
    tmp_path: Path, pack: Path, monkeypatch: pytest.MonkeyPatch, held_open: bool
) -> None:
    # Codex's reviews of PR #165: the chat's idle video was kept by the picture's name, so
    # the old face's stayed, above all while a browser held it open (as on Windows).
    def idle(photo: Path, output: Path) -> None:
        output.write_bytes(photo.read_bytes())

    picture = tmp_path / "default-people" / f"{CHOICE.name}.png"
    replies = ReplyVideos(
        tmp_path,
        renderer([]),
        VoiceReady(lambda: None, lambda: "v"),
        ClipSteps(lambda text, wav: None, lambda photo, wav, output: None, idle),
    )
    first = started(tmp_path, pack, on_ready=lambda: replies.warm_up(picture))
    first.start(CHOICE)
    first.wait(10)
    old = replies.idle(picture)
    assert old is not None and old.read_bytes() == b"picture bytes"
    real_unlink = Path.unlink

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if self == old:
            raise PermissionError("open in the browser")
        real_unlink(self, missing_ok)

    if held_open:
        monkeypatch.setattr(Path, "unlink", unlink)
    new = remade(tmp_path)
    again = started(tmp_path, new, on_ready=lambda: replies.warm_up(picture))
    assert again.refresh() is True
    again.wait(10)
    remade_idle = replies.idle(picture)
    assert remade_idle is not None and remade_idle.read_bytes() == b"the new face"
    assert old.exists() is held_open
    monkeypatch.undo()  # the browser lets go: the next warm-up removes the old one
    replies.warm_up(picture)
    assert not old.exists() and replies.idle(picture) == remade_idle


def test_a_person_unpacked_before_the_pack_was_noted_is_told_by_the_kept_pack(
    tmp_path: Path, pack: Path
) -> None:
    first = started(tmp_path, pack)
    first.start(CHOICE)
    first.wait(10)
    noted = tmp_path / "default-people" / f"{CHOICE.name}.pack"
    noted.unlink()  # as left by an older version of the app
    fetch = Fetcher(pack)
    assert started(tmp_path, pack, fetch=fetch).start(CHOICE).state == "ready"
    assert fetch.urls == [] and noted.read_text() == sha256_of(pack)
    # Older still, with a kept pack that is not the one named now: downloaded again.
    noted.unlink()
    new = remade(tmp_path)
    fetch = Fetcher(new)
    again = started(tmp_path, new, fetch=fetch)
    again.start(CHOICE)
    again.wait(10)
    assert again.status().state == "ready" and len(fetch.urls) == 1


def test_lines_that_cant_be_rendered_again_say_so(
    tmp_path: Path, pack: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    first = started(tmp_path, pack)
    first.start(CHOICE)
    first.wait(10)
    monkeypatch.setattr(sn, "voice_of", lambda name, accent: ("b", "bf_emma,af_kore"))

    def broken(picture: Path, text: str, output: Path) -> None:
        raise RuntimeError("no engine")

    released: list[bool] = []
    again = started(tmp_path, pack, render_clip=broken, release=lambda: released.append(True))
    with caplog.at_level(logging.ERROR):
        assert again.refresh() is True
        again.wait(10)
    error = again.status().error or ""
    assert again.status().state == "failed" and error.startswith(sn.NOT_READY)
    assert "Reference for support: P-" in error
    assert released == [True] and again.chosen() == CHOICE
    assert any(r.getMessage() == "Could not render the lines again" for r in caplog.records)


@pytest.mark.parametrize(
    ("error", "message"),
    [(DownloadError("offline"), sn.DOWNLOAD_FAILED), (dp.PackError("bad"), sn.DAMAGED)],
)
def test_a_failed_download_says_so_and_chooses_nobody(
    tmp_path: Path, pack: Path, error: Exception, message: str, caplog: pytest.LogCaptureFixture
) -> None:
    start = started(tmp_path, pack, fetch=Fetcher(pack, error))
    with caplog.at_level(logging.ERROR):
        start.start(CHOICE)
        start.wait(10)
    assert start.status() == sn.StartStatus("failed", CHOICE.name, 0, message)
    assert start.chosen() is None
    assert any(vars(r).get("error") == str(error) for r in caplog.records)
    # Try again starts over.
    start._fetch = Fetcher(pack)
    start.start(CHOICE)
    start.wait(10)
    assert start.status().state == "ready"


def test_a_pack_not_uploaded_yet_says_so(tmp_path: Path, pack: Path) -> None:
    not_found = urllib.error.HTTPError("https://x/rel/p.zip", 404, "Not Found", Message(), None)
    error = DownloadError("gave up")
    error.__cause__ = not_found
    start = started(tmp_path, pack, fetch=Fetcher(pack, error))
    start.start(CHOICE)
    start.wait(10)
    assert start.status().error == sn.NOT_PUBLISHED


def test_a_real_404_from_the_release_says_not_available(tmp_path: Path, pack: Path) -> None:
    """download() keeps the server's 404 as the cause of the DownloadError it raises."""
    empty = tmp_path / "release"
    empty.mkdir()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(empty))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        start = sn.StartNow(tmp_path / "home", renderer([]), packs=packs_of(pack), base_url=url)
        start.start(CHOICE)
        start.wait(30)
    finally:
        server.shutdown()
    assert start.status().error == sn.NOT_PUBLISHED


def test_the_packs_can_come_from_elsewhere(
    tmp_path: Path, pack: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(sn.URL_VARIABLE, "http://127.0.0.1:9100/")
    fetch = Fetcher(pack)
    start = sn.StartNow(tmp_path, renderer([]), packs=packs_of(pack), fetch=fetch)
    start.start(CHOICE)
    start.wait(10)
    assert fetch.urls == [f"http://127.0.0.1:9100/{CHOICE.name}.zip"]


def test_a_damaged_pack_is_refused(tmp_path: Path, pack: Path) -> None:
    pack.write_bytes(b"not a zip")
    start = started(tmp_path, pack)
    start.start(CHOICE)
    start.wait(10)
    assert start.status().error == sn.DAMAGED and start.chosen() is None


def test_a_person_with_no_pack_is_refused(tmp_path: Path, pack: Path) -> None:
    start = started(tmp_path, pack)
    start.start(sn.Choice("male", "British", "animated", "Boss"))
    start.wait(10)
    assert start.status().error == sn.DAMAGED


def test_a_failed_render_says_so(
    tmp_path: Path, pack: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(picture: Path, text: str, output: Path) -> None:
        raise RuntimeError("no ffmpeg")

    start = started(tmp_path, pack, render_clip=broken)
    with caplog.at_level(logging.ERROR):
        start.start(CHOICE)
        start.wait(10)
    error = start.status().error or ""
    assert error.startswith(f"{sn.NOT_READY} Something unexpected went wrong. Click Try again.")
    [logged] = [r for r in caplog.records if r.getMessage().startswith("Could not get")]
    assert error.endswith(f"Reference for support: {vars(logged)['reference']}.")
    assert any(r.exc_info and "no ffmpeg" in str(r.exc_info[1]) for r in caplog.records)


def test_a_second_start_while_one_runs_reports_on_it(tmp_path: Path, pack: Path) -> None:
    go = threading.Event()

    def slow(picture: Path, text: str, output: Path) -> None:
        go.wait(10)
        output.write_bytes(b"mp4")

    start = started(tmp_path, pack, render_clip=slow)
    start.start(CHOICE)
    other = start.start(sn.Choice("male", "American", "photoreal", "Boss"))
    assert other.person == CHOICE.name
    go.set()
    start.wait(10)
    assert start.status().state == "ready"


def test_the_lines_are_spoken_in_the_persons_voice_only_while_rendered(
    tmp_path: Path, pack: Path
) -> None:
    # Prepare's engines render the lines, and speak the person's own voice otherwise.
    voices: list[tuple[str, str] | None] = []
    start = started(tmp_path, pack)

    def render(picture: Path, text: str, output: Path) -> None:
        voices.append(start.rendering_voice())
        output.write_bytes(b"mp4")

    start._render_clip = render
    assert start.rendering_voice() is None
    start.start(CHOICE)
    start.wait(10)
    assert voices == [CHOICE.voice, CHOICE.voice]
    assert start.rendering_voice() is None


def test_getting_a_person_ready_holds_the_prepare_job(tmp_path: Path, pack: Path) -> None:
    # Claimed before anything is written and given back only once nothing more is, and before
    # the person is reported ready, so Prepare can start as soon as the page sees it.
    held: list[str] = []
    start = started(tmp_path, pack)

    def render(picture: Path, text: str, output: Path) -> None:
        held.append(f"render {text}")
        output.write_bytes(b"mp4")

    start._render_clip = render
    start._claim = lambda: held.append("claim")
    start._release = lambda: held.append(f"release when {start.status().state}")
    start.start(CHOICE)
    start.wait(10)
    assert held == [
        "claim",
        "render Goodbye.",
        "render Welcome back.",
        "release when getting-ready",
    ]
    assert start.status().state == "ready"


def test_a_failed_start_gives_the_prepare_job_back(tmp_path: Path, pack: Path) -> None:
    held: list[str] = []
    start = started(
        tmp_path,
        pack,
        fetch=Fetcher(pack, DownloadError("offline")),
        claim=lambda: held.append("claim"),
        release=lambda: held.append("release"),
    )
    start.start(CHOICE)
    start.wait(10)
    assert held == ["claim", "release"] and start.status().state == "failed"


def test_a_start_refused_by_the_prepare_job_changes_nothing(tmp_path: Path, pack: Path) -> None:
    def busy() -> None:
        raise PrepareError("Setup is preparing your own video.")

    fetch = Fetcher(pack)
    start = started(tmp_path, pack, fetch=fetch, claim=busy)
    with pytest.raises(PrepareError):
        start.start(CHOICE)
    assert start.status().state == "idle" and fetch.urls == [] and start.chosen() is None


def test_progress_follows_the_download(tmp_path: Path, pack: Path) -> None:
    seen: list[sn.StartStatus] = []
    start = started(tmp_path, pack)

    def watch(picture: Path, text: str, output: Path) -> None:
        seen.append(start.status())
        output.write_bytes(b"mp4")

    start._render_clip = watch
    fetch = start._fetch

    def fetch_and_look(*args: Any, **kwargs: Any) -> None:
        fetch(*args, **kwargs)
        seen.append(start.status())

    start._fetch = fetch_and_look
    start.start(CHOICE)
    start.wait(10)
    assert (seen[0].state, seen[0].percent) == ("downloading", 50)
    assert seen[1].state == "getting-ready"


def test_forget_and_a_broken_choice_file(tmp_path: Path, pack: Path) -> None:
    start = started(tmp_path, pack)
    start.forget()  # nothing chosen: nothing to do
    (tmp_path / sn.CHOICE_FILE).write_text("{")
    assert start.chosen() is None
    (tmp_path / sn.CHOICE_FILE).write_text(json.dumps({**vars(CHOICE), "role": "Duke"}))
    assert start.chosen() is None
    (tmp_path / sn.CHOICE_FILE).write_text(json.dumps(vars(CHOICE)))
    assert start.chosen() == CHOICE
    assert start.picture() is None and start.clip("goodbye") is None  # not downloaded
    start.forget()
    assert start.chosen() is None


class Engine:
    def __init__(self, name: str) -> None:
        self.name = name
        self.said: list[tuple[str, str]] = []

    def speak(self, voice: str, text: str) -> Speech:
        self.said.append((voice, text))
        return Speech(b"", 24000, [])

    def forget_voice(self) -> str:
        return f"forgot {self.name}"


def test_preset_voice_speaks_in_the_default_persons_voice() -> None:
    own = Engine("own")
    made: dict[str, Engine] = {}
    preset: list[tuple[str, str] | None] = [None]
    voice = sn.PresetVoice(own, lambda: preset[0], lambda lang: made.setdefault(lang, Engine(lang)))
    voice.speak("their-voice", "Hi")
    preset[0] = ("b", "bf_emma")
    voice.speak("their-voice", "Hello")
    voice.speak("their-voice", "Again")
    assert own.said == [("their-voice", "Hi")]
    assert made["b"].said == [("bf_emma", "Hello"), ("bf_emma", "Again")]  # loaded once
    assert voice.forget_voice() == "forgot own"


def test_preset_voice_loads_kokoro_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    langs: list[str] = []

    def kokoro_for(lang: str) -> Engine:
        langs.append(lang)
        return Engine(lang)

    monkeypatch.setattr("imageskin.kokoro_engine.kokoro_for", kokoro_for)
    sn.PresetVoice(Engine("own"), lambda: ("a", "am_michael")).speak("x", "Hi")
    assert langs == ["a"]


# The app


@pytest.fixture
def client(tmp_path: Path, pack: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        "imageskin.app.StartNow",
        functools.partial(sn.StartNow, packs=packs_of(pack), fetch=Fetcher(pack)),
    )
    home = tmp_path / "home"
    return TestClient(
        create_app(
            home,
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=renderer([]),
            ask_llm=lambda messages: "Hello there",
        )
    )


def choose(client: TestClient) -> dict[str, Any]:
    started = client.post("/api/start-now", json=vars(CHOICE))
    assert started.status_code == 200
    client.app.state.start_now.wait(10)  # type: ignore[attr-defined]
    status: dict[str, Any] = client.get("/api/start-now").json()
    return status


def test_the_chat_is_locked_until_a_person_is_chosen(client: TestClient) -> None:
    assert client.get("/api/start-now").json() == {
        "state": "idle",
        "person": None,
        "percent": 0,
        "error": None,
        "left_s": None,
        "chosen": None,
        "chat_ready": False,
    }
    assert client.get("/api/review").status_code == 403  # no consent and no default person
    assert client.get("/api/start-now/picture").status_code == 404
    assert client.get("/api/start-now/lines/goodbye").status_code == 404


def test_a_nonbinary_person_is_a_choice_with_a_blended_voice() -> None:
    choice = sn.Choice("nonbinary", "British", "animated", "Boss")
    assert choice.problem() is None
    assert choice.name == "animated_nonbinary_boss"
    # Older (R24e): a blend of the accent's woman's voice and its lowest man's.
    assert choice.voice == ("b", "bf_emma,bm_lewis")
    assert sn.Choice("nonbinary", "American", "animated", "Parent").voice == (
        "a",
        "af_heart,am_michael",
    )
    assert "no face 2" in (sn.Choice("nonbinary", "British", "animated", "Boss", 2).problem() or "")


def test_a_bad_choice_is_refused(client: TestClient) -> None:
    refused = client.post("/api/start-now", json={**vars(CHOICE), "role": "Duke"})
    assert refused.status_code == 400 and "Duke" in refused.json()["detail"]
    no_face = client.post("/api/start-now", json={**vars(CHOICE), "face": 3})
    assert no_face.status_code == 400 and "no face 3" in no_face.json()["detail"]


def test_the_page_is_told_every_face(client: TestClient) -> None:
    faces = client.get("/api/start-now/faces").json()
    assert len(faces) == 68 and len({f["name"] for f in faces}) == 68
    assert {
        "gender": "female",
        "realism": "animated",
        "role": "Professor",
        "face": 2,
        "name": "animated_female_professor_2",
    } in faces
    # In the order the page shows them: by role, then face.
    women = [f["name"] for f in faces if (f["gender"], f["realism"]) == ("female", "photoreal")]
    assert women[:3] == [
        "photoreal_female_professor",
        "photoreal_female_professor_2",
        "photoreal_female_teaching_assistant",
    ]
    assert len(women) == 15 and women[-1] == "photoreal_female_business_consultant"
    # The page shows a look's women, men and nonbinary people together (no gender to pick): by
    # role, then face, then gender, so they take turns.
    photoreal = [f["name"] for f in faces if f["realism"] == "photoreal"]
    assert photoreal[:5] == [
        "photoreal_female_professor",
        "photoreal_male_professor",
        "photoreal_nonbinary_professor",
        "photoreal_female_professor_2",
        "photoreal_female_teaching_assistant",
    ]
    assert len(photoreal) == 34


def test_a_default_person_opens_the_chat_without_consent(client: TestClient) -> None:
    status = choose(client)
    assert status["state"] == "ready" and status["chosen"] == vars(CHOICE)
    assert client.get("/api/review").json()["accepted"] is True
    picture = client.get("/api/start-now/picture")
    assert picture.content == b"picture bytes" and picture.headers["cache-control"] == "no-cache"
    assert client.get("/api/start-now/lines/goodbye").content == b"mp4"
    assert client.get("/api/start-now/lines/sample").status_code == 422
    photo = client.get("/api/chat/photo").json()
    # Addresses of the person's own, so the browser can't show the person before from its cache.
    assert photo["url"] == f"/api/start-now/picture?person={CHOICE.name}"
    assert photo["idle"] == f"/api/chat/idle?photo={CHOICE.name}"
    reply = client.post("/api/chat", json={"prompt": "Hi"})
    assert reply.status_code == 200 and reply.json()["content"] == "Hello there"
    # The uploads still need consent.
    assert client.get("/api/uploads/photos").status_code == 403


def test_start_now_waits_for_the_new_persons_idle_video(client: TestClient, tmp_path: Path) -> None:
    """Larry's test of R32a: the chat opened on the person before. Ready is said only once the
    chat would show the new one: their idle video is made, or the warm-up making it has ended."""
    choose(client)
    client.app.state.reply_warm_up.join(10)  # type: ignore[attr-defined]
    warming = client.app.state.warm_up  # type: ignore[attr-defined]
    warming["running"] = True  # as while a warm-up runs
    status = client.get("/api/start-now").json()
    assert status["state"] == "ready" and status["chat_ready"] is False  # no idle video yet
    warming["running"] = False  # the warm-up ended, with or without one
    assert client.get("/api/start-now").json()["chat_ready"] is True
    warming["running"] = True
    picture = client.app.state.start_now.picture()  # type: ignore[attr-defined]
    idle = tmp_path / "home" / "replies" / "idle" / f"{picture.stem}-{sha256_of(picture)[:12]}.mp4"
    idle.parent.mkdir(parents=True, exist_ok=True)
    idle.write_bytes(b"mp4")
    assert client.get("/api/start-now").json()["chat_ready"] is True  # made, while it runs on


def test_the_warm_up_starts_before_ready_is_said(tmp_path: Path, pack: Path) -> None:
    states: list[str] = []
    people: list[sn.StartNow] = []
    person = started(tmp_path, pack, on_ready=lambda: states.append(people[0].status().state))
    people.append(person)
    person.start(CHOICE)
    person.wait(10)
    assert states == ["getting-ready"] and person.status().state == "ready"


def test_delete_my_data_forgets_the_default_person(client: TestClient) -> None:
    choose(client)
    assert client.delete("/api/data").status_code == 200
    assert client.get("/api/start-now").json()["chosen"] is None
    assert client.get("/api/review").status_code == 403


def test_replies_and_lines_share_one_kokoro_per_language() -> None:
    made: list[str] = []
    voices = sn.KokoroVoices(lambda lang: made.append(lang) or Engine(lang))  # type: ignore[func-returns-value]
    reply = sn.PresetVoice(Engine("own"), lambda: ("b", "bf_emma"), voices)
    lines = sn.PresetVoice(Engine("own"), lambda: ("b", "bm_george"), voices)
    reply.speak("x", "Hi")
    lines.speak("x", "Goodbye.")
    assert made == ["b"]


class Blocked(Fetcher):
    """A download that waits until the test lets it go on."""

    def __init__(self, pack: Path) -> None:
        super().__init__(pack)
        self.reached, self.go = threading.Event(), threading.Event()

    def __call__(self, url: str, dest: Path, size: int, sha256: str, **kwargs: Any) -> None:
        self.reached.set()
        assert self.go.wait(10)
        super().__call__(url, dest, size, sha256, **kwargs)


def blocked_client(
    tmp_path: Path, pack: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, Blocked]:
    fetch = Blocked(pack)
    monkeypatch.setattr(
        "imageskin.app.StartNow",
        functools.partial(sn.StartNow, packs=packs_of(pack), fetch=fetch),
    )
    client = TestClient(
        create_app(
            tmp_path / "home",
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=renderer([]),
            ask_llm=lambda messages: "Hello there",
        )
    )
    return client, fetch


def test_delete_my_data_waits_for_a_person_being_got_ready(
    tmp_path: Path, pack: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review on PR #113: a Start now still running must not write the choice, the library or
    # the lines again after Delete my data has returned.
    client, fetch = blocked_client(tmp_path, pack, monkeypatch)
    home = tmp_path / "home"
    assert client.post("/api/start-now", json=vars(CHOICE)).status_code == 200
    assert fetch.reached.wait(10)
    refused = client.delete("/api/data")
    assert refused.status_code == 409
    assert "default person is being got ready" in refused.json()["detail"]
    fetch.go.set()
    client.app.state.start_now.wait(10)  # type: ignore[attr-defined]
    assert client.get("/api/start-now").json()["state"] == "ready"
    assert client.delete("/api/data").status_code == 200
    assert not (home / sn.CHOICE_FILE).exists() and not (home / "photoreal").exists()
    assert client.get("/api/start-now").json()["chosen"] is None
    assert client.get("/api/review").status_code == 403


def test_prepare_and_start_now_never_run_together(
    tmp_path: Path, pack: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review on PR #113: they share the voice and video engines and the photoreal library.
    client, fetch = blocked_client(tmp_path, pack, monkeypatch)
    job = client.app.state.prepare_job  # type: ignore[attr-defined]
    assert client.post("/api/start-now", json=vars(CHOICE)).status_code == 200
    assert fetch.reached.wait(10)
    with pytest.raises(PrepareError, match="default person is being got ready"):
        job.start()
    fetch.go.set()
    client.app.state.start_now.wait(10)  # type: ignore[attr-defined]
    job.claim()  # as if Prepare were running: Start now is refused and nothing changes
    try:
        other = {**vars(CHOICE), "accent": "American"}
        refused = client.post("/api/start-now", json=other)
    finally:
        job.release()
    assert refused.status_code == 409
    assert client.get("/api/start-now").json()["chosen"] == vars(CHOICE)


def test_the_person_is_chosen_only_once_ready(tmp_path: Path, pack: Path) -> None:
    # Review on PR #113: while the lines are rendered, and after they fail, the chat stays
    # with whoever was chosen before.
    seen: list[sn.Choice | None] = []
    start = started(tmp_path, pack)

    def render(picture: Path, text: str, output: Path) -> None:
        seen.append(start.chosen())
        raise RuntimeError("no video engine")

    start._render_clip = render
    start.start(CHOICE)
    start.wait(10)
    assert seen == [None] and start.status().state == "failed"
    assert start.chosen() is None and not (tmp_path / sn.CHOICE_FILE).exists()


def test_choosing_the_person_pauses_the_replies(tmp_path: Path, pack: Path) -> None:
    events: list[str] = []
    start = started(tmp_path, pack)

    def activate(choose: Any) -> None:
        events.append(f"paused, chosen: {start.chosen() is not None}")
        choose()
        events.append(f"resumed, chosen: {start.chosen() is not None}")

    start._activate = activate
    start.start(CHOICE)
    start.wait(10)
    start.start(CHOICE)  # ready at once
    assert events == [
        "paused, chosen: False",
        "resumed, chosen: True",
        "paused, chosen: True",
        "resumed, chosen: True",
    ]


def test_choosing_the_same_person_after_delete_needs_no_download(
    client: TestClient, tmp_path: Path
) -> None:
    # Review on PR #113: Delete my data removes the library with photoreal/; the kept pack
    # puts it back, so neither a download nor preparing the face is needed.
    home = tmp_path / "home"
    choose(client)
    fetch = client.app.state.start_now._fetch  # type: ignore[attr-defined]
    assert len(fetch.urls) == 1
    assert client.delete("/api/data").status_code == 200
    assert not (home / "photoreal").exists()
    status = choose(client)
    assert status["state"] == "ready" and status["chosen"] == vars(CHOICE)
    assert len(fetch.urls) == 1  # not downloaded again
    assert list((home / "photoreal").glob("*/library.json"))


def test_the_packs_come_from_the_hosted_site_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(sn.URL_VARIABLE, raising=False)
    assert sn.packs_url() == "https://app.me0.ai/default-people"


def test_the_app_says_the_lines_again_at_start_up_in_a_changed_voice(
    tmp_path: Path, pack: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def app() -> TestClient:
        monkeypatch.setattr(
            "imageskin.app.StartNow",
            functools.partial(sn.StartNow, packs=packs_of(pack), fetch=Fetcher(pack)),
        )
        return TestClient(
            create_app(
                tmp_path / "home",
                prepare_voice=lambda: None,
                prepare_face=lambda photo, progress: None,
                render_clip=renderer([]),
                ask_llm=lambda messages: "Hello there",
            )
        )

    choose(app())
    monkeypatch.setattr(sn, "voice_of", lambda name, accent: ("b", "bf_emma,af_kore"))
    restarted = app()
    restarted.app.state.start_now.wait(10)  # type: ignore[attr-defined]
    assert restarted.get("/api/start-now/lines/goodbye").status_code == 200

    # Refused while Prepare runs: logged, and the app still starts.
    def refuse(self: sn.StartNow) -> bool:
        raise PrepareError("Prepare is running.")

    monkeypatch.setattr(sn.StartNow, "refresh", refuse)
    with caplog.at_level(logging.WARNING):
        assert app().get("/api/start-now").status_code == 200
    logged = [r.getMessage() for r in caplog.records]
    assert "Default person's lines not rendered again" in logged


def test_time_left_counts_down_to_the_chat(tmp_path: Path, pack: Path) -> None:
    """R176: about how long is left, from the download's pace and each stage's time, which the
    next person on this machine is then expected to take."""
    now = [0.0]
    start = started(tmp_path, pack, clock=lambda: now[0])
    assert start.status().left_s is None  # nothing being got ready
    start._set("downloading")
    assert start.status().left_s == 10 + 4 + 15 + 10  # every stage's usual time
    now[0] = 2.0
    start._set("downloading", 50)  # half of it in 2 s
    assert start.status().left_s == round(remaining(4, 2) + 4 + 15 + 10)
    now[0] = 3.0
    start._set("unpacking", 100)
    assert start.status().left_s == 4 + 15 + 10
    now[0] = 3.5
    start._set("getting-ready", 100)  # unpacked in 0.5 s: too quick to time
    now[0] = 23.5
    start._set("ready", 100)
    assert start.status().left_s == 10  # the chat's video
    now[0] = 25.5
    assert start.status().left_s == round(remaining(10, 2))
    start.chat_shown()
    start.chat_shown()  # timed once
    assert start.status().left_s is None
    times = json.loads((tmp_path / sn.TIMES_FILE).read_text())
    assert times == {"download": 3.0, "lines": 20.0, "chat": 2.0}
    again = started(tmp_path, pack, clock=lambda: now[0])
    again._set("downloading")
    assert again.status().left_s == 3 + 4 + 20 + 2


def test_no_time_left_once_failed_or_from_a_stage_skipped(tmp_path: Path, pack: Path) -> None:
    start = started(tmp_path, pack)
    start._set("getting-ready", 100)
    start._set("failed", error="No")
    assert start.status().left_s is None
    start._set("unpacking", 100)
    start._set("downloading")  # back to an earlier stage: nothing timed
    assert not (tmp_path / sn.TIMES_FILE).exists()


def test_times_that_cant_be_read_or_saved(
    tmp_path: Path, pack: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / sn.TIMES_FILE).write_text("[1, 2]")
    assert started(tmp_path, pack)._times == {}
    (tmp_path / sn.TIMES_FILE).write_text('{"lines": 7, "other": 1, "chat": "x"}')
    assert started(tmp_path, pack)._times == {"lines": 7.0}
    (tmp_path / sn.TIMES_FILE).write_text("{")
    with caplog.at_level(logging.ERROR, logger="imageskin.start_now"):
        start = started(tmp_path, pack)
        (tmp_path / sn.TIMES_FILE).unlink()
        (tmp_path / sn.TIMES_FILE).mkdir()  # can't be written
        start._timed("lines", 5.0)
    assert start._times == {"lines": 5.0}
    messages = [r.getMessage() for r in caplog.records]
    assert "Could not read the default person's times" in messages
    assert "Could not save the default person's times" in messages


def test_the_page_is_told_no_time_left_once_the_chat_shows_the_person(client: TestClient) -> None:
    status = choose(client)
    assert status["state"] == "ready" and status["chat_ready"] is True
    assert status["left_s"] is None
