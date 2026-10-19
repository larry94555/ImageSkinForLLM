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
from imageskin.prepare_job import PrepareError
from imageskin.voice import Speech

CHOICE = sn.Choice("female", "British", "animated", "Professor")


@pytest.fixture
def pack(tmp_path: Path) -> Path:
    """A real, small pack of the person CHOICE names."""
    library = tmp_path / "lib"
    fake_library(library, np.random.default_rng(1))
    picture = tmp_path / "pic.png"
    picture.write_bytes(b"picture bytes")
    person = next(p for p in dp.people() if p.name == CHOICE.name)
    out = tmp_path / "served" / f"{CHOICE.name}.zip"
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
    assert start.status() == sn.StartStatus("ready", CHOICE.name, 100)
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
    assert start.status().error == sn.NOT_READY
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
    assert seen[0] == sn.StartStatus("downloading", CHOICE.name, 50)
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
        "chosen": None,
    }
    assert client.get("/api/review").status_code == 403  # no consent and no default person
    assert client.get("/api/start-now/picture").status_code == 404
    assert client.get("/api/start-now/lines/goodbye").status_code == 404


def test_a_bad_choice_is_refused(client: TestClient) -> None:
    refused = client.post("/api/start-now", json={**vars(CHOICE), "role": "Duke"})
    assert refused.status_code == 400 and "Duke" in refused.json()["detail"]


def test_a_default_person_opens_the_chat_without_consent(client: TestClient) -> None:
    status = choose(client)
    assert status["state"] == "ready" and status["chosen"] == vars(CHOICE)
    assert client.get("/api/review").json()["accepted"] is True
    assert client.get("/api/start-now/picture").content == b"picture bytes"
    assert client.get("/api/start-now/lines/goodbye").content == b"mp4"
    assert client.get("/api/start-now/lines/sample").status_code == 422
    photo = client.get("/api/chat/photo").json()
    assert photo["url"] == "/api/start-now/picture"
    reply = client.post("/api/chat", json={"prompt": "Hi"})
    assert reply.status_code == 200 and reply.json()["content"] == "Hello there"
    # The uploads still need consent.
    assert client.get("/api/uploads/photos").status_code == 403


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
