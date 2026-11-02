"""Each existing host's files move to their own site (roadmap R61e)."""

import io
import json
import logging
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_site_addresses import PASSWORD, served, sign_in

from imageskin import admin
from imageskin.host_disk import Owners, count
from imageskin.hosts import HostAccounts
from imageskin.photoreal_library import library_key
from imageskin.site_moves import SHARED_FILES, move_hosts_to_sites, site_name
from imageskin.sites import SiteDirectory

pytestmark = pytest.mark.real_hosts

ANN, BOB, CY = "ann@example.com", "bob@example.com", "cy@example.com"


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = admin.Secret("hash", admin.hash_password("nobody's password"))
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


def stored(home: Path, kind: str, item: str, data: bytes, suffix: str) -> Path:
    folder = home / "uploads" / kind
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{item}{suffix}"
    path.write_bytes(data)
    (folder / f"{item}.json").write_text(json.dumps({"id": item}))
    return path


def existing(home: Path, ann_recorded: bool = True) -> dict[str, Any]:
    """Three hosts in signing-up order, sharing the one site as before R61: Ann's and Bob's
    photos and recordings (Ann's only when `ann_recorded`), a photo from before host accounts,
    Bob's photo chosen and prepared, and the settings every host shared."""
    times = iter([100.0, 200.0, 300.0])
    hosts = HostAccounts(home, clock=lambda: next(times, 400.0))
    for email in (ANN, BOB, CY):
        hosts.sign_up(email, PASSWORD, "test")
    ids = {name: name[0] * 32 for name in ("ann-photo", "bob-photo", "old-photo")}
    ids |= {"ann-sound": "c" * 32, "bob-sound": "d" * 32}
    stored(home, "photos", ids["ann-photo"], b"ann's face", ".jpg")
    bob_photo = stored(home, "photos", ids["bob-photo"], b"bob's face", ".jpg")
    stored(home, "photos", ids["old-photo"], b"an old face", ".jpg")
    if ann_recorded:
        stored(home, "sounds", ids["ann-sound"], b"ann speaking", ".wav")
    stored(home, "sounds", ids["bob-sound"], b"bob speaking", ".wav")
    owners = Owners(home)
    for key, email in (("ann", ANN), ("bob", BOB)):
        owners.record("photos", ids[f"{key}-photo"], email)
        if key == "bob" or ann_recorded:
            owners.record("sounds", ids[f"{key}-sound"], email)
    face = home / "photoreal" / library_key(bob_photo)
    face.mkdir(parents=True)
    (face / "library.json").write_text("{}")
    (home / "uploads" / "chosen-photo.json").write_text(json.dumps({"id": ids["bob-photo"]}))
    (home / "uploads" / "voice-sample.wav").write_bytes(b"ann and bob speaking")
    (home / "uploads" / "voice-sample.wav.accent.npz").write_bytes(b"the accent learned")
    (home / "prepare.json").write_text('{"state": "done"}')
    (home / "clips").mkdir()
    (home / "clips" / "sample.mp4").write_bytes(b"video")
    for name in SHARED_FILES[:2]:
        (home / name).write_text(f'{{"from": "{name}"}}')
    (home / "conversation.json").write_text('{"turns": []}')
    return {"hosts": hosts, "sites": SiteDirectory(home, hosts), "ids": ids}


def test_every_host_gets_a_site_with_what_they_added(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    made = existing(tmp_path)
    ids = made["ids"]
    with caplog.at_level(logging.INFO):
        moved = move_hosts_to_sites(tmp_path, made["hosts"], made["sites"])
    # Every host, the first too, so no host's site is at the main address (Larry, PR #275).
    assert [(m.site, m.host) for m in moved] == [("ann", ANN), ("bob", BOB), ("cy", CY)]
    assert made["sites"].names() == ["ann", "bob", "cy"]
    assert made["hosts"].site_of(ANN) == "ann" and made["hosts"].site_of(BOB) == "bob"
    bob = tmp_path / "sites" / "bob"
    # Bob's photo and recording, his photo's prepared face, and the chosen photo. What was
    # prepared from it had Ann's recording in its voice, so it was dropped (Codex, PR #275).
    assert sorted(p.name for p in (bob / "uploads" / "photos").iterdir()) == [
        f"{ids['bob-photo']}.jpg",
        f"{ids['bob-photo']}.json",
    ]
    assert (bob / "uploads" / "sounds" / f"{ids['bob-sound']}.wav").is_file()
    assert (
        (bob / "photoreal").is_dir()
        and not (tmp_path / "photoreal").exists()
        or not any((tmp_path / "photoreal").iterdir())
    )
    assert json.loads((bob / "uploads" / "chosen-photo.json").read_text())["id"] == ids["bob-photo"]
    assert not (bob / "prepare.json").exists() and not (bob / "clips").exists()
    assert not (tmp_path / "clips").exists()
    assert "Prepared voice dropped: other hosts' recordings were in it" in caplog.messages
    # The first host's site has her photo, the old one no host added, and the conversation.
    ann = tmp_path / "sites" / "ann"
    ann_photos = sorted(p.stem for p in (ann / "uploads" / "photos").glob("*.jpg"))
    assert ann_photos == sorted([ids["ann-photo"], ids["old-photo"]])
    assert (ann / "conversation.json").is_file()
    # The main address's site holds no host's person now.
    assert not list((tmp_path / "uploads" / "photos").glob("*"))
    assert not list((tmp_path / "uploads" / "sounds").glob("*"))
    assert not (tmp_path / "uploads" / "chosen-photo.json").exists()
    assert not (tmp_path / "prepare.json").exists()
    assert not (tmp_path / "conversation.json").exists()
    assert not (tmp_path / "uploads" / "voice-sample.wav").exists()  # joined again in each site
    assert not (tmp_path / "uploads" / "voice-sample.wav.accent.npz").exists()
    # Each site's record of who added what, and so each host's Resources total; the old photo
    # counts for no host, as R192 counts it.
    assert count(ann, Owners(ann), ANN)["total"] == len(b"ann's faceann speaking")
    assert count(bob, Owners(bob), BOB)["total"] == len(b"bob's facebob speaking")
    assert count(tmp_path, Owners(tmp_path), ANN)["total"] == 0
    # The settings every host shared are copied to each new site.
    for site in ("ann", "bob", "cy"):
        for name in SHARED_FILES[:2]:
            assert (tmp_path / "sites" / site / name).read_text() == (tmp_path / name).read_text()
    logged = {r.__dict__["site"]: r.__dict__ for r in caplog.records if r.message == "Site moved"}
    assert logged["bob"]["host"] == BOB and logged["bob"]["files"] == 6
    assert logged["cy"]["files"] == 0 and logged["cy"]["shared_copied"] == 2
    assert logged["ann"]["files"] == 7  # 2 photos, 1 recording, their info, the conversation


def test_whats_prepared_moves_with_the_chosen_photo_when_its_voice_is_the_hosts_own(
    tmp_path: Path,
) -> None:
    made = existing(tmp_path, ann_recorded=False)
    move_hosts_to_sites(tmp_path, made["hosts"], made["sites"])
    bob = tmp_path / "sites" / "bob"
    assert json.loads((bob / "prepare.json").read_text()) == {"state": "done"}
    assert (bob / "clips" / "sample.mp4").read_bytes() == b"video"


def test_the_move_is_done_once_and_carries_on_after_a_start_cut_short(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    made = existing(tmp_path)
    move_hosts_to_sites(tmp_path, made["hosts"], made["sites"])
    caplog.clear()
    with caplog.at_level(logging.INFO):
        assert move_hosts_to_sites(tmp_path, made["hosts"], made["sites"]) == []
    assert "Site moved" not in caplog.messages
    # A file of Bob's left behind, as by a start cut short, moves at the next start.
    ids = made["ids"]
    stored(tmp_path, "sounds", "e" * 32, b"more of bob", ".wav")
    Owners(tmp_path).record("sounds", "e" * 32, BOB)
    (tmp_path / "sites" / "bob" / "llm.json").write_text('{"his": "own"}')
    moved = move_hosts_to_sites(tmp_path, made["hosts"], made["sites"])
    assert [(m.site, m.files) for m in moved] == [("bob", 2)]
    assert (tmp_path / "sites" / "bob" / "uploads" / "sounds" / f"{'e' * 32}.wav").is_file()
    assert (tmp_path / "sites" / "bob" / "llm.json").read_text() == '{"his": "own"}'  # kept
    assert ids  # the other files stayed as they were moved


def test_a_file_already_in_the_site_is_left_where_it_was_and_keeps_its_host(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    made = existing(tmp_path)
    bob_sound = made["ids"]["bob-sound"]
    target = tmp_path / "sites" / "bob" / "uploads" / "sounds" / f"{bob_sound}.wav"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"already there")
    with caplog.at_level(logging.WARNING):
        move_hosts_to_sites(tmp_path, made["hosts"], made["sites"])
        move_hosts_to_sites(tmp_path, made["hosts"], made["sites"])  # and a second start
    assert target.read_bytes() == b"already there"
    assert "Already in the site; left where it was" in caplog.text
    assert "Host's files left at the main address" in caplog.messages
    # The recording left behind is still Bob's, where it is: never taken for one no host added
    # and moved to the first host's site (Codex's review of PR #275).
    left = tmp_path / "uploads" / "sounds" / f"{bob_sound}.wav"
    assert left.read_bytes() == b"bob speaking"
    assert Owners(tmp_path).read().get("sounds", {}).get(bob_sound) == BOB
    assert not (tmp_path / "sites" / "ann" / "uploads" / "sounds" / left.name).exists()
    assert Owners(tmp_path / "sites" / "ann").read().get("sounds", {}).get(bob_sound) is None
    # Bob's photo, fully moved, is recorded in his site only.
    bob_photo = made["ids"]["bob-photo"]
    assert Owners(tmp_path / "sites" / "bob").read().get("photos", {}).get(bob_photo) == BOB
    assert Owners(tmp_path).read().get("photos", {}).get(bob_photo) is None


def test_a_move_cut_short_after_a_file_was_copied_finishes(tmp_path: Path) -> None:
    made = existing(tmp_path)
    bob_sound = made["ids"]["bob-sound"]
    target = tmp_path / "sites" / "bob" / "uploads" / "sounds" / f"{bob_sound}.wav"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"bob speaking")  # the same file, there already
    move_hosts_to_sites(tmp_path, made["hosts"], made["sites"])
    assert not (tmp_path / "uploads" / "sounds" / target.name).exists()
    assert Owners(tmp_path / "sites" / "bob").read().get("sounds", {}).get(bob_sound) == BOB
    assert Owners(tmp_path).read().get("sounds", {}).get(bob_sound) is None


def test_nothing_moves_while_a_record_cant_be_read(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    made = existing(tmp_path)
    (tmp_path / "owners.json").write_text("{broken")
    with caplog.at_level(logging.ERROR):
        assert move_hosts_to_sites(tmp_path, made["hosts"], made["sites"]) == []
    assert "the prepared voice can't be checked" in caplog.text
    assert made["sites"].names() == []  # made once it can be read
    assert (tmp_path / "uploads" / "photos" / f"{made['ids']['bob-photo']}.jpg").is_file()

    (tmp_path / "hosts.json").write_text("{broken")
    with caplog.at_level(logging.ERROR):
        assert move_hosts_to_sites(tmp_path, made["hosts"], made["sites"]) == []
    assert "Hosts not moved to their sites" in caplog.text


def test_a_host_already_given_a_site_keeps_it_and_their_files_follow(tmp_path: Path) -> None:
    made = existing(tmp_path)
    made["sites"].add("bobs-place", BOB)
    moved = move_hosts_to_sites(tmp_path, made["hosts"], made["sites"])
    assert [m.site for m in moved] == ["ann", "bobs-place", "cy"]
    assert (tmp_path / "sites" / "bobs-place" / "uploads" / "chosen-photo.json").is_file()


def test_a_sites_name_comes_from_the_email_and_is_unique() -> None:
    assert site_name("Ann.Lee@example.com", set()) == "ann-lee"
    assert site_name("ann@example.com", {"ann", "ann-2"}) == "ann-3"
    assert site_name("www@example.com", set()) == "www-2"
    assert site_name("...@example.com", set()) == "site"


def test_a_moved_host_is_told_where_their_site_is(tmp_path: Path) -> None:
    sites, made, _ = served(tmp_path)
    main = TestClient(sites, base_url="http://www.localhost:8000")
    told = main.post("/api/host/sign-in", json={"email": ANN, "password": PASSWORD})
    assert told.status_code == 401
    assert told.json() == {
        "detail": "Your site is at a.localhost:8000. Sign in there.",
        "site": "a",
    }
    a = TestClient(sites, base_url="http://a.localhost:8000")
    assert sign_in(a, ANN) == 200
    assert a.post("/api/content", files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4\n"))})


def a_pdf(home: Path, pdf_id: str, data: bytes, owner: str | None) -> None:
    """A PDF with all made from it: its info, what was read, its wiki pages, edits and
    history."""
    content = home / "content"
    for folder in ("pdfs", "read", "wiki"):
        (content / folder).mkdir(parents=True, exist_ok=True)
    (content / "pdfs" / f"{pdf_id}.pdf").write_bytes(data)
    (content / "pdfs" / f"{pdf_id}.json").write_text(json.dumps({"id": pdf_id}))
    (content / "read" / f"{pdf_id}.json").write_text('{"pieces": []}')
    (content / "wiki" / f"{pdf_id}.json").write_text('{"outline": []}')
    (content / "wiki" / f"{pdf_id}.edits.json").write_text("{}")
    history = content / "wiki" / f"{pdf_id}.history"
    history.mkdir()
    (history / "v1.json").write_text("{}")
    if owner is not None:
        Owners(home).record("pdfs", pdf_id, owner)


PDF_FILES = 6  # the PDF, its info, what was read, its wiki pages, edits and one version


def test_each_hosts_pdfs_move_to_their_site_with_all_made_from_them(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    made = existing(tmp_path)
    ann_pdf, bob_pdf, old_pdf = "1" * 32, "2" * 32, "3" * 32
    a_pdf(tmp_path, ann_pdf, b"%PDF-ann", ANN)
    a_pdf(tmp_path, bob_pdf, b"%PDF-bob's", BOB)
    a_pdf(tmp_path, old_pdf, b"%PDF-old", None)
    (tmp_path / "content" / "wiki" / "lessons.json").write_text('{"lessons": {}}')
    with caplog.at_level(logging.INFO):
        move_hosts_to_sites(tmp_path, made["hosts"], made["sites"])

    def pdfs(site: Path) -> list[str]:
        return sorted(p.stem for p in (site / "content" / "pdfs").glob("*.pdf"))

    ann, bob = tmp_path / "sites" / "ann", tmp_path / "sites" / "bob"
    # The first host also gets the PDF no host added, as with the photos (R61e).
    assert pdfs(ann) == [ann_pdf, old_pdf] and pdfs(bob) == [bob_pdf]
    for site, pdf_id in ((ann, ann_pdf), (bob, bob_pdf)):
        assert (site / "content" / "read" / f"{pdf_id}.json").is_file()
        assert (site / "content" / "wiki" / f"{pdf_id}.json").is_file()
        assert (site / "content" / "wiki" / f"{pdf_id}.edits.json").is_file()
        assert (site / "content" / "wiki" / f"{pdf_id}.history" / "v1.json").is_file()
    assert not list((tmp_path / "content").rglob("*.json"))  # nothing left, lessons too
    # Each host's Resources total counts their own files, PDFs too.
    assert count(bob, Owners(bob), BOB)["total"] == len(b"bob's facebob speaking%PDF-bob's")
    assert count(ann, Owners(ann), ANN)["pdfs"] == len(b"%PDF-ann")
    assert Owners(tmp_path).read().get("pdfs") == {}
    logged = {
        r.__dict__["host"]: r.__dict__ for r in caplog.records if r.message == "Site PDFs moved"
    }
    assert logged[ANN]["pdfs"] == 2 and logged[ANN]["files"] == 2 * PDF_FILES
    assert logged[BOB]["pdfs"] == 1 and logged[BOB]["site"] == "bob"
    assert CY not in logged
    # A second start moves nothing.
    caplog.clear()
    with caplog.at_level(logging.INFO):
        assert move_hosts_to_sites(tmp_path, made["hosts"], made["sites"]) == []
    assert "Site PDFs moved" not in caplog.messages


def test_a_pdf_left_behind_keeps_its_host(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    made = existing(tmp_path)
    bob_pdf = "2" * 32
    a_pdf(tmp_path, bob_pdf, b"%PDF-bob's", BOB)
    clash = tmp_path / "sites" / "bob" / "content" / "read" / f"{bob_pdf}.json"
    clash.parent.mkdir(parents=True)
    clash.write_text('{"pieces": ["another reading"]}')
    with caplog.at_level(logging.WARNING):
        move_hosts_to_sites(tmp_path, made["hosts"], made["sites"])
        move_hosts_to_sites(tmp_path, made["hosts"], made["sites"])
    assert "Host's PDFs left at the main address" in caplog.messages
    assert (tmp_path / "content" / "read" / clash.name).is_file()
    assert Owners(tmp_path).read()["pdfs"] == {bob_pdf: BOB}  # never taken for no host's
    assert not (tmp_path / "sites" / "ann" / "content" / "pdfs").exists()
    # Once the clash is gone, the next start finishes the move.
    clash.unlink()
    move_hosts_to_sites(tmp_path, made["hosts"], made["sites"])
    assert Owners(tmp_path / "sites" / "bob").read()["pdfs"] == {bob_pdf: BOB}
    assert Owners(tmp_path).read()["pdfs"] == {}
