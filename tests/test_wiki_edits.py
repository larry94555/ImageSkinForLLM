import io
import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_wiki_job import PDF, jobs, one_page_per_piece, settle, two_pages

from imageskin.app import create_app
from imageskin.content import ContentStore
from imageskin.pdf_reading import Progress, Reading
from imageskin.reading_job import ReadingJob
from imageskin.wiki import Progress as WikiProgress
from imageskin.wiki import Wiki, WikiPage
from imageskin.wiki_edits import MAX_SUMMARY_CHARS, MAX_TITLE_CHARS, EditError, WikiEdits, lost
from imageskin.wiki_job import WikiJob


def test_edits_are_kept_by_entry_until_undone(tmp_path: Path) -> None:
    edits = WikiEdits(tmp_path)
    assert edits.get("a") == {}
    saved = edits.save("a", "a-rain", "  Rain   and drizzle ", " Rain falls.\n")
    assert saved["title"] == "Rain and drizzle" and saved["summary"] == "Rain falls."
    assert not saved["review"] and saved["edited_at"]
    assert WikiEdits(tmp_path).get("a") == {"a-rain": saved}  # read back, as after a restart
    assert edits.get("b") == {}  # each PDF has its own

    assert edits.flag_all("a") == 1 and edits.get("a")["a-rain"]["review"]
    assert edits.reviewed("a", "a-rain") and not edits.get("a")["a-rain"]["review"]
    assert not edits.reviewed("a", "a-snow") and edits.flag_all("b") == 0

    assert edits.discard("a", "a-rain") and not edits.discard("a", "a-rain")
    assert not (tmp_path / "a.edits.json").exists()  # nothing left to keep
    edits.save("a", "a-rain", "Rain", "Rain falls.")
    edits.forget("a")
    assert edits.get("a") == {}


@pytest.mark.parametrize(
    ("title", "summary", "reason"),
    [
        ("", "Rain falls.", "needs a title and a summary"),
        ("Rain", "   ", "needs a title and a summary"),
        ("x" * (MAX_TITLE_CHARS + 1), "Rain falls.", "title can be at most"),
        ("Rain", "x" * (MAX_SUMMARY_CHARS + 1), "summary can be at most"),
    ],
)
def test_an_edit_needs_a_title_and_a_summary_of_a_sensible_length(
    tmp_path: Path, title: str, summary: str, reason: str
) -> None:
    with pytest.raises(EditError, match=reason) as refused:
        WikiEdits(tmp_path).save("a", "a-rain", title, summary)
    assert refused.value.status == 422


def test_unreadable_or_unwritable_edits_are_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "a.edits.json").write_text("{ broken")
    (tmp_path / "b.edits.json").write_text("[]")
    edits = WikiEdits(tmp_path)
    assert edits.get("a") == {} and edits.get("b") == {}
    assert "Could not read the wiki edits" in caplog.text

    blocked = WikiEdits(tmp_path / "blocked")
    (tmp_path / "blocked" / "a.edits.writing").mkdir(parents=True)  # where it is written first
    with pytest.raises(EditError, match="could not be saved") as refused:
        blocked.save("a", "a-rain", "Rain", "Rain falls.")
    assert refused.value.status == 500
    assert "Could not save the wiki edits" in caplog.text


@pytest.mark.parametrize("stored", ["{ broken", "[]", '{"edits": []}'])
def test_a_change_never_replaces_edits_it_could_not_read(tmp_path: Path, stored: str) -> None:
    path = tmp_path / "a.edits.json"
    path.write_text(stored)
    edits = WikiEdits(tmp_path)
    changes: list[Callable[[], object]] = [
        lambda: edits.save("a", "a-rain", "Rain", "Rain falls."),
        lambda: edits.discard("a", "a-rain"),
        lambda: edits.reviewed("a", "a-rain"),
        lambda: edits.flag_all("a"),
    ]
    for change in changes:
        with pytest.raises(EditError, match="could not be read, so nothing was changed") as refused:
            change()
        assert refused.value.status == 500
    assert path.read_text() == stored  # left as it was, to be recovered


def test_an_edit_whose_entry_is_gone_is_listed_as_lost() -> None:
    entries = [{"id": "a-rain", "entries": [{"id": "a-drops", "entries": []}]}]
    edits = {
        "a-drops": {"title": "Drops", "summary": "Small.", "review": True},
        "a-hail": {"title": "Hail", "summary": "Ice.", "review": True},
    }
    assert lost(entries, edits) == [{"id": "a-hail", "title": "Hail", "summary": "Ice."}]


def test_a_rebuild_keeps_the_edits_and_flags_them(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    store, readings, wiki = jobs(tmp_path)
    pdf = store.add("weather.pdf", io.BytesIO(PDF))
    readings.queue(pdf)
    settle(readings, wiki)

    page = wiki.edit(f"{pdf.id}-p1", "Rain", "Rain falls from clouds.")
    assert page["title"] == "Rain" and page["summary"] == "Rain falls from clouds."
    assert page["edited"] and not page["review"]
    assert "Wiki entry edited" in caplog.text
    with pytest.raises(EditError, match="No such wiki page") as refused:
        wiki.edit(f"{pdf.id}-nope", "Rain", "Rain falls.")
    assert refused.value.status == 404

    assert wiki.rebuild(pdf.id) and not wiki.rebuild("f" * 32)
    wiki.wait()
    [contents] = wiki.contents()
    rain = contents["entries"][0]
    assert rain["title"] == "Rain" and rain["edited"] and rain["review"]  # kept, to check
    assert rain["built"] == {"title": "Rain.", "summary": "Rain."}  # what the rebuild says
    assert not contents["entries"][1]["edited"] and contents["lost_edits"] == []
    assert wiki.built(pdf.id)["edits"][f"{pdf.id}-p1"]["review"]  # type: ignore[index]
    built = [r for r in caplog.records if r.message == "Wiki pages built"][-1]
    assert built.__dict__["flagged_edits"] == 1

    assert wiki.reviewed(f"{pdf.id}-p1") and not wiki.reviewed(f"{pdf.id}-p2")
    assert not wiki.contents()[0]["entries"][0]["review"]
    assert "built" not in wiki.contents()[0]["entries"][0]
    assert wiki.undo_edit(f"{pdf.id}-p1") and not wiki.undo_edit(f"{pdf.id}-p1")
    assert wiki.contents()[0]["entries"][0]["title"] == "Rain."  # as the LLM built it

    wiki.edit(f"{pdf.id}-p2", "Snow", "Snow is frozen.")
    wiki.forget(pdf.id)
    assert wiki.edits.get(pdf.id) == {}  # removing the PDF removes its edits


def test_a_rebuild_that_drops_an_edited_entry_lists_the_edit(tmp_path: Path) -> None:
    builds = 0

    def fewer_each_time(
        pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress, wait: Any = None
    ) -> Wiki:
        nonlocal builds
        builds += 1
        pages = [WikiPage(f"{pdf_id}-p{n}", f"Page {n}", "Text.", [n]) for n in (1, 2)]
        return Wiki(1, pages[: 3 - builds])

    store = ContentStore(tmp_path)
    readings = ReadingJob(store, two_pages)
    wiki = WikiJob(store, readings, fewer_each_time)
    readings.on_read = wiki.read
    pdf = store.add("weather.pdf", io.BytesIO(PDF))
    readings.queue(pdf)
    settle(readings, wiki)
    wiki.edit(f"{pdf.id}-p2", "My page 2", "What I wrote.")
    wiki.rebuild(pdf.id)
    wiki.wait()
    [contents] = wiki.contents()
    assert [e["id"] for e in contents["entries"]] == [f"{pdf.id}-p1"]
    assert contents["lost_edits"] == [
        {"id": f"{pdf.id}-p2", "title": "My page 2", "summary": "What I wrote."}
    ]
    assert wiki.page(f"{pdf.id}-p2") is None
    assert wiki.undo_edit(f"{pdf.id}-p2")  # discarded
    assert wiki.contents()[0]["lost_edits"] == []


def test_a_detail_pages_trail_shows_the_edited_titles(tmp_path: Path) -> None:
    store, readings, wiki = jobs(tmp_path)
    pdf = store.add("weather.pdf", io.BytesIO(PDF))
    readings.queue(pdf)
    settle(readings, wiki)
    path = tmp_path / "content" / "wiki" / f"{pdf.id}.json"
    saved = json.loads(path.read_text())
    part = {"id": f"{pdf.id}-drops", "title": "Drops", "summary": "Drops.", "pages": [1]}
    saved["outline"][0] |= {"detail": True, "entries": [{**part, "detail": False, "entries": []}]}
    path.write_text(json.dumps(saved))
    wiki.edit(f"{pdf.id}-p1", "Rain", "Rain falls.")
    page = wiki.page(f"{pdf.id}-drops")
    assert page is not None and page["trail"] == [{"id": f"{pdf.id}-p1", "title": "Rain"}]


def test_the_wiki_api_edits_undoes_and_rebuilds(tmp_path: Path) -> None:
    app = create_app(tmp_path, read_pdf=two_pages, build_wiki=one_page_per_piece)
    client = TestClient(app)
    pdf = client.post("/api/content", files={"file": ("w.pdf", PDF, "application/pdf")}).json()
    settle(app.state.readings, app.state.wiki)
    entry = f"{pdf['id']}-p1"

    edit = {"title": "Rain", "summary": "Rain falls from clouds."}
    page = client.put(f"/api/wiki/{entry}", json=edit).json()
    assert page["summary"] == "Rain falls from clouds." and page["edited"]
    assert client.put(f"/api/wiki/{entry}", json={**edit, "title": " "}).status_code == 422
    assert client.put(f"/api/wiki/{pdf['id']}-nope", json=edit).status_code == 404

    # Kept after a restart.
    restarted = TestClient(create_app(tmp_path, read_pdf=two_pages, build_wiki=one_page_per_piece))
    assert restarted.get(f"/api/wiki/{entry}").json()["title"] == "Rain"

    rebuilt = client.post(f"/api/content/{pdf['id']}/wiki/rebuild")
    assert rebuilt.status_code == 200 and rebuilt.json()["state"] in ("waiting", "building", "done")
    settle(app.state.readings, app.state.wiki)
    [contents] = client.get("/api/wiki/contents").json()
    assert contents["entries"][0]["review"] and contents["lost_edits"] == []
    assert client.post(f"/api/wiki/{entry}/reviewed").json() == {"reviewed": True}
    assert client.post(f"/api/wiki/{pdf['id']}-p2/reviewed").status_code == 404
    assert client.delete(f"/api/wiki/{entry}/edit").json() == {"undone": True}
    assert client.delete(f"/api/wiki/{entry}/edit").status_code == 404
    assert client.get(f"/api/wiki/{entry}").json()["title"] == "Rain."

    assert client.post(f"/api/content/{'f' * 32}/wiki/rebuild").status_code == 404


def test_a_pdf_not_read_yet_cant_be_rebuilt(tmp_path: Path) -> None:
    def never_read(path: Path, progress: Progress) -> Reading:
        raise RuntimeError("unreadable")

    client = TestClient(create_app(tmp_path, read_pdf=never_read, build_wiki=one_page_per_piece))
    pdf = client.post("/api/content", files={"file": ("w.pdf", PDF, "application/pdf")}).json()
    client.app.state.readings.wait()  # type: ignore[attr-defined]
    refused = client.post(f"/api/content/{pdf['id']}/wiki/rebuild")
    assert refused.status_code == 409 and "hasn't been read" in refused.json()["detail"]


def test_api_edit_failures_are_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app(tmp_path, read_pdf=two_pages, build_wiki=one_page_per_piece)
    client = TestClient(app)
    pdf = client.post("/api/content", files={"file": ("w.pdf", PDF, "application/pdf")}).json()
    settle(app.state.readings, app.state.wiki)
    entry = f"{pdf['id']}-p1"
    client.put(f"/api/wiki/{entry}", json={"title": "Rain", "summary": "Rain falls."})

    def fail(*args: Any) -> bool:
        raise EditError("The edit could not be saved. Try again.", status=500)

    monkeypatch.setattr(app.state.wiki.edits, "discard", fail)
    monkeypatch.setattr(app.state.wiki.edits, "reviewed", fail)
    assert client.delete(f"/api/wiki/{entry}/edit").status_code == 500
    assert client.post(f"/api/wiki/{entry}/reviewed").status_code == 500


def test_a_failed_flag_after_a_rebuild_keeps_the_new_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, readings, wiki = jobs(tmp_path)
    pdf = store.add("weather.pdf", io.BytesIO(PDF))
    readings.queue(pdf)
    settle(readings, wiki)

    def fail(pdf_id: str) -> int:
        raise EditError("The edit could not be saved. Try again.", status=500)

    monkeypatch.setattr(wiki.edits, "flag_all", fail)
    wiki.rebuild(pdf.id)
    wiki.wait()
    assert wiki.statuses()[pdf.id].state == "done"


def test_an_edit_made_as_a_rebuild_is_saved_is_not_flagged(tmp_path: Path) -> None:
    """The new pages and the flags on the edits made before them go in together: an edit
    waiting for them is made on the new pages, and not flagged."""
    store, readings, wiki = jobs(tmp_path)
    pdf = store.add("weather.pdf", io.BytesIO(PDF))
    readings.queue(pdf)
    settle(readings, wiki)
    wiki.edit(f"{pdf.id}-p1", "Rain", "Before the rebuild.")

    edited = threading.Event()
    late: list[threading.Thread] = []
    flag_all = wiki.edits.flag_all

    def late_edit() -> None:
        wiki.edit(f"{pdf.id}-p2", "Snow", "After the rebuild.")
        edited.set()

    def flag_after_a_late_edit(pdf_id: str) -> int:
        # The new pages are saved: an edit now would be on them.
        thread = threading.Thread(target=late_edit)
        thread.start()
        late.append(thread)
        edited.wait(0.5)  # it waits for the flags, so it isn't done
        return flag_all(pdf_id)

    wiki.edits.flag_all = flag_after_a_late_edit  # type: ignore[method-assign]
    wiki.rebuild(pdf.id)
    wiki.wait()
    late[0].join(5)
    edits = wiki.edits.get(pdf.id)
    assert edits[f"{pdf.id}-p1"]["review"]  # made before the rebuild: to check
    assert not edits[f"{pdf.id}-p2"]["review"]  # made on the new pages
