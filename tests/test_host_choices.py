"""One host's Allow and Deny of a custom image and sound, over Admin settings' defaults (R242)."""

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from imageskin import admin
from imageskin.app import create_app
from imageskin.hosts import FILENAME, HostAccounts
from imageskin.uploads import PhotoResult, Upload, UploadStore, VoiceSample

# These tests sign up hosts for themselves, and keep Admin settings' real defaults (both off).
pytestmark = [pytest.mark.real_hosts, pytest.mark.custom_defaults]

PASSWORD = "a long secret"
ANN, BOB = "ann@example.com", "bob@example.com"
JPG = b"\xff\xd8\xff\xe0" + b"\0" * 100
RECORDINGS = VoiceSample(2, 40, 35, None)  # recordings that passed: the own voice is used


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = admin.Secret("hash", admin.hash_password("nobody's password"))
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


def test_choices_are_kept_with_the_host(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    accounts = HostAccounts(tmp_path)
    accounts.sign_up(ANN, PASSWORD, "127.0.0.1")
    assert accounts.choices(ANN) == (None, None)
    with caplog.at_level(logging.INFO):
        assert accounts.set_choices("ANN@example.com", {"custom_image": "allow"}) == ("allow", None)
    record = next(r for r in caplog.records if r.message == "Host properties changed")
    assert record.__dict__["email"] == ANN
    assert record.__dict__["custom_image_change"] == [None, "allow"]
    assert record.__dict__["custom_voice_change"] == [None, None]

    assert accounts.set_choices(ANN, {"custom_voice": "deny"}) == ("allow", "deny")
    assert HostAccounts(tmp_path).choices(ANN) == ("allow", "deny")  # read from hosts.json
    assert accounts.set_choices(ANN, {"custom_image": None}) == (None, "deny")  # the default
    stored = json.loads((tmp_path / FILENAME).read_text())["hosts"][ANN]
    assert "custom_image" not in stored and stored["custom_voice"] == "deny"

    assert accounts.set_choices(BOB, {"custom_image": "allow"}) is None  # no such host
    assert accounts.choices(BOB) == (None, None)


def test_a_hand_edited_choice_that_isnt_one_is_the_default(tmp_path: Path) -> None:
    accounts = HostAccounts(tmp_path)
    accounts.sign_up(ANN, PASSWORD, "127.0.0.1")
    data = json.loads((tmp_path / FILENAME).read_text())
    data["hosts"][ANN]["custom_image"] = "yes"
    (tmp_path / FILENAME).write_text(json.dumps(data))
    assert HostAccounts(tmp_path).choices(ANN) == (None, None)
    (tmp_path / FILENAME).write_text("not json")
    assert HostAccounts(tmp_path).choices(ANN) == (None, None)


def site(tmp_path: Path) -> tuple[TestClient, TestClient, TestClient]:
    """The administrator, Ann and Bob, each in their own browser."""
    (tmp_path / "admin.toml").write_text('password = "secret"\n')
    app = create_app(tmp_path, check_photo=lambda photo: PhotoResult([], 80))
    ann, bob, administrator = TestClient(app), TestClient(app), TestClient(app)
    for client, email in ((ann, ANN), (bob, BOB)):
        client.post("/api/host/sign-up", json={"email": email, "password": PASSWORD})
        client.post("/api/consent", json={"agreed": True})
    # The admin sign-in is only for a signed-in host or a listed laptop (R191).
    administrator.post("/api/host/sign-in", json={"email": BOB, "password": PASSWORD})
    administrator.post("/api/admin/sign-in", json={"password": "secret"})
    return administrator, ann, bob


def test_allow_custom_image_for_one_host(tmp_path: Path) -> None:
    administrator, ann, bob = site(tmp_path)
    shown = administrator.get("/api/admin/hosts/properties", params={"email": ANN}).json()
    assert shown == {
        "email": ANN,
        "custom_image": None,
        "custom_voice": None,
        "default": {"custom_image": "disabled", "custom_voice": "disabled"},
    }
    allowed = administrator.put(
        "/api/admin/hosts/properties", json={"email": ANN, "custom_image": "allow"}
    )
    assert allowed.status_code == 200 and allowed.json()["custom_image"] == "allow"
    # At once, with no sign-out: Ann may add a photo, Bob still can't.
    assert ann.get("/api/host/me").json()["custom_image"] is True
    assert ann.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)}).status_code == 200
    assert bob.get("/api/host/me").json()["custom_image"] is False
    assert bob.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)}).status_code == 403
    # The site's own person is Ann's photo, so her rule is the one it follows.
    may_use = administrator.app.state.may_use  # type: ignore[attr-defined]
    assert may_use(None).image is True

    # Back to the default: Ann can't either.
    administrator.put("/api/admin/hosts/properties", json={"email": ANN, "custom_image": None})
    assert ann.get("/api/host/me").json()["custom_image"] is False
    assert may_use(None).image is False


def test_deny_custom_sound_for_one_host(tmp_path: Path) -> None:
    administrator, ann, bob = site(tmp_path)
    administrator.put("/api/admin/settings", json={"disable_custom_voice": False})
    shown = administrator.put(
        "/api/admin/hosts/properties", json={"email": ANN, "custom_voice": "deny"}
    ).json()
    assert shown["custom_voice"] == "deny" and shown["default"]["custom_voice"] == "enabled"
    assert ann.get("/api/host/me").json()["custom_voice"] is False
    assert bob.get("/api/host/me").json()["custom_voice"] is True
    # The image choice wasn't sent, so it is left as it was.
    assert shown["custom_image"] is None


def test_only_the_administrator_and_only_a_host(tmp_path: Path) -> None:
    administrator, ann, _ = site(tmp_path)
    assert ann.get("/api/admin/hosts/properties", params={"email": ANN}).status_code == 401
    assert (
        ann.put("/api/admin/hosts/properties", json={"email": ANN, "custom_image": "allow"})
    ).status_code == 401
    missing = administrator.get("/api/admin/hosts/properties", params={"email": "zed@x.org"})
    assert missing.status_code == 404
    assert (
        administrator.put("/api/admin/hosts/properties", json={"email": "zed@x.org"})
    ).status_code == 404
    wrong = administrator.put(
        "/api/admin/hosts/properties", json={"email": ANN, "custom_image": "maybe"}
    )
    assert wrong.status_code == 422


def test_an_unreadable_hosts_file_is_503(tmp_path: Path) -> None:
    administrator, _, _ = site(tmp_path)
    (tmp_path / FILENAME).write_text("not json")
    assert (
        administrator.get("/api/admin/hosts/properties", params={"email": ANN})
    ).status_code == 503
    assert (
        administrator.put("/api/admin/hosts/properties", json={"email": ANN})
    ).status_code == 503


def recordings(*ids: str, rejected: tuple[str, ...] = ()):  # type: ignore[no-untyped-def]
    """The store's recordings, as if they had been added and checked."""
    sounds = [Upload(i, "sounds", f"{i}.wav", "wav", 10, "2026-01-01", 5.0, [], 1) for i in ids] + [
        Upload(i, "sounds", f"{i}.wav", "wav", 10, "2026-01-01", 5.0, ["too short"], 1)
        for i in rejected
    ]
    real = UploadStore.list
    return patch.object(
        UploadStore, "list", lambda self, kind: sounds if kind == "sounds" else real(self, kind)
    )


def test_the_site_voice_follows_the_host_who_added_the_recordings(tmp_path: Path) -> None:
    administrator, _, _ = site(tmp_path)
    administrator.put("/api/admin/hosts/properties", json={"email": ANN, "custom_voice": "allow"})
    may_use = administrator.app.state.may_use  # type: ignore[attr-defined]
    owners = tmp_path / "owners.json"
    a, b = "a" * 32, "b" * 32
    # No photo: the one host who added the recordings.
    owners.write_text(json.dumps({"sounds": {a: ANN, b: ANN}}))
    with recordings(a, b):
        assert may_use(None).voice is True
    # Two hosts' recordings: not known, so Admin settings' checkbox.
    owners.write_text(json.dumps({"sounds": {a: ANN, b: BOB}}))
    with recordings(a, b):
        assert may_use(None).voice is False
        owners.write_text("not json")
        assert may_use(None).voice is False
    # Only the recordings that passed make the voice: Bob's rejected one doesn't count.
    owners.write_text(json.dumps({"sounds": {a: ANN, b: BOB}}))
    with recordings(a, rejected=(b,)):
        assert may_use(None).voice is True
    # A recording with no record of who added it (from before R192): not known.
    owners.write_text(json.dumps({"sounds": {a: ANN}}))
    with recordings(a, b):
        assert may_use(None).voice is False


def test_the_site_photo_and_voice_follow_their_own_hosts(tmp_path: Path) -> None:
    """Codex's review of PR #268: the photo and the recordings can be different hosts'. The
    photo follows the rule of whoever added it, and the voice whoever added the recordings."""
    administrator, ann, _ = site(tmp_path)
    administrator.put(
        "/api/admin/hosts/properties",
        json={"email": ANN, "custom_image": "allow", "custom_voice": "allow"},
    )
    administrator.put("/api/admin/hosts/properties", json={"email": BOB, "custom_voice": "deny"})
    administrator.put("/api/admin/settings", json={"disable_custom_voice": False})
    photo = ann.post("/api/uploads/photos", files={"file": ("me.jpg", JPG)}).json()["id"]
    sound = "c" * 32
    (tmp_path / "owners.json").write_text(
        json.dumps({"photos": {photo: ANN}, "sounds": {sound: BOB}})
    )
    may_use = administrator.app.state.may_use  # type: ignore[attr-defined]
    with recordings(sound), patch.object(UploadStore, "voice_sample", return_value=RECORDINGS):
        assert may_use(None).image is True  # Ann's photo, Ann's Allow
        assert may_use(None).voice is False  # Bob's recordings, Bob's Deny
        # Prepare and the replies speak in the ready-made voice, not Bob's.
        assert ann.get("/api/ready-voice").json()["in_use"] is True

        # The other way round: Ann denies her voice, Bob is allowed his, the checkbox is off.
        administrator.put("/api/admin/settings", json={"disable_custom_voice": True})
        administrator.put(
            "/api/admin/hosts/properties", json={"email": ANN, "custom_voice": "deny"}
        )
        administrator.put(
            "/api/admin/hosts/properties", json={"email": BOB, "custom_voice": "allow"}
        )
        assert may_use(None).voice is True
        assert ann.get("/api/ready-voice").json()["in_use"] is False  # Bob's recordings
