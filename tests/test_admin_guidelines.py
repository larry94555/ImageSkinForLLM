"""The administrator's identity, goals and guidelines as system requirements (roadmap R243)."""

import json
import logging
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_question_scope import Llm
from test_quiz import QuizLlm, chat, started
from test_topics import riemann_app

from imageskin.admin_guidelines import (
    ADMIN_FILE,
    EMPTY,
    GUIDELINES_FIRST,
    HOST_AFTER,
    REQUIREMENTS,
    AdminGuidelines,
    AdminGuidelinesFile,
    applied,
    checked,
    requirements,
)
from imageskin.app import create_app
from imageskin.chat import detail_level, system_message
from imageskin.customization import (
    FEATURES,
    SHIPPED,
    CustomizationRefused,
    guidelines_of,
    instructions,
    is_edited,
    with_guidelines,
)
from imageskin.quiz import QUESTION_GUIDELINES

THREE = "Always answer in at least three sentences."
ONE = "Answer in one sentence."
PRACTICAL = "Ask how the idea applies to a practical situation."


def test_they_are_checked_as_an_edit_is_and_empty_text_is_no_requirement() -> None:
    admin = checked(
        {
            "identity": {"name": "Tutor", "purpose": " "},
            "goals": ["Be accurate.", ""],
            "guidelines": {"questions": THREE, "topics": ""},
        }
    )
    assert admin == AdminGuidelines({"name": "Tutor"}, ("Be accurate.",), {"questions": THREE})
    assert admin.parts() == ["identity", "goals", "questions"]
    shown = admin.as_dict()
    assert shown["identity"]["purpose"] == "" and set(shown["guidelines"]) == set(FEATURES)
    assert checked({}) == EMPTY and EMPTY.parts() == []
    for bad, said in (
        ([], "JSON object"),
        ({"identity": []}, "identity must be"),
        ({"identity": {"age": "9"}}, "no age"),
        ({"goals": "x"}, "goals must be a list"),
        ({"goals": ["g"] * 11}, "at most 10 goals"),
        ({"guidelines": []}, "guidelines must be"),
        ({"guidelines": {"nothing": "x"}}, "no feature nothing"),
        ({"guidelines": {"questions": "x" * 2001}}, "too long"),
    ):
        with pytest.raises(CustomizationRefused, match=said):
            checked(bad)


def test_with_none_written_every_prompt_is_as_before() -> None:
    assert applied(SHIPPED, EMPTY) is SHIPPED
    assert requirements(EMPTY) == ""
    with detail_level(3, SHIPPED):
        before = system_message(None)
    with detail_level(3, applied(SHIPPED, EMPTY)):
        assert system_message(None) == before


def test_they_come_first_as_requirements_over_the_hosts() -> None:
    host = with_guidelines(SHIPPED, "questions", ONE)
    admin = AdminGuidelines(
        {"name": "Tutor"}, ("Be accurate.",), {"questions": THREE, "topics": "Be brief."}
    )
    asked = applied(host, admin)
    assert guidelines_of(asked, "questions") == f"{GUIDELINES_FIRST} {THREE} {HOST_AFTER} {ONE}"
    # The host's as shipped follow the administrator's too.
    topics = FEATURES["topics"].shipped
    assert guidelines_of(asked, "topics") == f"{GUIDELINES_FIRST} Be brief. {HOST_AFTER} {topics}"
    assert is_edited(asked, "topics") and not is_edited(asked, "teach me")
    said = instructions(asked)
    assert said.startswith(f"{REQUIREMENTS} Your name is Tutor. Your goals: Be accurate.")
    assert said.endswith(instructions(host))
    assert asked.as_dict() == {**host.as_dict(), "guidelines": asked.guidelines}  # never saved
    with detail_level(3, asked):
        content = system_message(None)["content"]
    assert content.startswith(REQUIREMENTS) and f"{THREE} {HOST_AFTER} {ONE}" in content


def test_the_file_is_read_once_until_it_changes_and_a_broken_one_is_empty(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    file = AdminGuidelinesFile(tmp_path)
    assert file.read() == EMPTY
    admin = AdminGuidelines({}, ("Be accurate.",), {"questions": THREE})
    with caplog.at_level(logging.INFO, logger="imageskin.admin_guidelines"):
        assert file.save(admin) == ["goals", "questions"]
        assert file.save(admin) == []
    changed = [r.parts for r in caplog.records if r.message == "Admin guidelines changed"]  # type: ignore[attr-defined]
    assert changed == [["goals", "questions"], []]
    assert AdminGuidelinesFile(tmp_path).read() == admin  # after a restart
    (tmp_path / ADMIN_FILE).write_text("{broken", encoding="utf-8")
    with caplog.at_level(logging.ERROR, logger="imageskin.admin_guidelines"):
        assert file.read() == EMPTY
        assert file.read() == EMPTY
    assert caplog.text.count("Admin guidelines can't be read") == 1  # once, not every prompt
    (tmp_path / ADMIN_FILE).write_text(json.dumps({"goals": "x"}), encoding="utf-8")
    assert file.read() == EMPTY
    (tmp_path / ADMIN_FILE).unlink()
    assert file.read() == EMPTY


def as_admin(client: Any, home: Path) -> Any:
    (home / "admin.toml").write_text('password = "secret"\n')
    assert client.post("/api/admin/sign-in", json={"password": "secret"}).status_code == 200
    return client


def test_the_next_answer_follows_the_administrators_over_the_hosts(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    llm = Llm()
    client: Any = as_admin(riemann_app(tmp_path, llm), tmp_path)
    client.put("/api/customization/guidelines/questions", json={"text": ONE})
    chat(client, "What is the zeta function?")
    assert THREE not in llm.sent[-1][0]["content"]
    saved = client.put(
        "/api/admin/guidelines",
        json={"goals": ["Be accurate."], "guidelines": {"questions": THREE}},
    )
    assert saved.status_code == 200 and saved.json()["guidelines"]["questions"] == THREE
    assert client.get("/api/admin/guidelines").json() == saved.json()
    with caplog.at_level(logging.INFO):
        chat(client, "What is the zeta function?")
    system = llm.sent[-1][0]["content"]
    assert system.startswith(f"{REQUIREMENTS} Your goals: Be accurate.")
    assert f"{GUIDELINES_FIRST} {THREE} {HOST_AFTER} {ONE}" in system
    used = [r for r in caplog.records if r.message == "Admin guidelines used"]
    assert used and used[0].parts == ["goals", "questions"]  # type: ignore[attr-defined]
    # Cleared, answers are as before.
    assert client.put("/api/admin/guidelines", json={}).status_code == 200
    chat(client, "What is the zeta function?")
    assert REQUIREMENTS not in llm.sent[-1][0]["content"]
    assert client.put("/api/admin/guidelines", json={"goals": "x"}).status_code == 400


def test_a_quiz_question_follows_the_administrators_quiz_guidelines(tmp_path: Path) -> None:
    llm = QuizLlm("Right.")
    client: Any = as_admin(riemann_app(tmp_path, llm), tmp_path)
    assert client.patch("/api/settings", json={"quiz_me": True}).status_code == 200
    client.put("/api/admin/guidelines", json={"guidelines": {"quiz questions": PRACTICAL}})
    quiz = started(client, llm, "Zeta Function Integral")
    chat(client, "An integral.", quiz=quiz)
    asked = llm.sent[-1][-1]["content"]
    assert f"{QUESTION_GUIDELINES} {GUIDELINES_FIRST} {PRACTICAL} {HOST_AFTER}" in asked


def test_a_save_that_fails_says_so(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    client: Any = as_admin(riemann_app(tmp_path, Llm()), tmp_path)
    (tmp_path / "admin-guidelines.saving.json").mkdir()  # in the way of the save
    with caplog.at_level(logging.ERROR):
        failed = client.put("/api/admin/guidelines", json={"goals": ["Be accurate."]})
    assert failed.status_code == 500 and "Admin guidelines can't be saved" in caplog.text


@pytest.mark.real_hosts
def test_only_the_administrator_reads_or_changes_them(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/admin/guidelines").status_code == 401
    assert client.put("/api/admin/guidelines", json={}).status_code == 401
