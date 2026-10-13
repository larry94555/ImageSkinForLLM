import io
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_wiki_job import PDF, jobs, one_page_per_piece, settle, two_pages

from imageskin.app import create_app, wiki_file_name
from imageskin.content import Pdf
from imageskin.wiki_edits import EditError
from imageskin.wiki_history import (
    NOT_A_WIKI_FILE,
    HistoryError,
    WikiHistory,
    read_wiki_file,
    wiki_file,
)
from imageskin.wiki_job import WIKI_FORMAT, WikiJob

ENTRY = {"id": "a-rain", "title": "Rain.", "summary": "Rain.", "pages": [1], "detail": False}
WIKI: dict[str, Any] = {
    "format": WIKI_FORMAT,
    "name": "a.pdf",
    "version": "v1",
    "parts": 1,
    "skipped_parts": [],
    "pages": [{"id": "a-rain", "title": "Rain.", "text": "Rain.", "pages": [1]}],
    "outline": [{**ENTRY, "entries": [{**ENTRY, "id": "a-drops", "entries": []}]}],
}
EDIT = {"title": "Rain", "summary": "Rain falls.", "edited_at": "2026", "review": False}


def built(tmp_path: Path) -> tuple[Any, Any, WikiJob, Pdf]:
    store, readings, wiki = jobs(tmp_path)
    pdf = store.add("weather.pdf", io.BytesIO(PDF))
    readings.queue(pdf)
    settle(readings, wiki)
    return store, readings, wiki, pdf


def kinds(wiki: WikiJob, pdf_id: str) -> list[str]:
    return [v["change"]["kind"] for v in wiki.versions(pdf_id) or []]


def title(wiki: WikiJob, pdf_id: str) -> str:
    title: str = wiki.contents(pdf_id)[0]["entries"][0]["title"]
    return title


def test_versions_are_kept_newest_first_until_forgotten(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    history = WikiHistory(tmp_path, WIKI_FORMAT)
    assert not history.started("a") and history.versions("a") == []
    first = history.record("a", WIKI, {}, "built")
    second = history.record("a", WIKI, {"a-rain": EDIT}, "edited", title="Rain")
    assert history.started("a") and not history.started("b")
    assert [v["id"] for v in history.versions("a")] == [second["id"], first["id"]]
    assert history.versions("a")[0] == {
        "id": second["id"],
        "at": second["at"],
        "change": {"kind": "edited", "title": "Rain"},
    }
    assert WikiHistory(tmp_path, WIKI_FORMAT).get("a", first["id"]) == first  # after a restart
    assert history.get("a", "nope") is None
    assert history.everything("a") == [first, second]  # oldest first, with the wikis
    assert "Wiki version kept" in caplog.text

    other = {**first, "id": "from-a-file"}
    assert history.add("a", [first, other]) == 1  # only the one it didn't have
    assert len(history.versions("a")) == 3
    history.forget("a")
    assert history.versions("a") == [] and not (tmp_path / "a.history").exists()
    history.forget("a")  # nothing to forget


def test_unreadable_versions_are_left_out_and_unwritable_ones_refused(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    history = WikiHistory(tmp_path, WIKI_FORMAT)
    kept = history.record("a", WIKI, {}, "built")
    (tmp_path / "a.history" / "0-broken.json").write_text("{ broken")
    (tmp_path / "a.history" / "1-other.json").write_text('{"id": "x"}')
    assert history.versions("a") == [{"id": kept["id"], "at": kept["at"], "change": kept["change"]}]
    assert caplog.text.count("Could not read a wiki version") == 2

    (tmp_path / "b.history").write_text("a file where its folder goes")
    with pytest.raises(HistoryError, match="could not be saved") as refused:
        history.record("b", WIKI, {}, "built")
    assert refused.value.status == 500
    assert "Could not keep the wiki version" in caplog.text


def a_file(**changed: Any) -> bytes:
    current = {"wiki": WIKI, "edits": {}}
    version = {"id": "v", "at": "2026-01-01", "change": {"kind": "built"}, **current}
    return json.dumps({**wiki_file("a", "a.pdf", "v1", current, [version]), **changed}).encode()


@pytest.mark.parametrize(
    "data",
    [
        b"\xff\xfe",
        b"{ broken",
        b"[]",
        a_file(kind="something-else"),
        a_file(format=2),
        a_file(pdf_id=None),
        a_file(current={"wiki": {**WIKI, "format": 0}, "edits": {}}),
        a_file(current={"wiki": WIKI, "edits": []}),
        a_file(history=[{"id": "v"}]),
        a_file(history={}),
    ],
)
def test_a_file_that_isnt_a_wiki_file_is_refused(data: bytes) -> None:
    with pytest.raises(HistoryError, match="isn't a wiki file") as refused:
        read_wiki_file(data, WIKI_FORMAT)
    assert refused.value.status == 422 and str(refused.value) == NOT_A_WIKI_FILE


def test_a_wiki_file_is_read_back() -> None:
    loaded = read_wiki_file(a_file(), WIKI_FORMAT)
    assert loaded["pdf_name"] == "a.pdf" and len(loaded["history"]) == 1


def test_every_change_is_a_version_and_a_rebuild_can_be_undone(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    _, _, wiki, pdf = built(tmp_path)
    rain = f"{pdf.id}-p1"
    assert kinds(wiki, pdf.id) == ["built"]

    wiki.edit(rain, "Rain", "Rain falls from clouds.")
    wiki.rebuild(pdf.id)
    wiki.wait()
    wiki.reviewed(rain)
    wiki.undo_edit(rain)
    assert kinds(wiki, pdf.id) == ["undone", "kept", "rebuilt", "edited", "built"]
    assert wiki.versions(pdf.id)[0]["change"] == {"kind": "undone", "title": "Rain"}  # type: ignore[index]
    assert title(wiki, pdf.id) == "Rain."

    # Back to the wiki before the rebuild: the edit is back, not to be checked.
    before_rebuild = wiki.versions(pdf.id)[3]  # type: ignore[index]
    shown = wiki.version(pdf.id, before_rebuild["id"])
    assert shown is not None and shown["entries"][0]["title"] == "Rain"
    assert not shown["entries"][0]["review"] and shown["lost_edits"] == []
    wiki.restore(pdf.id, before_rebuild["id"])
    assert title(wiki, pdf.id) == "Rain" and not wiki.contents(pdf.id)[0]["entries"][0]["review"]
    restored = wiki.versions(pdf.id)[0]  # type: ignore[index]
    assert restored["change"] == {"kind": "restored", "restored_at": before_rebuild["at"]}
    assert "Wiki version restored" in caplog.text

    # A restore is a version too, so it can be undone the same way.
    wiki.restore(pdf.id, wiki.versions(pdf.id)[1]["id"])  # type: ignore[index]
    assert title(wiki, pdf.id) == "Rain."
    assert len(wiki.versions(pdf.id) or []) == 7

    with pytest.raises(HistoryError, match="No such version") as refused:
        wiki.restore(pdf.id, "nope")
    assert refused.value.status == 404
    assert wiki.version(pdf.id, "nope") is None and wiki.versions("f" * 32) is None

    wiki.forget(pdf.id)
    assert wiki.history.versions(pdf.id) == []  # removing the PDF removes its history


def test_a_wiki_built_before_its_history_began_is_kept_first(tmp_path: Path) -> None:
    _, _, wiki, pdf = built(tmp_path)
    wiki.history.forget(pdf.id)  # as it was before R38a
    assert kinds(wiki, pdf.id) == ["start"]
    wiki.history.forget(pdf.id)
    wiki.edit(f"{pdf.id}-p1", "Rain", "Rain falls.")
    assert kinds(wiki, pdf.id) == ["edited", "start"]


def test_a_discarded_lost_edit_is_its_own_kind(tmp_path: Path) -> None:
    _, _, wiki, pdf = built(tmp_path)
    path = tmp_path / "content" / "wiki" / f"{pdf.id}.edits.json"
    edit = {"title": "Hail", "summary": "Ice.", "edited_at": "2026", "review": True}
    path.write_text(json.dumps({"edits": {f"{pdf.id}-hail": edit}}))
    assert wiki.undo_edit(f"{pdf.id}-hail")
    assert wiki.versions(pdf.id)[0]["change"] == {"kind": "discarded", "title": "Hail"}  # type: ignore[index]


def test_a_version_cant_be_restored_while_the_wiki_is_being_built(tmp_path: Path) -> None:
    _, _, wiki, pdf = built(tmp_path)
    [version] = wiki.versions(pdf.id) or []
    wiki._waiting.append(pdf.id)  # queued, as a rebuild is before it starts
    with pytest.raises(HistoryError, match="being built") as refused:
        wiki.restore(pdf.id, version["id"])
    assert refused.value.status == 409
    with pytest.raises(HistoryError, match="being built"):
        wiki.load(pdf.id, json.dumps(wiki.export(pdf.id)).encode())


def test_a_version_of_a_replaced_pdf_is_restored_only_when_asked_again(tmp_path: Path) -> None:
    store, readings, wiki, pdf = built(tmp_path)
    wiki.edit(f"{pdf.id}-p1", "Rain", "Rain falls.")
    saved = json.dumps(wiki.export(pdf.id)).encode()
    old = wiki.versions(pdf.id)[0]  # type: ignore[index]
    new = store.replace(pdf.id, "weather2.pdf", io.BytesIO(b"%PDF-1.4" + PDF))
    wiki.reset(pdf.id)
    readings.queue(new)
    settle(readings, wiki)
    assert kinds(wiki, pdf.id) == ["rebuilt", "edited", "built"]  # the old pages kept first

    for change in (
        lambda f: wiki.restore(pdf.id, old["id"], f),
        lambda f: wiki.load(pdf.id, saved, f),
    ):
        with pytest.raises(HistoryError, match="earlier copy of the PDF") as refused:
            change(False)
        assert refused.value.status == 412
        change(True)
        assert title(wiki, pdf.id) == "Rain"
        assert wiki.built(pdf.id) is not None  # saved as the PDF's as it is now
        assert wiki.contents(pdf.id)[0]["pdf_name"] == "weather2.pdf"


def test_save_rebuild_and_load_brings_the_wiki_and_its_history_back(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    _, _, wiki, pdf = built(tmp_path)
    wiki.edit(f"{pdf.id}-p1", "Rain", "Rain falls.")
    saved = wiki.export(pdf.id)
    assert saved is not None and saved["pdf_name"] == "weather.pdf"
    assert saved["current"]["edits"][f"{pdf.id}-p1"]["title"] == "Rain"
    assert len(saved["history"]) == 2 and "Wiki saved to a file" in caplog.text
    assert wiki.export("f" * 32) is None

    # Removed and built again: no edits, a new history.
    wiki.forget(pdf.id)
    wiki.rebuild(pdf.id)
    wiki.wait()
    assert title(wiki, pdf.id) == "Rain." and kinds(wiki, pdf.id) == ["built"]

    assert wiki.load(pdf.id, json.dumps(saved).encode()) == 2
    assert title(wiki, pdf.id) == "Rain"
    assert kinds(wiki, pdf.id) == ["loaded", "built", "edited", "built"]
    assert "Wiki loaded from a file" in caplog.text
    assert wiki.load(pdf.id, json.dumps(saved).encode()) == 0  # the history has them all

    other = {**saved, "pdf_id": "f" * 32, "pdf_name": "other.pdf"}
    with pytest.raises(HistoryError, match=r"another PDF \(other.pdf\)") as refused:
        wiki.load(pdf.id, json.dumps(other).encode())
    assert refused.value.status == 422


def test_a_restore_that_cant_be_saved_keeps_the_wiki_as_it_was(tmp_path: Path) -> None:
    _, _, wiki, pdf = built(tmp_path)
    wiki.edit(f"{pdf.id}-p1", "Rain", "Rain falls.")
    first = wiki.versions(pdf.id)[1]  # type: ignore[index]
    (tmp_path / "content" / "wiki" / f"{pdf.id}.writing").mkdir()  # where it is written first
    with pytest.raises(HistoryError, match="could not be saved") as refused:
        wiki.restore(pdf.id, first["id"])
    assert refused.value.status == 500
    assert wiki.statuses()[pdf.id].state == "done" and title(wiki, pdf.id) == "Rain"


def test_a_change_is_made_even_when_its_version_cant_be_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, wiki, pdf = built(tmp_path)

    def fail(*args: Any, **kw: Any) -> None:
        raise HistoryError("The wiki's history could not be saved. Try again.", 500)

    monkeypatch.setattr(wiki.history, "record", fail)
    assert wiki.edit(f"{pdf.id}-p1", "Rain", "Rain falls.")["title"] == "Rain"


def test_a_restore_for_a_removed_pdf_is_refused(tmp_path: Path) -> None:
    store, _, wiki, pdf = built(tmp_path)
    [version] = wiki.versions(pdf.id) or []
    store.remove(pdf.id)
    with pytest.raises(HistoryError, match="No such PDF") as refused:
        wiki.restore(pdf.id, version["id"])
    assert refused.value.status == 404


def test_a_saved_wiki_file_is_named_after_its_pdf() -> None:
    assert wiki_file_name({"pdf_name": "Water cycle.pdf"}) == "Water cycle-wiki.json"
    assert wiki_file_name({"pdf_name": 'é"x\r\n.pdf'}) == "__x__-wiki.json"
    assert wiki_file_name({"pdf_name": ".pdf"}) == ".pdf-wiki.json"
    assert wiki_file_name({"pdf_name": ""}) == "wiki-wiki.json"


def test_the_history_api_restores_saves_and_loads(tmp_path: Path) -> None:
    app = create_app(tmp_path, read_pdf=two_pages, build_wiki=one_page_per_piece)
    client = TestClient(app)
    pdf = client.post("/api/content", files={"file": ("w.pdf", PDF, "application/pdf")}).json()
    settle(app.state.readings, app.state.wiki)
    api = f"/api/content/{pdf['id']}/wiki"
    entry = f"{pdf['id']}-p1"
    client.put(f"/api/wiki/{entry}", json={"title": "Rain", "summary": "Rain falls."})

    versions = client.get(f"{api}/history").json()
    assert [v["change"]["kind"] for v in versions] == ["edited", "built"]
    shown = client.get(f"{api}/history/{versions[1]['id']}").json()
    assert shown["entries"][0]["title"] == "Rain." and shown["pdf_name"] == "w.pdf"
    assert client.get(f"{api}/history/nope").status_code == 404
    assert client.get(f"/api/content/{'f' * 32}/wiki/history").status_code == 404

    restored = client.post(f"{api}/history/{versions[1]['id']}/restore")
    assert restored.json() == {"restored": True}
    assert client.get(f"/api/wiki/{entry}").json()["title"] == "Rain."
    assert client.post(f"{api}/history/nope/restore").status_code == 404

    download = client.get(f"{api}/file")
    assert download.headers["content-disposition"] == 'attachment; filename="w-wiki.json"'
    assert download.json()["kind"] == "imageskin-wiki"
    assert client.get(f"/api/content/{'f' * 32}/wiki/file").status_code == 404

    client.put(f"/api/wiki/{entry}", json={"title": "Drizzle", "summary": "Light rain."})
    loaded = client.post(f"{api}/file", files={"file": ("w-wiki.json", download.content)})
    assert loaded.json() == {"versions_added": 0}
    assert client.get(f"/api/wiki/{entry}").json()["title"] == "Rain."
    refused = client.post(f"{api}/file", files={"file": ("x.json", b"{}")})
    assert refused.status_code == 422 and "isn't a wiki file" in refused.json()["detail"]


def test_the_api_asks_first_for_a_replaced_pdf_and_refuses_a_big_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(tmp_path, read_pdf=two_pages, build_wiki=one_page_per_piece)
    client = TestClient(app)
    pdf = client.post("/api/content", files={"file": ("w.pdf", PDF, "application/pdf")}).json()
    settle(app.state.readings, app.state.wiki)
    api = f"/api/content/{pdf['id']}/wiki"
    saved = client.get(f"{api}/file").content
    [old] = client.get(f"{api}/history").json()
    client.put(
        f"/api/content/{pdf['id']}",
        files={"file": ("w2.pdf", b"%PDF-1.4" + PDF, "application/pdf")},
    )
    settle(app.state.readings, app.state.wiki)

    asked = client.post(f"{api}/history/{old['id']}/restore")
    assert asked.status_code == 412 and "earlier copy" in asked.json()["detail"]
    assert client.post(f"{api}/history/{old['id']}/restore?force=true").status_code == 200
    asked = client.post(f"{api}/file", files={"file": ("w-wiki.json", saved)})
    assert asked.status_code == 412
    forced = client.post(f"{api}/file?force=true", files={"file": ("w-wiki.json", saved)})
    assert forced.status_code == 200

    monkeypatch.setattr("imageskin.app.MAX_WIKI_FILE_BYTES", 10)
    big = client.post(f"{api}/file", files={"file": ("w-wiki.json", saved)})
    assert big.status_code == 413 and "at most" in big.json()["detail"]


@pytest.mark.parametrize(
    ("at", "version_id"),
    [
        ("../../../../escaped", "x"),
        ("2026-01-01", "../../../../escaped"),
        ("/tmp/escaped", "/tmp/escaped"),
        ("2026-01-01", "a/b\\c"),
    ],
)
def test_a_loaded_file_never_writes_outside_the_history(
    tmp_path: Path, at: str, version_id: str
) -> None:
    _, _, wiki, pdf = built(tmp_path)
    saved = wiki.export(pdf.id)
    assert saved is not None
    crafted = {**saved["history"][0], "id": version_id, "at": at}
    saved["history"].append(crafted)
    history = tmp_path / "content" / "wiki" / f"{pdf.id}.history"
    above = [tmp_path.parent, Path("/tmp")]  # where the crafted names lead
    assert not any(list(p.glob("*escaped*")) for p in above)

    assert wiki.load(pdf.id, json.dumps(saved).encode()) == 1
    assert not any(list(p.glob("*escaped*")) for p in above)
    written = list(history.rglob("*"))
    assert all(p.parent == history and re.fullmatch(r"[0-9a-f]{32}\.json", p.name) for p in written)
    assert wiki.history.get(pdf.id, version_id) == crafted  # kept, under a name of its own


def nested(**changed: Any) -> dict[str, Any]:
    return {**WIKI["outline"][0]["entries"][0], **changed}


@pytest.mark.parametrize(
    "wiki",
    [
        {**WIKI, "outline": [{}]},
        {**WIKI, "outline": [{**WIKI["outline"][0], "entries": [nested(summary=None)]}]},
        {**WIKI, "outline": [{**WIKI["outline"][0], "entries": [nested(entries=None)]}]},
        {**WIKI, "outline": [nested(detail="no")]},
        {**WIKI, "outline": [nested(pages=["1"])]},
        {**WIKI, "outline": [nested(pages=[True])]},
        {**WIKI, "pages": [{"id": "a-rain", "title": "Rain.", "pages": [1]}]},
        {**WIKI, "parts": None},
        {**WIKI, "name": None},
    ],
)
def test_a_file_with_a_broken_wiki_is_refused(wiki: dict[str, Any]) -> None:
    with pytest.raises(HistoryError, match="isn't a wiki file"):
        read_wiki_file(a_file(current={"wiki": wiki, "edits": {}}), WIKI_FORMAT)
    version = {"id": "v", "at": "2026", "change": {"kind": "built"}, "wiki": wiki, "edits": {}}
    with pytest.raises(HistoryError, match="isn't a wiki file"):
        read_wiki_file(a_file(history=[version]), WIKI_FORMAT)


@pytest.mark.parametrize(
    "edits",
    [
        {"a-rain": "Rain"},
        {"a-rain": {"title": "Rain", "summary": "Rain falls."}},
        {"a-rain": {**EDIT, "summary": None}},
        {"a-rain": {**EDIT, "review": "no"}},
    ],
)
def test_a_file_with_broken_edits_is_refused(edits: dict[str, Any]) -> None:
    with pytest.raises(HistoryError, match="isn't a wiki file"):
        read_wiki_file(a_file(current={"wiki": WIKI, "edits": edits}), WIKI_FORMAT)
    version = {"id": "v", "at": "2026", "change": {"kind": "built"}, "wiki": WIKI, "edits": edits}
    with pytest.raises(HistoryError, match="isn't a wiki file"):
        read_wiki_file(a_file(history=[version]), WIKI_FORMAT)


def wiki_files(tmp_path: Path) -> dict[str, str]:
    """Every file the wiki keeps, by name, with what it holds."""
    folder = tmp_path / "content" / "wiki"
    return {str(p.relative_to(folder)): p.read_text() for p in folder.rglob("*") if p.is_file()}


def test_a_broken_file_changes_nothing(tmp_path: Path) -> None:
    _, _, wiki, pdf = built(tmp_path)
    wiki.edit(f"{pdf.id}-p1", "Rain", "Rain falls.")
    saved = wiki.export(pdf.id)
    assert saved is not None
    saved["current"]["wiki"]["outline"] = [{}]
    before = wiki_files(tmp_path)
    with pytest.raises(HistoryError, match="isn't a wiki file") as refused:
        wiki.load(pdf.id, json.dumps(saved).encode())
    assert refused.value.status == 422 and wiki_files(tmp_path) == before


def fail_edits(*args: Any) -> None:
    raise EditError("The edit could not be saved. Try again.", status=500)


def test_a_restore_or_load_whose_edits_cant_be_saved_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, wiki, pdf = built(tmp_path)
    [first] = wiki.versions(pdf.id) or []
    wiki.edit(f"{pdf.id}-p1", "Rain", "Rain falls.")
    saved = wiki.export(pdf.id)
    wiki.rebuild(pdf.id)
    wiki.wait()
    wiki.undo_edit(f"{pdf.id}-p1")  # the built text, with no edits
    current = wiki.contents(pdf.id)
    files = wiki_files(tmp_path)

    monkeypatch.setattr(wiki.edits, "replace", fail_edits)
    for change in (
        lambda: wiki.restore(pdf.id, first["id"]),
        lambda: wiki.load(pdf.id, json.dumps(saved).encode()),
    ):
        with pytest.raises(HistoryError, match="nothing was changed") as refused:
            change()
        assert refused.value.status == 500
        assert wiki.contents(pdf.id) == current and wiki_files(tmp_path) == files
        assert wiki.statuses()[pdf.id].state == "done"


def test_a_load_with_no_wiki_before_it_leaves_none_when_it_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, wiki, pdf = built(tmp_path)
    saved = json.dumps(wiki.export(pdf.id)).encode()
    wiki.forget(pdf.id)
    monkeypatch.setattr(wiki.edits, "replace", fail_edits)
    with pytest.raises(HistoryError, match="nothing was changed"):
        wiki.load(pdf.id, saved)
    assert wiki.contents(pdf.id) == [] and pdf.id not in wiki.statuses()


def test_a_wiki_that_cant_be_put_back_is_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _, _, wiki, pdf = built(tmp_path)
    saved = wiki.export(pdf.id)
    assert saved is not None
    saved["current"]["wiki"]["parts"] = 2  # not the wiki as it is now
    save = wiki._save
    saves: list[bool] = []

    def once(wiki_saved: dict[str, Any]) -> bool:
        saves.append(not saves and save(wiki_saved))  # the loaded wiki, then not the one before
        return saves[-1]

    monkeypatch.setattr(wiki, "_save", once)
    monkeypatch.setattr(wiki.edits, "replace", fail_edits)
    with pytest.raises(HistoryError, match="nothing was changed"):
        wiki.load(pdf.id, json.dumps(saved).encode())
    assert saves == [True, False]
    assert "Could not put the wiki back after a failed change" in caplog.text


def test_a_load_whose_history_cant_all_be_kept_still_loads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, wiki, pdf = built(tmp_path)
    wiki.edit(f"{pdf.id}-p1", "Rain", "Rain falls.")
    saved = wiki.export(pdf.id)
    assert saved is not None
    wiki.forget(pdf.id)
    wiki.rebuild(pdf.id)
    wiki.wait()
    write = wiki.history._write
    imported = {v["id"] for v in saved["history"]}

    def not_imported(pdf_id: str, version: dict[str, Any]) -> None:
        if version["id"] in imported:
            raise HistoryError("The wiki's history could not be saved. Try again.", 500)
        write(pdf_id, version)

    monkeypatch.setattr(wiki.history, "_write", not_imported)
    assert wiki.load(pdf.id, json.dumps(saved).encode()) == 0  # the change is made all the same
    assert title(wiki, pdf.id) == "Rain" and kinds(wiki, pdf.id) == ["loaded", "built"]


def test_a_saved_file_is_one_moment_of_the_wiki(tmp_path: Path) -> None:
    """A change made while the file is being saved waits for it, so the file's current wiki is
    its history's newest version."""
    _, _, wiki, pdf = built(tmp_path)
    everything = wiki.history.everything
    late: list[threading.Thread] = []
    edited = threading.Event()

    def late_edit() -> None:
        wiki.edit(f"{pdf.id}-p1", "Rain", "Rain falls.")
        edited.set()

    def with_an_edit_meanwhile(pdf_id: str) -> list[dict[str, Any]]:
        thread = threading.Thread(target=late_edit)
        thread.start()
        late.append(thread)
        edited.wait(0.5)  # it waits for the file, so it isn't done
        return everything(pdf_id)

    wiki.history.everything = with_an_edit_meanwhile  # type: ignore[method-assign]
    saved = wiki.export(pdf.id)
    late[0].join(5)
    assert saved is not None and edited.is_set()
    assert saved["current"]["edits"] == saved["history"][-1]["edits"] == {}
    assert saved["current"]["wiki"] == saved["history"][-1]["wiki"]
    assert kinds(wiki, pdf.id) == ["edited", "built"]  # made after
