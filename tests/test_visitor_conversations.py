"""Each visitor's own conversation (roadmap R65a): every browser on a site has a conversation of
its own, by a visitor cookie, which the LLM reads with that browser's questions only."""

import json
import logging
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_chat import FakeLlm2

from imageskin import admin
from imageskin.app import VISITOR_VIDEOS_FROM, create_app
from imageskin.prepare_job import PrepareJob, PrepareStatus
from imageskin.reply_video import ReplyVideos, VoiceReady
from imageskin.review import Review
from imageskin.uploads import PhotoResult, UploadStore, VoiceSample
from imageskin.visitor_chat import COOKIE, FOLDER, UNUSED_DAYS, VisitorConversations, key, valid

pytestmark = pytest.mark.real_hosts

HOST, PASSWORD = "host@example.com", "a long secret"
JPG = b"\xff\xd8\xff\xe0" + b"\0" * 100


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = admin.Secret("hash", admin.hash_password("nobody's password"))
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


@pytest.fixture(autouse=True)
def accepted() -> object:
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        yield


def write_video(photo: Path, text: str, output: Path) -> None:
    output.write_bytes(text.encode())


def site(home: Path, llm: FakeLlm2) -> FastAPI:
    return create_app(
        home,
        check_photo=lambda p: PhotoResult([], 80),
        prepare_voice=lambda: None,
        prepare_face=lambda photo, progress: None,
        render_clip=write_video,
        ask_llm=llm,
    )


def the_host(app: FastAPI, home: Path) -> TestClient:
    """The site's host, signed up, signed in and having consented, as setup asks."""
    if not (home / "hosts.json").exists():
        app.state.service.host_accounts.sign_up(HOST, PASSWORD, "test")
    host = TestClient(app)
    assert host.post("/api/host/sign-in", json={"email": HOST, "password": PASSWORD}).is_success
    host.post("/api/consent", json={"agreed": True})
    return host


def said(browser: TestClient) -> list[str]:
    return [t["content"] for t in browser.get("/api/chat").json()["turns"]]


def test_each_visitor_sees_and_continues_only_their_own_conversation(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    llm = FakeLlm2()
    app = site(tmp_path, llm)
    host = the_host(app, tmp_path)
    ann, bob = TestClient(app), TestClient(app)
    with caplog.at_level(logging.INFO):
        assert ann.post("/api/chat", json={"prompt": "I am Ann."}).status_code == 200
    assert "Visitor conversation started" in caplog.messages
    assert valid(ann.cookies.get(COOKIE))
    assert bob.post("/api/chat", json={"prompt": "I am Bob."}).status_code == 200
    assert bob.post("/api/chat", json={"prompt": "Who am I?"}).status_code == 200
    # Bob's question was sent with his own conversation only.
    sent = [m["content"] for m in llm.sent[-1] if m["role"] != "system"]
    assert "I am Bob." in sent and "I am Ann." not in sent
    assert said(ann) == ["I am Ann.", "Reply 1"]
    assert said(bob)[0::2] == ["I am Bob.", "Who am I?"]
    # The host has the site's own conversation, as before, apart from the visitors'.
    assert said(host) == []
    assert host.post("/api/chat", json={"prompt": "I am the host."}).is_success
    assert said(host)[0] == "I am the host."
    assert said(ann) == ["I am Ann.", "Reply 1"]
    # Kept apart on disk: by a hash of the cookie, never the cookie itself.
    files = sorted(p.name for p in (tmp_path / FOLDER).glob("*.json"))
    assert len(files) == 2
    assert f"{key(ann.cookies.get(COOKIE) or '')}.json" in files
    assert len(json.loads((tmp_path / "conversation.json").read_text())["turns"]) == 2


def test_a_visitors_conversation_is_still_there_after_a_restart(tmp_path: Path) -> None:
    app = site(tmp_path, FakeLlm2())
    the_host(app, tmp_path)
    ann = TestClient(app)
    ann.post("/api/chat", json={"prompt": "Remember me."})
    cookie = ann.cookies.get(COOKIE) or ""
    again = TestClient(site(tmp_path, FakeLlm2()))
    again.cookies.set(COOKIE, cookie)
    assert said(again) == ["Remember me.", "Reply 1"]
    stranger = TestClient(site(tmp_path, FakeLlm2()))
    assert said(stranger) == []


def test_a_made_up_cookie_gets_a_new_conversation(tmp_path: Path) -> None:
    app = site(tmp_path, FakeLlm2())
    the_host(app, tmp_path)
    answer = TestClient(app).get("/api/chat", cookies={COOKIE: "../../hosts"})
    assert answer.json()["turns"] == []
    given = answer.cookies.get(COOKIE)
    assert given != "../../hosts" and valid(given)


def test_clear_conversation_clears_only_the_hosts_and_delete_my_data_every_visitors(
    tmp_path: Path,
) -> None:
    app = site(tmp_path, FakeLlm2())
    host = the_host(app, tmp_path)
    ann = TestClient(app)
    ann.post("/api/chat", json={"prompt": "I am Ann."})
    host.post("/api/chat", json={"prompt": "I am the host."})
    assert host.delete("/api/chat").json() == {"cleared": 2}
    assert said(host) == []
    assert said(ann) == ["I am Ann.", "Reply 1"]
    assert ann.delete("/api/chat").status_code == 404  # Settings is the host's
    assert host.delete("/api/data").is_success
    assert not any((tmp_path / FOLDER).glob("*.json"))


def test_a_conversation_not_used_for_30_days_is_removed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    made: list[Path] = []

    def make(path: Path) -> Path:
        made.append(path)
        return path

    now = [time.time()]
    visitors = VisitorConversations(tmp_path, make, lambda: now[0])
    old, recent = visitors.of("a" * 32), visitors.of("b" * 32)
    for path in (old, recent):
        path.write_text("{}")
    os.utime(old, (now[0] - (UNUSED_DAYS + 1) * 86400,) * 2)
    os.utime(recent, (now[0] - (UNUSED_DAYS - 1) * 86400,) * 2)
    assert visitors.sweep() == 0  # looked for at most once an hour
    now[0] += 3601
    with caplog.at_level(logging.INFO):
        assert visitors.sweep() == 1
    assert not old.exists() and recent.exists()
    removed = next(r for r in caplog.records if r.message == "Visitor conversations removed")
    assert removed.__dict__["removed"] == 1
    # Asked for again, the removed one starts afresh; the kept one is the same.
    assert visitors.of("a" * 32) == old and len(made) == 3
    assert visitors.of("b" * 32) == recent and len(made) == 3
    assert sorted(visitors.open()) == sorted([old, recent])
    assert visitors.forget_all() == 1  # only the kept one has a file
    assert visitors.open() == []


def video_of(browser: TestClient, prompt: str) -> int:
    """Ask, have the reply's video made, and return the reply's turn."""
    turn = int(browser.post("/api/chat", json={"prompt": prompt}).json()["turn"])
    assert browser.post("/api/chat/video", json={"turn": turn}).json()["video"]
    return turn


def test_the_hosts_clear_leaves_each_visitors_reply_videos(tmp_path: Path) -> None:
    """Codex's review of PR #290: Clear conversation removed every reply video, so a visitor's
    still in their conversation answered 404."""
    app = site(tmp_path, FakeLlm2())
    app.state.reply_warm_up.join(5)
    host = the_host(app, tmp_path)
    photo = host.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)}).json()
    done = PrepareStatus("done", photo_id=photo["id"])
    with (
        patch.object(PrepareJob, "status", return_value=done),
        patch.object(UploadStore, "voice_sample", return_value=VoiceSample(2, 40, 35, None)),
    ):
        ann = TestClient(app)
        turn = video_of(ann, "I am Ann.")
        assert ann.get(f"/api/chat/videos/{turn}").content == b"Reply 1"
        assert host.delete("/api/chat").is_success
        assert ann.get(f"/api/chat/videos/{turn}").content == b"Reply 1"
        # The host's own reply videos still go with their conversation.
        mine = video_of(host, "I am the host.")
        assert host.get(f"/api/chat/videos/{mine}").is_success
        # The host's new video replaces their own old ones only, and one visitor's another's.
        assert ann.get(f"/api/chat/videos/{turn}").is_success
        bob = TestClient(app)
        video_of(bob, "I am Bob.")
        assert ann.get(f"/api/chat/videos/{turn}").is_success
        again = video_of(ann, "Me again.")
        assert ann.get(f"/api/chat/videos/{again}").is_success
        assert ann.get(f"/api/chat/videos/{turn}").status_code == 404
        assert host.delete("/api/chat").is_success
        assert host.get(f"/api/chat/videos/{mine}").status_code == 404
        # Delete my data takes every visitor's.
        assert any((tmp_path / "replies").glob("*.mp4"))
        assert host.delete("/api/data").is_success
        assert not any((tmp_path / "replies").glob("*.mp4"))


def test_a_clear_drops_only_its_own_videos_being_made(tmp_path: Path) -> None:
    videos = ReplyVideos(tmp_path, write_video, VoiceReady(lambda: None, lambda: "v"))
    visitors = VISITOR_VIDEOS_FROM + 1
    videos.render(Path("me.jpg"), visitors, "A visitor's reply")
    before = videos.generation
    assert videos.clear(lambda n: n < VISITOR_VIDEOS_FROM) == 0  # the host's: none of theirs
    assert videos.video(visitors) is not None
    # One being made for the host before the clear is dropped; a visitor's is published.
    assert videos.render(Path("me.jpg"), 3, "The host's", generation=before) is None
    assert videos.render(Path("me.jpg"), visitors + 1, "Another", generation=before)
    assert videos.clear() == 1  # every one, as for Delete my data
    assert videos.video(visitors + 1) is None
