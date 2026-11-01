"""The administrator's guidelines keep a history of each part, as the host's do (roadmap R253):
going back changes only that part and adds no change."""

import json
import logging
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_admin_guidelines import ONE, THREE, as_admin
from test_question_scope import Llm
from test_quiz import chat
from test_topics import riemann_app

from imageskin.admin_guidelines import (
    EMPTY,
    HISTORY_FILE,
    AdminGuidelines,
    AdminGuidelinesFile,
    value_of,
    with_value,
)
from imageskin.app import create_app
from imageskin.customization import CustomizationRefused
from imageskin.customization_history import HISTORY_FILE as HOST_HISTORY_FILE
from imageskin.customization_history import History

BRIEF = "Name the main idea first."
BRIEFER = "Name the main idea first, in one sentence."
SIMPLER = "Use everyday words."


def put(client: Any, **edit: Any) -> Any:
    """Save the admin guidelines as the page does: whole."""
    saved = client.put("/api/admin/guidelines", json=edit)
    assert saved.status_code == 200, saved.text
    return saved.json()


def history(client: Any) -> dict[str, Any]:
    return {h["part"]: h for h in client.get("/api/admin/guidelines/history").json()["parts"]}


def test_a_parts_value_and_setting_it_back() -> None:
    admin = AdminGuidelines({"name": "Tutor"}, ("Be accurate.",), {"topics": BRIEF})
    assert value_of(admin, "identity")["name"] == "Tutor"
    assert value_of(admin, "identity")["purpose"] == ""
    assert value_of(admin, "goals") == ["Be accurate."]
    assert value_of(admin, "topics") == BRIEF and value_of(admin, "questions") == ""
    assert with_value(admin, "topics", "") == AdminGuidelines({"name": "Tutor"}, ("Be accurate.",))
    assert with_value(admin, "goals", []).goals == ()
    assert with_value(EMPTY, "identity", value_of(admin, "identity")).identity == {"name": "Tutor"}
    assert with_value(admin, "questions", None) == admin
    with pytest.raises(CustomizationRefused):
        with_value(admin, "goals", "not a list")


def test_going_back_on_one_part_keeps_the_others_and_adds_no_change(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client: Any = as_admin(riemann_app(tmp_path, Llm()), tmp_path)
    assert history(client) == {}
    with caplog.at_level(logging.INFO):
        put(client, guidelines={"topics": BRIEF})
        put(client, guidelines={"topics": BRIEFER})
        put(client, guidelines={"topics": BRIEFER, "say it simpler": SIMPLER})
    kept = history(client)
    assert list(kept) == ["topics", "say it simpler"]
    topics = kept["topics"]
    assert topics["label"] == "Topics" and topics["current"] == 3
    assert [(c["number"], c["made_by"], c["value"]) for c in topics["changes"]] == [
        (3, "saved", BRIEFER),
        (2, "saved", BRIEF),
        (1, "shipped", ""),  # empty to begin with
    ]
    assert [c["value"] for c in kept["say it simpler"]["changes"]] == [SIMPLER, ""]
    assert "Admin guidelines change kept" in caplog.text

    with caplog.at_level(logging.INFO):
        back = client.post("/api/admin/guidelines/history/topics/2/restore")
    assert back.status_code == 200
    assert back.json()["guidelines"]["topics"] == BRIEF
    assert back.json()["guidelines"]["say it simpler"] == SIMPLER  # kept
    restored = next(r for r in caplog.records if r.message == "Admin guidelines restored")
    assert restored.part == "topics" and restored.number == 2  # type: ignore[attr-defined]
    after = history(client)["topics"]
    assert after["current"] == 2 and len(after["changes"]) == 3  # no change added
    assert client.get("/api/admin/guidelines").json()["guidelines"]["topics"] == BRIEF

    # An edit after it adds one; the change gone back from stays.
    put(client, guidelines={"topics": "Start with an example.", "say it simpler": SIMPLER})
    after = history(client)["topics"]
    assert after["current"] == 4 and [c["number"] for c in after["changes"]] == [4, 3, 2, 1]

    # Kept apart from the host's history.
    assert not (tmp_path / HOST_HISTORY_FILE).exists()
    assert client.get("/api/customization/history").json() == {"parts": []}


def test_clear_is_a_change_and_can_be_gone_back_on(tmp_path: Path) -> None:
    client: Any = as_admin(riemann_app(tmp_path, Llm()), tmp_path)
    put(client, identity={"name": "Tutor"}, goals=["Be accurate."])
    put(client, goals=["Be accurate."])  # the identity cleared
    identity = history(client)["identity"]
    assert [c["value"]["name"] for c in identity["changes"]] == ["", "Tutor", ""]
    back = client.post("/api/admin/guidelines/history/identity/2/restore").json()
    assert back["identity"]["name"] == "Tutor" and back["goals"] == ["Be accurate."]


def test_the_next_answer_follows_the_requirement_gone_back_to(tmp_path: Path) -> None:
    llm = Llm()
    client: Any = as_admin(riemann_app(tmp_path, llm), tmp_path)
    client.put("/api/customization/guidelines/questions", json={"text": ONE})
    put(client, guidelines={"questions": THREE})
    put(client, guidelines={"questions": "Answer in two sentences."})
    client.post("/api/admin/guidelines/history/questions/2/restore")
    chat(client, "What is the zeta function?")
    system = llm.sent[-1][0]["content"]
    assert THREE in system and "two sentences" not in system


def test_the_history_is_opened_and_a_missing_change_is_404(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client: Any = as_admin(riemann_app(tmp_path, Llm()), tmp_path)
    put(client, goals=["Be accurate."])
    with caplog.at_level(logging.INFO):
        assert len(client.get("/api/admin/guidelines/history?opened=true").json()["parts"]) == 1
    assert "Admin guidelines history opened" in caplog.text
    assert client.post("/api/admin/guidelines/history/goals/9/restore").status_code == 404
    assert client.post("/api/admin/guidelines/history/topics/1/restore").status_code == 404


def test_a_kept_change_no_longer_valid_is_refused(tmp_path: Path) -> None:
    client: Any = as_admin(riemann_app(tmp_path, Llm()), tmp_path)
    put(client, goals=["Be accurate."])
    path = tmp_path / HISTORY_FILE
    data = json.loads(path.read_text())
    data["parts"]["goals"]["changes"][0]["value"] = "not a list"
    path.write_text(json.dumps(data))
    refused = client.post("/api/admin/guidelines/history/goals/1/restore")
    assert refused.status_code == 400
    assert client.get("/api/admin/guidelines").json()["goals"] == ["Be accurate."]


def test_a_go_back_that_cant_be_saved_says_so(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client: Any = as_admin(riemann_app(tmp_path, Llm()), tmp_path)
    put(client, goals=["Be accurate."])
    (tmp_path / "admin-guidelines.saving.json").mkdir()  # in the way of the save
    with caplog.at_level(logging.ERROR):
        failed = client.post("/api/admin/guidelines/history/goals/1/restore")
    assert failed.status_code == 500 and "Admin guidelines can't be saved" in caplog.text


def test_saves_and_go_backs_are_told_to_the_history_in_order(tmp_path: Path) -> None:
    kept = History(tmp_path, HISTORY_FILE, value_of, EMPTY, "Admin guidelines")
    file = AdminGuidelinesFile(tmp_path, kept.saved)
    file.save(AdminGuidelines({}, ("One.",)))
    saved, changed = file.change(lambda now: AdminGuidelines({}, (*now.goals, "Two.")))
    assert saved.goals == ("One.", "Two.") and changed == ["goals"]
    file.change(lambda now: with_value(now, "goals", ["One."]), gone_back=("goals", 2))
    goals = kept.part("goals")
    assert goals.current == 2 and len(goals.changes) == 3


@pytest.mark.real_hosts
def test_only_the_administrator_reads_or_restores_it(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/admin/guidelines/history").status_code == 401
    assert client.post("/api/admin/guidelines/history/goals/1/restore").status_code == 401
