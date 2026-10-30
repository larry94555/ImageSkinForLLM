"""The identity and goals in every reply (roadmap R92)."""

import json
import logging
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from test_question_scope import Llm, app_with_content, find

from imageskin.app import create_app
from imageskin.chat import NO_IDENTITY, Conversation, Message, system_prompt
from imageskin.customization import (
    CUSTOMIZATION_FILE,
    FEATURES,
    SHIPPED,
    Customization,
    CustomizationFile,
    CustomizationRefused,
    CustomizationUnreadable,
    Feature,
    Identity,
    NoSuchFeature,
    Read,
    about_me,
    asks_about_identity,
    features,
    from_dict,
    guidelines_of,
    instructions,
    save,
    with_goals,
    with_guidelines,
    with_identity,
)
from imageskin.review import Review

SHIPPED_ANSWER = (
    "My purpose is to help you understand the material I was given. I'm here for anyone who"
    " wants to learn about it. I can help with answering your questions about it, teaching it"
    " in short parts, quizzing you on it and assessing what you know."
)
MAYA = Customization(
    Identity(name="Maya", purpose="to teach astronomy", audience="", helps_with="the planets"),
    ("Make every answer exam-ready",),
)


def errors(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.message == "Customization can't be read"]


def test_a_missing_file_is_the_shipped_default(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    read = CustomizationFile(tmp_path).read()
    assert (read.customization, read.shipped) == (SHIPPED, True)
    assert not errors(caplog)


def test_a_save_is_read_back_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    file = CustomizationFile(tmp_path)
    save(tmp_path, MAYA)
    read = file.read()
    assert (read.customization, read.shipped) == (MAYA, False)
    assert [p.name for p in tmp_path.iterdir()] == [CUSTOMIZATION_FILE]
    data = json.loads((tmp_path / CUSTOMIZATION_FILE).read_text())
    assert data["identity"]["name"] == "Maya" and data["guidelines"] == {}


def test_a_broken_file_is_the_shipped_default_logged_once_until_it_changes(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / CUSTOMIZATION_FILE
    path.write_text("{not json")
    file = CustomizationFile(tmp_path)
    with caplog.at_level(logging.ERROR):
        assert file.read().shipped and file.read().shipped
    assert len(errors(caplog)) == 1
    assert errors(caplog)[0].path == str(path)  # type: ignore[attr-defined]
    save(tmp_path, MAYA)
    assert file.read().customization == MAYA
    path.unlink()
    assert file.read().customization == SHIPPED


def test_an_unreadable_file_is_the_shipped_default(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    file = CustomizationFile(tmp_path)
    with (
        patch.object(Path, "stat", side_effect=PermissionError("denied")),
        caplog.at_level(logging.ERROR),
    ):
        assert file.read().shipped
    assert "denied" in errors(caplog)[0].error  # type: ignore[attr-defined]


def test_a_part_left_out_is_as_shipped() -> None:
    read = from_dict({"identity": {"name": " Maya "}, "goals": ["Be kind.", " "]})
    assert read.identity == Identity(name="Maya")
    assert read.goals == ("Be kind.",)
    assert from_dict({}) == SHIPPED


@pytest.mark.parametrize(
    ("data", "why"),
    [
        ([], "not a JSON object"),
        ({"identity": "Maya"}, "identity is not"),
        ({"identity": {"name": 3}}, "identity.name is not text"),
        ({"goals": "Be kind."}, "goals is not"),
        ({"goals": [1]}, "goals is not"),
        ({"guidelines": []}, "guidelines is not"),
    ],
)
def test_a_file_of_the_wrong_shape_cant_be_read(data: Any, why: str) -> None:
    with pytest.raises(CustomizationUnreadable, match=why):
        from_dict(data)


@pytest.mark.parametrize(
    "prompt",
    [
        "Who are you?",
        "who r you",
        "So, who are you?",
        "What are you?",
        "What is your purpose?",
        "What’s your name?",
        "What are your goals?",
        "What are you for?",
        "Why are you here?",
        "Who am I talking to?",
        "Tell me about yourself.",
        "Can you tell me about yourself, please?",
        "Introduce yourself",
    ],
)
def test_questions_about_the_ai_are_recognized(prompt: str) -> None:
    assert asks_about_identity(prompt)


@pytest.mark.parametrize(
    "prompt",
    [
        "Who are you talking about?",
        "What can you talk about?",
        "What is your favourite planet?",
        "Who are the moons of Mars named after?",
    ],
)
def test_other_questions_are_not(prompt: str) -> None:
    assert not asks_about_identity(prompt)


def test_the_identity_is_said_in_the_first_person_without_its_empty_parts() -> None:
    assert " ".join(about_me(SHIPPED.identity)) == SHIPPED_ANSWER
    assert about_me(MAYA.identity) == [
        "I'm Maya.",
        "My purpose is to teach astronomy.",
        "I can help with the planets.",
    ]
    assert about_me(Identity("", "", "", "", "")) == []


def test_the_llm_is_told_the_identity_who_it_speaks_as_and_the_goals() -> None:
    told = instructions(MAYA)
    assert told.startswith("This is who you are, in your own words: \"I'm Maya. My purpose")
    assert "You speak as the person seen in the video, in the first person." in told
    assert told.endswith("Your goals: Make every answer exam-ready.")
    assert instructions(Customization(Identity("", "", "", "", ""), ())) == ""


def reading(customization: Customization, shipped: bool = False) -> Read:
    return Read(customization, shipped, 0.1)


def test_every_prompt_is_sent_with_the_identity_and_goals_as_they_are_then(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    llm = Llm()
    file = CustomizationFile(tmp_path)
    conversation = Conversation(llm, lambda: 4096, customization=file.read)
    with caplog.at_level(logging.INFO, logger="imageskin.chat"):
        conversation.send("How many moons has Mars?")
        save(tmp_path, MAYA)
        conversation.send("And Jupiter?")
    first, second = (sent[0]["content"] for sent in llm.sent)
    assert first.startswith(instructions(SHIPPED)) and system_prompt() in first
    assert second.startswith(instructions(MAYA))
    used = [r for r in caplog.records if r.message == "Identity used"]
    assert [r.shipped for r in used] == [True, False]  # type: ignore[attr-defined]
    assert all(r.duration_ms >= 0 for r in used)  # type: ignore[attr-defined]


def test_without_a_reader_nothing_is_added() -> None:
    llm = Llm()
    Conversation(llm, lambda: 4096).send("Hello?")
    assert llm.sent[0][0]["content"].startswith(system_prompt())


def test_who_are_you_is_answered_from_the_identity_with_general_prompts_off(
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm = Llm()
    conversation = Conversation(
        llm,
        lambda: 4096,
        find=find,
        content_only=lambda: True,
        customization=lambda: reading(MAYA),
    )
    with caplog.at_level(logging.INFO, logger="imageskin.chat"):
        reply, _ = conversation.send("Who are you?")
        conversation.send("How many moons has Mars?")
    assert (
        reply.content == "I'm Maya. My purpose is to teach astronomy. I can help with the planets."
    )
    assert len(llm.sent) == 1  # only Mars asked the LLM
    sent: list[Message] = llm.sent[0]
    assert [m["content"] for m in sent[1:3]] == ["Who are you?", reply.content]
    assert "Identity asked for" in caplog.text


def test_who_are_you_is_spoken_like_a_streamed_reply() -> None:
    def stream(messages: list[Message]) -> Any:
        raise AssertionError("the LLM isn't asked")

    said: list[str | None] = []
    conversation = Conversation(
        Llm(), lambda: 4096, stream=stream, customization=lambda: reading(MAYA)
    )
    conversation.send("Who are you?", said.append)
    assert said[0] is None and "I'm Maya." in said[1:]


def test_an_empty_identity_still_answers() -> None:
    blank = Customization(Identity("", "", "", "", ""), ())
    conversation = Conversation(Llm(), lambda: 4096, customization=lambda: reading(blank))
    assert conversation.send("Who are you?")[0].content == NO_IDENTITY


def test_a_reader_that_fails_leaves_the_identity_out_and_the_chat_goes_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken() -> Read:
        raise RuntimeError("gone")

    llm = Llm()
    conversation = Conversation(llm, lambda: 4096, customization=broken)
    with caplog.at_level(logging.ERROR, logger="imageskin.chat"):
        assert conversation.send("Hello?")[0].content == "Two moons."
        assert conversation.send("Who are you?")[0].content == NO_IDENTITY
    assert llm.sent[0][0]["content"].startswith(system_prompt())
    assert "Could not read the identity" in caplog.text


def test_the_app_answers_who_are_you_from_the_file_with_general_prompts_off(
    tmp_path: Path,
) -> None:
    llm = Llm()
    client = app_with_content(tmp_path, llm, general_prompts=False, add_pdf=True)
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        shipped = client.post("/api/chat", json={"prompt": "Who are you?"}).json()
        save(tmp_path, MAYA)
        edited = client.post("/api/chat", json={"prompt": "What is your purpose?"}).json()
        client.post("/api/chat", json={"prompt": "Which moons circle Mars?"})
    assert shipped["content"] == SHIPPED_ANSWER
    assert edited["content"].startswith("I'm Maya.")
    assert llm.sent[-1][0]["content"].startswith(instructions(MAYA))


def test_a_host_gets_the_customization(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    client = TestClient(create_app(tmp_path))
    with caplog.at_level(logging.INFO, logger="imageskin.app"):
        got = client.get("/api/customization")
        assert not any(r.message == "Customization page opened" for r in caplog.records)
        save(tmp_path, MAYA)
        opened = client.get("/api/customization?opened=true")
    assert got.status_code == 200
    assert got.json() == {**SHIPPED.as_dict(), "features": [], "shipped": True}
    assert opened.json()["identity"]["name"] == "Maya"
    logged = [r for r in caplog.records if r.message == "Customization page opened"]
    assert [r.shipped for r in logged] == [False]  # type: ignore[attr-defined]


@pytest.mark.real_hosts
def test_anyone_not_signed_in_as_a_host_is_refused(tmp_path: Path) -> None:
    got = TestClient(create_app(tmp_path)).get("/api/customization")
    assert got.status_code == 401


# The Customization page's edits (R94).

QUESTIONS = Feature(
    "Answering questions",
    "How every answer is written.",
    "Which questions are declined stays as the code decides.",
    "Answer from the content, in your own words.",
)


@pytest.fixture
def a_feature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(FEATURES, "questions", QUESTIONS)


def test_the_identity_and_goals_are_edited_and_checked() -> None:
    edited = with_identity(SHIPPED, {"name": "  Maya ", "audience": ""})
    assert (edited.identity.name, edited.identity.audience) == ("Maya", "")
    assert edited.identity.purpose == SHIPPED.identity.purpose
    assert with_goals(SHIPPED, ["Be kind.", "  ", "Be brief."]).goals == ("Be kind.", "Be brief.")
    wrongs: list[tuple[dict[str, object], str]] = [
        ({"age": "3"}, "The identity has no age."),
        ({"name": 3}, "The name must be text."),
        ({"purpose": "x" * 501}, "The purpose is too long: at most 500 characters."),
    ]
    for wrong, why in wrongs:
        with pytest.raises(CustomizationRefused, match=re.escape(why)):
            with_identity(SHIPPED, wrong)
    for goals, why in [
        ("Be kind.", "The goals must be a list."),
        (["x" * 301], "A goal is too long"),
        (["Go."] * 11, "at most 10 goals"),
    ]:
        with pytest.raises(CustomizationRefused, match=why):
            with_goals(SHIPPED, goals)


@pytest.mark.usefixtures("a_feature")
def test_a_features_guidelines_are_edited_and_set_back() -> None:
    assert guidelines_of(SHIPPED, "questions") == QUESTIONS.shipped
    edited = with_guidelines(SHIPPED, "questions", " End with a question. ")
    assert guidelines_of(edited, "questions") == "End with a question."
    assert features(edited) == [
        {"key": "questions", **asdict(QUESTIONS), "text": "End with a question.", "edited": True}
    ]
    back = with_guidelines(edited, "questions", None)
    assert back.guidelines == {} and features(back)[0]["edited"] is False
    with pytest.raises(NoSuchFeature):
        with_guidelines(SHIPPED, "jokes", "Be funny.")
    with pytest.raises(CustomizationRefused, match="Answering questions's guidelines is too"):
        with_guidelines(SHIPPED, "questions", "x" * 2001)


def test_a_change_is_saved_whole_and_read_back_without_reading_the_file_again(
    tmp_path: Path,
) -> None:
    file = CustomizationFile(tmp_path)
    file.change(lambda c: with_identity(c, {"name": "Maya"}))
    file.change(lambda c: with_goals(c, ["Be kind."]))  # keeps the name
    read = file.read()
    assert (read.customization.identity.name, read.customization.goals) == ("Maya", ("Be kind.",))
    assert not read.shipped
    assert from_dict(json.loads((tmp_path / CUSTOMIZATION_FILE).read_text())) == read.customization


def test_a_change_to_a_broken_file_starts_from_the_shipped_default(tmp_path: Path) -> None:
    (tmp_path / CUSTOMIZATION_FILE).write_text("{broken")
    file = CustomizationFile(tmp_path)
    edited = file.change(lambda c: with_identity(c, {"name": "Maya"}))
    assert edited == with_identity(SHIPPED, {"name": "Maya"})
    assert file.read().customization == edited


def test_a_refused_change_saves_nothing(tmp_path: Path) -> None:
    file = CustomizationFile(tmp_path)
    with pytest.raises(CustomizationRefused):
        file.change(lambda c: with_goals(c, "Be kind."))
    assert not (tmp_path / CUSTOMIZATION_FILE).exists()


@pytest.mark.usefixtures("a_feature")
def test_a_host_edits_the_customization_and_the_next_prompt_uses_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    llm = Llm()
    client = app_with_content(tmp_path, llm, general_prompts=False, add_pdf=True)
    with caplog.at_level(logging.INFO, logger="imageskin.app"):
        identity = client.put("/api/customization/identity", json={"name": "Maya"})
        goals = client.put("/api/customization/goals", json={"goals": ["Be exam-ready."]})
        edited = client.put("/api/customization/guidelines/questions", json={"text": "Be brief."})
        back = client.put("/api/customization/guidelines/questions", json={"text": None})
    assert identity.status_code == goals.status_code == edited.status_code == 200
    assert identity.json()["identity"]["name"] == "Maya" and identity.json()["shipped"] is False
    assert goals.json()["goals"] == ["Be exam-ready."]
    assert edited.json()["features"][0]["text"] == "Be brief."
    assert back.json()["features"][0] == {
        "key": "questions",
        **asdict(QUESTIONS),
        "text": QUESTIONS.shipped,
        "edited": False,
    }
    saved = [r for r in caplog.records if r.message == "Customization saved"]
    parts = [(r.part, r.feature) for r in saved]  # type: ignore[attr-defined]
    assert parts == [
        ("identity", None),
        ("goals", None),
        ("guidelines", "questions"),
        ("guidelines set back", "questions"),
    ]
    assert all(r.duration_ms >= 0 for r in saved)  # type: ignore[attr-defined]
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        reply = client.post("/api/chat", json={"prompt": "Who are you?"}).json()
        client.post("/api/chat", json={"prompt": "Which moons circle Mars?"})
    assert reply["content"].startswith("I'm Maya.")
    assert "Your goals: Be exam-ready." in llm.sent[-1][0]["content"]


@pytest.mark.parametrize(
    ("path", "body", "status", "detail"),
    [
        ("identity", {"age": "3"}, 400, "The identity has no age."),
        ("goals", {"goals": "Be kind."}, 400, "The goals must be a list."),
        ("guidelines/jokes", {"text": "Be funny."}, 404, "There is no such feature."),
    ],
)
def test_an_edit_that_cant_be_saved_is_refused_and_says_why(
    tmp_path: Path, path: str, body: dict[str, Any], status: int, detail: str
) -> None:
    client = TestClient(create_app(tmp_path))
    got = client.put(f"/api/customization/{path}", json=body)
    assert (got.status_code, got.json()["detail"]) == (status, detail)
    assert not (tmp_path / CUSTOMIZATION_FILE).exists()


def test_a_save_that_fails_says_so(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    client = TestClient(create_app(tmp_path))
    with (
        patch("imageskin.customization.save", side_effect=OSError("disk full")),
        caplog.at_level(logging.ERROR, logger="imageskin.app"),
    ):
        got = client.put("/api/customization/identity", json={"name": "Maya"})
    assert got.status_code == 500
    assert "Customization can't be saved" in caplog.text


@pytest.mark.real_hosts
@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("identity", {"name": "Maya"}),
        ("goals", {"goals": []}),
        ("guidelines/questions", {"text": "x"}),
    ],
)
def test_edits_are_refused_to_anyone_not_signed_in_as_a_host(
    tmp_path: Path, path: str, body: dict[str, Any]
) -> None:
    got = TestClient(create_app(tmp_path)).put(f"/api/customization/{path}", json=body)
    assert got.status_code == 401
    assert not (tmp_path / CUSTOMIZATION_FILE).exists()
