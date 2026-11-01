"""The question and answer screen for visitors who aren't signed in (roadmap R45, item 31)."""

import logging
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from test_question_scope import Llm
from test_topics import riemann_app

from imageskin.app import create_app
from imageskin.host_api import NOT_SIGNED_IN
from imageskin.review import Review
from imageskin.ui_settings import UiSettings
from imageskin.visitor import OFF_FOR_VISITORS, for_visitor

ALL_ON = {"teach_me": True, "quiz_me": True, "assessment": True}

# Reading the wiki and the PDFs: the host's to a visitor too, until R46's participants.
READING_CALLS = [
    "/api/content",
    "/api/content/some-pdf",
    "/api/content/some-pdf/reading",
    "/api/content/some-pdf/wiki",
    "/api/content/some-pdf/wiki/file",
    "/api/wiki",
    "/api/wiki/contents",
    "/api/wiki/builds",
    "/api/wiki/some-page",
]


def signed_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """From here on, the browser is no longer signed in as a host: a visitor."""
    monkeypatch.setattr("imageskin.hosts.HostAccounts.host", lambda self, token: None)


def test_a_visitor_has_teach_me_quiz_me_and_the_assessment_off(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = UiSettings(teach_me=True, quiz_me=True, assessment=True, show_metrics=True)
    with caplog.at_level(logging.INFO, logger="imageskin.visitor"):
        off = for_visitor(settings)
    assert (off.teach_me, off.quiz_me, off.assessment) == (False, False, False)
    assert off.show_metrics  # the rest are left as the host set them
    logged = next(r for r in caplog.records if r.message == "Turned off for a visitor")
    assert logged.settings == list(OFF_FOR_VISITORS)  # type: ignore[attr-defined]


def test_nothing_is_logged_when_they_are_already_off(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="imageskin.visitor"):
        assert for_visitor(UiSettings()) == UiSettings()
    assert "Turned off for a visitor" not in caplog.messages


def test_the_settings_a_visitor_reads_have_them_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    browser = TestClient(create_app(tmp_path))
    assert browser.patch("/api/settings", json=ALL_ON).status_code == 200
    host_sees = browser.get("/api/settings").json()
    assert {k: host_sees[k] for k in ALL_ON} == ALL_ON
    signed_out(monkeypatch)
    visitor_sees = browser.get("/api/settings").json()
    assert {k: visitor_sees[k] for k in ALL_ON} == dict.fromkeys(ALL_ON, False)
    assert visitor_sees["view"] == "participant"
    chosen = [r for r in caplog.records if r.getMessage() == "View chosen"]
    assert [r.visitor for r in chosen] == [False, True]  # type: ignore[attr-defined]


def test_the_wiki_and_the_pdfs_refuse_a_visitor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    browser = TestClient(create_app(tmp_path))
    for path in READING_CALLS:  # a host gets past the check
        answer = browser.get(path)
        assert answer.status_code != 401 or answer.json() != {"detail": NOT_SIGNED_IN}, path
    signed_out(monkeypatch)
    for path in READING_CALLS:
        answer = browser.get(path)
        assert (path, answer.status_code) == (path, 401)
        assert answer.json() == {"detail": NOT_SIGNED_IN}
    refused = [r for r in caplog.records if r.getMessage() == "Host call refused"]
    assert [r.path for r in refused] == READING_CALLS  # type: ignore[attr-defined]
    # The chat's own calls stay open.
    assert browser.get("/api/settings").status_code == 200


def chat(client: Any, prompt: str) -> dict[str, Any]:
    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        response = client.post("/api/chat", json={"prompt": prompt})
    assert response.status_code == 200, response.text
    return dict(response.json())


@pytest.mark.parametrize(
    "prompt",
    [f"{ask} Zeta Function Integral" for ask in ("Teach me about", "Quiz me on", "Assess me on")],
)
def test_for_a_visitor_teach_me_quiz_me_and_assess_me_are_ordinary_prompts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prompt: str
) -> None:
    llm = Llm()
    client = riemann_app(tmp_path, llm)
    assert client.patch("/api/settings", json=ALL_ON).status_code == 200
    signed_out(monkeypatch)
    reply = chat(client, prompt)
    assert reply["content"] == "Two moons."
    assert reply["choices"] == [] and reply["lesson"] is None
    assert reply["quiz"] is None and reply["assessment"] is None
    assert llm.sent[-1][-1]["content"].endswith(prompt)


def test_a_host_still_gets_teach_me(tmp_path: Path) -> None:
    llm = Llm()
    client = riemann_app(tmp_path, llm)
    assert client.patch("/api/settings", json=ALL_ON).status_code == 200
    reply = chat(client, "Teach me")
    assert [c["label"] for c in reply["choices"]][:2] == [
        "Prime Number Basics",
        "Zeta Function Integral",
    ]
    assert llm.sent == []  # the topics are offered without asking the LLM
