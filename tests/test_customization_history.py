"""Change history of the customization: versions, going back and editing (roadmap R95)."""

import json
import logging
import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_customization_draft import DraftLlm, to_save
from test_question_scope import Llm
from test_quiz import QuizLlm, chat, started
from test_quiz_guidelines import ASKS
from test_topics import riemann_app

from imageskin.app import create_app
from imageskin.customization import (
    FEATURES,
    SHIPPED,
    CustomizationFile,
    as_generated,
    guidelines_of,
    with_goals,
    with_guidelines,
)
from imageskin.customization_draft import Generator
from imageskin.customization_history import HISTORY_DIR, History, NoSuchVersion, restored
from imageskin.quiz import QUESTION_GUIDELINES

GOAL = "Explain the zeta function in your own words."
LESSON = "Use one everyday analogy in each part."


def kept(tmp_path: Path) -> tuple[CustomizationFile, History]:
    history = History(tmp_path)
    return CustomizationFile(tmp_path, history.saved), history


def test_the_first_save_keeps_what_there_was_then_each_save_is_a_version(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    file, history = kept(tmp_path)
    assert history.versions() == []
    with caplog.at_level(logging.INFO, logger="imageskin.customization_history"):
        file.change(lambda c: with_goals(c, [GOAL]), part="goals")
        file.change(lambda c: with_guidelines(c, "teach me", LESSON), feature="teach me")
    versions = history.versions()
    assert [(v.number, v.made_by) for v in versions] == [(3, "saved"), (2, "saved"), (1, "shipped")]
    assert versions[0].customization == file.read().customization
    assert versions[1].customization.goals == (GOAL,) and versions[1].part == "goals"
    assert versions[2].customization == SHIPPED
    assert versions[0].features == tuple(FEATURES)
    assert versions[0].listed().keys() == {
        "number",
        "made_at",
        "made_by",
        "part",
        "feature",
        "back_to",
    }
    assert sorted(p.name for p in (tmp_path / HISTORY_DIR).iterdir()) == [
        "000001.json",
        "000002.json",
        "000003.json",
    ]
    logged = [r for r in caplog.records if r.message == "Customization version saved"]
    assert [(r.version, r.feature) for r in logged] == [(2, None), (3, "teach me")]  # type: ignore[attr-defined]
    assert all(r.duration_ms >= 0 for r in logged)  # type: ignore[attr-defined]


def test_a_file_saved_before_the_history_is_kept_as_saved(tmp_path: Path) -> None:
    CustomizationFile(tmp_path).change(lambda c: with_goals(c, [GOAL]))
    file, history = kept(tmp_path)
    file.change(lambda c: with_goals(c, ["Another goal."]))
    first, second = reversed(history.versions())
    assert first.made_by == "saved" and first.customization.goals == (GOAL,)
    assert second.customization.goals == ("Another goal.",)


def test_going_back_keeps_a_feature_added_since_as_it_is_now(tmp_path: Path) -> None:
    file, history = kept(tmp_path)
    file.change(lambda c: with_guidelines(c, "say it simpler", "Use short words."))
    old = history.versions()[1]  # the shipped one
    # As if made before Say it simpler had guidelines (R200).
    older = old.__class__(**{**old.__dict__, "features": tuple(FEATURES)[:-5]})
    now = as_generated(
        with_guidelines(SHIPPED, "detail general", "Define terms."), ["detail general"]
    )
    now = with_guidelines(now, "teach me", LESSON)
    back = restored(older, now)
    assert guidelines_of(back, "detail general") == "Define terms."  # added since: kept
    assert back.generated == ("detail general",)
    assert guidelines_of(back, "teach me") == guidelines_of(SHIPPED, "teach me")  # gone back
    assert restored(old, now) == SHIPPED


def test_a_version_that_cant_be_read_is_logged_and_left_out(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    file, history = kept(tmp_path)
    file.change(lambda c: with_goals(c, [GOAL]))
    (tmp_path / HISTORY_DIR / "000001.json").write_text("{broken", encoding="utf-8")
    (tmp_path / HISTORY_DIR / "notes.txt").write_text("not a version", encoding="utf-8")
    with caplog.at_level(logging.ERROR, logger="imageskin.customization_history"):
        assert [v.number for v in history.versions()] == [2]
    assert "Customization version can't be read" in caplog.text
    with pytest.raises(NoSuchVersion):
        history.version(9)
    bad = {**history.version(2).as_dict(), "made_by": "someone"}
    (tmp_path / HISTORY_DIR / "000002.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(NoSuchVersion):
        history.version(2)


def test_a_version_that_cant_be_written_is_logged_and_the_save_stands(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / HISTORY_DIR).write_text("in the way", encoding="utf-8")
    file, history = kept(tmp_path)
    with caplog.at_level(logging.ERROR, logger="imageskin.customization_history"):
        saved = file.change(lambda c: with_goals(c, [GOAL]))
    assert saved.goals == (GOAL,) and file.read().customization.goals == (GOAL,)
    assert "Customization version can't be saved" in caplog.text


def test_the_first_draft_is_kept_as_generated(tmp_path: Path) -> None:
    file, history = kept(tmp_path)
    llm = DraftLlm()
    g = Generator(file, lambda m, s: llm(m, s), lambda: None, lambda: [])
    g.needed()
    g.wait(5)
    latest = history.versions()[0]
    assert (latest.made_by, latest.part) == ("generated", "draft")
    assert latest.customization.identity.name == "Ada"


def listed(client: Any) -> list[dict[str, Any]]:
    got = client.get("/api/customization/history")
    assert got.status_code == 200
    return list(got.json()["versions"])


def test_the_host_goes_back_and_the_next_quiz_question_follows_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    llm = QuizLlm("Partly right. It needs the reason.", "Right.")
    client: Any = riemann_app(tmp_path, llm)
    assert client.patch("/api/settings", json={"quiz_me": True}).status_code == 200
    client.put("/api/customization/guidelines/quiz%20questions", json={"text": ASKS})
    with caplog.at_level(logging.INFO):
        shown = client.get("/api/customization/history?opened=true").json()["versions"]
        assert [(v["number"], v["made_by"], v["feature"]) for v in shown] == [
            (2, "saved", "quiz questions"),
            (1, "shipped", None),
        ]
        back = client.post("/api/customization/history/1/restore")
    assert back.status_code == 200
    assert "quiz questions" not in back.json()["guidelines"]
    assert [(v["number"], v["made_by"], v["back_to"]) for v in listed(client)][0] == (
        3,
        "gone back to",
        1,
    )
    quiz = started(client, llm, "Zeta Function Integral")
    chat(client, "An integral.", quiz=quiz)
    assert QUESTION_GUIDELINES not in llm.sent[-1][-1]["content"]
    # Going back can be undone: go back to the version with the edit.
    assert client.post("/api/customization/history/2/restore").status_code == 200
    quiz = started(client, llm, "Zeta Function Integral")
    chat(client, "An integral.", quiz=quiz)
    assert f"{QUESTION_GUIDELINES} {ASKS}" in llm.sent[-1][-1]["content"]
    assert len(listed(client)) == 4
    messages = [r.message for r in caplog.records]
    assert "Customization history opened" in messages and "Customization restored" in messages
    restore = next(r for r in caplog.records if r.message == "Customization restored")
    assert (restore.version, restore.made_by, restore.kept) == (1, "shipped", [])  # type: ignore[attr-defined]


def test_no_such_version_is_a_404(tmp_path: Path) -> None:
    client: Any = riemann_app(tmp_path, Llm())
    assert listed(client) == []
    assert client.post("/api/customization/history/7/restore").status_code == 404


def test_a_discarded_draft_is_no_version_and_a_saved_one_is_one(tmp_path: Path) -> None:
    client: Any = riemann_app(tmp_path, DraftLlm(name="Grace"))
    client.put("/api/customization/goals", json={"goals": [GOAL]})
    assert len(listed(client)) == 2
    client.post("/api/customization/draft")
    client.post("/api/customization/draft/discard")
    assert len(listed(client)) == 2
    body = client.post("/api/customization/draft").json()
    guidelines = {k: body["draft"]["guidelines"][k] for k in body["drafted"]}
    assert client.put("/api/customization/draft", json=to_save(body, guidelines)).status_code == 200
    versions = listed(client)
    assert len(versions) == 3
    assert (versions[0]["made_by"], versions[0]["part"]) == ("generated", "draft")


@pytest.mark.real_hosts
def test_only_a_signed_in_host_sees_the_history(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/customization/history").status_code == 401
    assert client.post("/api/customization/history/1/restore").status_code == 401


def test_saves_made_at_once_are_each_a_version(tmp_path: Path) -> None:
    file, history = kept(tmp_path)
    workers = [
        threading.Thread(target=file.change, args=(lambda c, i=i: with_goals(c, [f"Goal {i}."]),))
        for i in range(8)
    ]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    assert [v.number for v in history.versions()] == list(range(9, 0, -1))
