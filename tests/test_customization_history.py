"""The change history of each part of the customization (roadmap R95; Larry's review on PR #258):
going back changes only that part and adds no change."""

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
    guidelines_of,
    is_edited,
    with_goals,
    with_guidelines,
    with_identity,
)
from imageskin.customization_draft import Generator
from imageskin.customization_history import (
    HISTORY_FILE,
    History,
    NoSuchChange,
    as_text,
    compared,
    parts,
    value_of,
    with_value,
)
from imageskin.quiz import QUESTION_GUIDELINES

GOAL = "Explain the zeta function in your own words."
TOPICS = "Name the topic's main idea first."
SIMPLE = "Use short words."


def kept(tmp_path: Path) -> tuple[CustomizationFile, History]:
    history = History(tmp_path)
    return CustomizationFile(tmp_path, history.saved), history


def numbers(history: History, part: str) -> list[tuple[int, str]]:
    return [(c.number, c.made_by) for c in history.part(part).changes]


def test_each_save_is_a_change_of_only_the_parts_it_changed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    file, history = kept(tmp_path)
    assert history.histories() == []
    with caplog.at_level(logging.INFO, logger="imageskin.customization_history"):
        file.change(lambda c: with_guidelines(c, "topics", TOPICS))
        file.change(lambda c: with_guidelines(c, "say it simpler", SIMPLE))
        file.change(lambda c: with_guidelines(c, "say it simpler", SIMPLE))  # no change
    assert [h.part for h in history.histories()] == ["topics", "say it simpler"]
    assert numbers(history, "topics") == [(1, "shipped"), (2, "saved")]
    topics = history.part("topics")
    assert topics.current == 2 and topics.change(1).value is None
    assert topics.change(2).value == TOPICS
    assert topics.shown()["changes"][0]["number"] == 2  # newest first
    assert topics.shown()["label"] == FEATURES["topics"].label
    logged = [r for r in caplog.records if r.message == "Customization change kept"]
    assert [(r.parts, r.numbers) for r in logged] == [  # type: ignore[attr-defined]
        (["topics"], [2]),
        (["say it simpler"], [2]),
    ]
    assert all(r.duration_ms >= 0 for r in logged)  # type: ignore[attr-defined]
    with pytest.raises(NoSuchChange):
        history.part("goals")
    with pytest.raises(NoSuchChange):
        topics.change(9)


def test_going_back_sets_only_that_part_and_adds_no_change(tmp_path: Path) -> None:
    """Larry's example: change Topics, then Say it simpler, then take Topics back without
    losing Say it simpler."""
    file, history = kept(tmp_path)
    file.change(lambda c: with_guidelines(c, "topics", TOPICS))
    file.change(lambda c: with_guidelines(c, "say it simpler", SIMPLE))
    first = history.part("topics").change(1)
    file.change(
        lambda c: with_value(c, "topics", first.value, first.made_by), gone_back=("topics", 1)
    )
    now = file.read().customization
    assert not is_edited(now, "topics") and guidelines_of(now, "say it simpler") == SIMPLE
    assert numbers(history, "topics") == [(1, "shipped"), (2, "saved")]  # nothing added
    assert history.part("topics").current == 1
    # Only an edit after it is a new change; the one gone back from stays.
    file.change(lambda c: with_guidelines(c, "topics", "Start with an example."))
    assert numbers(history, "topics") == [(1, "shipped"), (2, "saved"), (3, "saved")]
    assert history.part("topics").current == 3


def test_a_draft_adds_a_change_to_each_part_it_changed(tmp_path: Path) -> None:
    file, history = kept(tmp_path)
    file.change(lambda c: with_goals(c, [GOAL]))
    draft = with_identity(with_guidelines(SHIPPED, "teach me", "Drafted."), {"name": "Ada"})
    file.change(lambda c: with_value(draft, "goals", [GOAL], "saved"), made_by="generated")
    assert [h.part for h in history.histories()] == ["identity", "goals", "teach me"]
    assert numbers(history, "identity") == [(1, "shipped"), (2, "generated")]
    assert numbers(history, "goals") == [(1, "shipped"), (2, "saved")]  # the draft kept them
    # Going back to a drafted change keeps it drafted, so Generate again drafts it anew.
    back = with_value(SHIPPED, "teach me", "Drafted.", "generated")
    assert back.generated == ("teach me",)
    assert with_value(back, "teach me", None, "shipped").generated == ()


def test_a_part_saved_before_the_history_starts_as_saved(tmp_path: Path) -> None:
    CustomizationFile(tmp_path).change(lambda c: with_goals(c, [GOAL]))
    file, history = kept(tmp_path)
    file.change(lambda c: with_goals(c, ["Another goal."]))
    assert numbers(history, "goals") == [(1, "saved"), (2, "saved")]
    assert history.part("goals").change(1).value == [GOAL]
    assert value_of(SHIPPED, "identity")["name"] == "" and parts()[:2] == ["identity", "goals"]


def test_a_history_that_cant_be_read_or_written_is_logged_and_saves_stand(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    file, history = kept(tmp_path)
    file.change(lambda c: with_goals(c, [GOAL]))
    data = json.loads((tmp_path / HISTORY_FILE).read_text(encoding="utf-8"))
    data["parts"]["nothing"] = {"current": 1, "changes": []}
    data["parts"]["topics"] = {"current": 1, "changes": [{"number": 1}]}
    (tmp_path / HISTORY_FILE).write_text(json.dumps(data), encoding="utf-8")
    with caplog.at_level(logging.ERROR, logger="imageskin.customization_history"):
        assert [h.part for h in history.histories()] == ["goals"]
        (tmp_path / HISTORY_FILE).write_text("{broken", encoding="utf-8")
        assert history.histories() == []
    assert caplog.text.count("Customization history can't be read") == 3
    (tmp_path / HISTORY_FILE).unlink()
    (tmp_path / HISTORY_FILE).mkdir()  # in the way of the file
    with caplog.at_level(logging.ERROR, logger="imageskin.customization_history"):
        saved = file.change(lambda c: with_goals(c, ["Kept anyway."]))
    assert saved.goals == ("Kept anyway.",) and file.read().customization.goals == saved.goals
    assert "Customization change can't be kept" in caplog.text


def test_the_first_draft_is_kept_as_generated(tmp_path: Path) -> None:
    file, history = kept(tmp_path)
    llm = DraftLlm()
    g = Generator(file, lambda m, s: llm(m, s), lambda: None, lambda: [])
    g.needed()
    g.wait(5)
    assert numbers(history, "identity") == [(1, "shipped"), (2, "generated")]
    assert numbers(history, "teach me") == [(1, "shipped"), (2, "generated")]


def shown(client: Any) -> dict[str, dict[str, Any]]:
    got = client.get("/api/customization/history")
    assert got.status_code == 200
    return {p["part"]: p for p in got.json()["parts"]}


def test_the_host_goes_back_on_quiz_me_only_and_the_next_question_follows_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    llm = QuizLlm("Partly right. It needs the reason.", "Right.")
    client: Any = riemann_app(tmp_path, llm)
    assert client.patch("/api/settings", json={"quiz_me": True}).status_code == 200
    client.put("/api/customization/guidelines/quiz%20questions", json={"text": ASKS})
    client.put("/api/customization/goals", json={"goals": [GOAL]})
    with caplog.at_level(logging.INFO):
        opened = client.get("/api/customization/history?opened=true").json()["parts"]
        assert [(p["part"], p["current"]) for p in opened] == [
            ("goals", 2),
            ("quiz questions", 2),
        ]
        back = client.post("/api/customization/history/quiz%20questions/1/restore")
    assert back.status_code == 200
    assert "quiz questions" not in back.json()["guidelines"]
    assert back.json()["goals"] == [GOAL]  # the other part is as it was
    after = shown(client)
    assert after["quiz questions"]["current"] == 1
    assert [c["number"] for c in after["quiz questions"]["changes"]] == [2, 1]  # nothing added
    quiz = started(client, llm, "Zeta Function Integral")
    chat(client, "An integral.", quiz=quiz)
    assert QUESTION_GUIDELINES not in llm.sent[-1][-1]["content"]
    # And forward again, to the change gone back from.
    assert client.post("/api/customization/history/quiz%20questions/2/restore").status_code == 200
    quiz = started(client, llm, "Zeta Function Integral")
    chat(client, "An integral.", quiz=quiz)
    assert f"{QUESTION_GUIDELINES} {ASKS}" in llm.sent[-1][-1]["content"]
    messages = [r.message for r in caplog.records]
    assert "Customization history opened" in messages
    restore = next(r for r in caplog.records if r.message == "Customization restored")
    assert (restore.part, restore.number, restore.made_by) == ("quiz questions", 1, "shipped")  # type: ignore[attr-defined]


def test_going_back_on_the_identity_or_teach_me(tmp_path: Path) -> None:
    client: Any = riemann_app(tmp_path, Llm())
    client.put("/api/customization/identity", json={"name": "Maya"})
    client.put("/api/customization/guidelines/teach%20me", json={"text": "Use analogies."})
    assert (
        client.post("/api/customization/history/identity/1/restore").json()["identity"]["name"]
        == ""
    )
    teach = client.post("/api/customization/history/teach%20me/1/restore").json()
    assert "teach me" not in teach["guidelines"]


def test_no_such_change_is_a_404(tmp_path: Path) -> None:
    client: Any = riemann_app(tmp_path, Llm())
    assert shown(client) == {}
    assert client.post("/api/customization/history/goals/1/restore").status_code == 404
    client.put("/api/customization/goals", json={"goals": [GOAL]})
    assert client.post("/api/customization/history/goals/7/restore").status_code == 404


def test_a_discarded_draft_adds_nothing_and_a_saved_one_a_change_to_each_part(
    tmp_path: Path,
) -> None:
    client: Any = riemann_app(tmp_path, DraftLlm(name="Grace"))
    client.put("/api/customization/goals", json={"goals": [GOAL]})
    assert list(shown(client)) == ["goals"]
    client.post("/api/customization/draft")
    client.post("/api/customization/draft/discard")
    assert list(shown(client)) == ["goals"]
    body = client.post("/api/customization/draft").json()
    guidelines = {k: body["draft"]["guidelines"][k] for k in body["drafted"]}
    assert client.put("/api/customization/draft", json=to_save(body, guidelines)).status_code == 200
    after = shown(client)
    assert after["identity"]["changes"][0]["made_by"] == "generated"
    # The draft has the same goal, so the goals have no new change.
    assert len(after["goals"]["changes"]) == 2
    assert set(FEATURES) <= set(after)


@pytest.mark.real_hosts
def test_only_a_signed_in_host_sees_the_history(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/customization/history").status_code == 401
    assert client.post("/api/customization/history/goals/1/restore").status_code == 401


def test_saves_made_at_once_are_each_a_change(tmp_path: Path) -> None:
    file, history = kept(tmp_path)
    workers = [
        threading.Thread(target=file.change, args=(lambda c, i=i: with_goals(c, [f"Goal {i}."]),))
        for i in range(8)
    ]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    assert [c.number for c in history.part("goals").changes] == list(range(1, 10))


@pytest.mark.parametrize(
    "stored",
    [
        {"parts": [1]},
        {"parts": "goals"},
        [1, 2],
        {"parts": {"goals": [1]}},
        {"parts": {"goals": {"current": 1, "changes": "x"}}},
        {"parts": {"goals": {"current": 1, "changes": [1]}}},
        {"parts": {"goals": {"current": 1, "changes": []}}},
        {
            "parts": {
                "goals": {
                    "current": 5,
                    "changes": [{"number": 1, "made_at": "t", "made_by": "saved"}],
                }
            }
        },
    ],
)
def test_valid_json_of_the_wrong_shape_never_breaks_a_save(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, stored: object
) -> None:
    """Codex's review on PR #258: a history file of the wrong shape is logged and read as
    empty, and the save it follows still stands, starting the part's history again."""
    file, history = kept(tmp_path)
    (tmp_path / HISTORY_FILE).write_text(json.dumps(stored), encoding="utf-8")
    with caplog.at_level(logging.ERROR, logger="imageskin.customization_history"):
        assert history.histories() == []
        saved = file.change(lambda c: with_goals(c, [GOAL]))
    assert saved.goals == (GOAL,) and file.read().customization.goals == (GOAL,)
    assert "Customization history can't be read" in caplog.text
    assert numbers(history, "goals") == [(1, "shipped"), (2, "saved")]


def test_a_history_of_the_wrong_shape_is_no_500(tmp_path: Path) -> None:
    client: Any = riemann_app(tmp_path, Llm())
    (tmp_path / HISTORY_FILE).write_text(json.dumps({"parts": [1]}), encoding="utf-8")
    assert client.get("/api/customization/history").json() == {"parts": []}
    assert client.put("/api/customization/goals", json={"goals": [GOAL]}).status_code == 200


# --- Comparing changes (R95a) ---


def joined(runs: list[dict[str, str]], kind: str) -> list[str]:
    return [r["text"] for r in runs if r["kind"] == kind]


def test_only_what_changed_is_marked() -> None:
    runs = compared("Name the main idea first.", "Name the main idea of the topic first.")
    assert joined(runs, "added") == ["of the topic "]
    assert joined(runs, "removed") == []
    assert "".join(r["text"] for r in runs if r["kind"] != "added") == "Name the main idea first."
    assert "".join(r["text"] for r in runs if r["kind"] != "removed") == (
        "Name the main idea of the topic first."
    )
    swapped = compared("Use short words.", "Use plain words.")
    assert joined(swapped, "removed") == ["short"] and joined(swapped, "added") == ["plain"]
    assert compared("Same.", "Same.") == [{"kind": "same", "text": "Same."}]
    assert compared("", "New.") == [{"kind": "added", "text": "New."}]


def test_each_part_is_compared_as_text() -> None:
    assert as_text("identity", {"name": "Maya", "purpose": "to teach"}).splitlines()[:3] == [
        "The name: Maya",
        "Speaks as: ",
        "The purpose: to teach",
    ]
    assert as_text("goals", ["One.", "Two."]) == "One.\nTwo."
    assert as_text("topics", None) == FEATURES["topics"].shipped  # as shipped
    assert as_text("topics", TOPICS) == TOPICS


def test_the_host_compares_the_change_in_use_with_an_earlier_one(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client: Any = riemann_app(tmp_path, Llm())
    client.put("/api/customization/guidelines/topics", json={"text": "Name the main idea first."})
    client.put(
        "/api/customization/guidelines/topics",
        json={"text": "Name the main idea of the topic first."},
    )
    with caplog.at_level(logging.INFO):
        before = client.get("/api/customization/history/topics/2/compare")
        first = client.get("/api/customization/history/topics/1/compare")
    assert before.status_code == 200
    body = before.json()
    assert (body["part"], body["earlier"], body["current"]) == ("topics", 2, 3)
    assert joined(body["runs"], "added") == ["of the topic "] and not joined(
        body["runs"], "removed"
    )
    # With the first, every change since: the shipped text taken out.
    assert FEATURES["topics"].shipped.split()[0] in "".join(joined(first.json()["runs"], "removed"))
    logged = [r for r in caplog.records if r.message == "Customization compared"]
    assert [(r.part, r.earlier, r.current, r.added) for r in logged][0] == ("topics", 2, 3, 13)  # type: ignore[attr-defined]
    assert all(r.duration_ms >= 0 for r in logged)  # type: ignore[attr-defined]
    assert client.get("/api/customization/history/topics/9/compare").status_code == 404
    assert client.get("/api/customization/history/goals/1/compare").status_code == 404


@pytest.mark.real_hosts
def test_only_a_signed_in_host_compares(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/customization/history/goals/1/compare").status_code == 401
