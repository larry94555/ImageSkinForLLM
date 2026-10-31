"""The identity, goals and guidelines drafted by the LLM (roadmap R93)."""

import json
import logging
import threading
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from test_question_scope import Llm
from test_teach import chat
from test_topics import riemann_app

from imageskin.chat import Message
from imageskin.customization import (
    FEATURES,
    SHIPPED,
    TEACHING,
    CustomizationFile,
    CustomizationUnreadable,
    features,
    from_dict,
    guidelines_of,
    is_edited,
    with_goals,
    with_guidelines,
)
from imageskin.customization_draft import (
    GENERATED_FILE,
    GenerationFailed,
    Generator,
    draft_asked,
    draft_schema,
    drafted,
    drafted_features,
    generate,
)

EDITED = "Use one everyday analogy in each part."


def reply_for(keys: list[str], name: str = "Ada") -> str:
    return json.dumps(
        {
            "identity": {
                "name": name,
                "purpose": "to help you learn the Riemann hypothesis",
                "audience": "students of number theory",
                "helps_with": "primes and the zeta function",
            },
            "goals": ["Explain the zeta function in your own words."],
            "guidelines": {key: f"Drafted for {key}." for key in keys},
        }
    )


class DraftLlm(Llm):
    """Answers a draft with JSON for each feature asked about, and anything else in a line."""

    def __init__(self, name: str = "Ada") -> None:
        super().__init__()
        self.name = name
        self.release: threading.Event | None = None

    def __call__(self, messages: list[Message], schema: dict[str, Any] | None = None) -> str:
        self.sent.append(messages)
        asked = messages[-1]["content"]
        if not asked.startswith("You are setting up an AI tutor"):
            return "Two moons."
        if self.release is not None:
            self.release.wait(5)
        keys = [k for k in FEATURES if f'- "{k}" (' in asked]
        return "Here it is:\n```json\n" + reply_for(keys, self.name) + "\n```"


def test_what_is_asked_names_the_person_the_topics_and_only_shipped_guidelines() -> None:
    edited = with_guidelines(SHIPPED, "teach me", EDITED)
    asked = draft_asked(edited, "a woman whose role is Professor", ["Primes", "Zeta"])
    assert "The person in the video is a woman whose role is Professor." in asked
    assert "The material's topics are: Primes; Zeta." in asked
    assert '- "questions" (Answering questions):' in asked
    assert '"teach me"' not in asked  # the host's are left alone
    assert drafted_features(edited) == [k for k in FEATURES if k != "teach me"]
    unknown = draft_asked(SHIPPED, None, [])
    assert "a person whose name and role weren't given" in unknown and "not read yet" in unknown
    schema = draft_schema(["questions"])
    assert schema["properties"]["guidelines"]["required"] == ["questions"]


def test_a_draft_takes_the_identity_goals_and_shipped_guidelines_only() -> None:
    edited = with_guidelines(SHIPPED, "teach me", EDITED)
    keys = drafted_features(edited)
    draft = drafted(edited, "```json\n" + reply_for([*keys, "teach me"]) + "\n```")
    assert draft.identity.name == "Ada"
    assert draft.identity.speaks_as == SHIPPED.identity.speaks_as  # told to the LLM only
    assert draft.goals == ("Explain the zeta function in your own words.",)
    assert guidelines_of(draft, "questions") == "Drafted for questions."
    assert guidelines_of(draft, "teach me") == EDITED
    assert all(is_edited(draft, k) for k in FEATURES)


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        ("I can't do that.", "no JSON object"),
        ("{not json}", "not valid JSON"),
        ('{"identity": "Ada"}', "no identity or guidelines"),
        (reply_for([], name="x" * 600), "too long"),
    ],
)
def test_a_bad_draft_is_refused(reply: str, reason: str) -> None:
    with pytest.raises(GenerationFailed, match=reason):
        drafted(SHIPPED, reply)


def test_empty_goals_and_guidelines_keep_what_there_was() -> None:
    data = json.loads(reply_for(["questions"]))
    data["goals"], data["guidelines"]["questions"] = [], " "
    draft = drafted(SHIPPED, json.dumps(data))
    assert draft.goals == SHIPPED.goals and not is_edited(draft, "questions")


def test_a_draft_that_takes_too_long_or_fails_is_not_used() -> None:
    stalled = threading.Event()

    def stall(messages: list[Message], schema: dict[str, Any]) -> str:
        stalled.wait(5)
        return "{}"

    def broken(messages: list[Message], schema: dict[str, Any]) -> str:
        raise OSError("no server")

    with pytest.raises(GenerationFailed, match="no reply within 0.2 s"):
        generate(SHIPPED, stall, None, [], timeout_s=0.2)
    stalled.set()
    with pytest.raises(GenerationFailed, match="the LLM failed: no server"):
        generate(SHIPPED, broken, None, [])


def generator(tmp_path: Path, llm: Any, timeout_s: float = 5) -> tuple[Generator, Any]:
    file = CustomizationFile(tmp_path)
    return Generator(
        file, llm, lambda: "a man whose role is Boss", lambda: ["Primes"], timeout_s
    ), file


def test_the_first_draft_runs_once_in_the_background_and_is_saved(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    llm = DraftLlm()
    g, file = generator(tmp_path, llm)
    with caplog.at_level(logging.INFO, logger="imageskin.customization_draft"):
        g.needed()
        g.needed()  # already running
        g.wait(5)
    assert len(llm.sent) == 1 and "Boss" in llm.sent[0][-1]["content"]
    assert file.read().customization.identity.name == "Ada"
    assert (tmp_path / GENERATED_FILE).exists()
    logged = next(r for r in caplog.records if r.message == "Customization generated")
    assert logged.features == len(FEATURES) and logged.duration_ms >= 0  # type: ignore[attr-defined]
    # It runs once, even after a restart, and never once a customization was saved.
    (tmp_path / "customization.json").unlink()
    again, _ = generator(tmp_path, llm)
    again.needed()
    again.wait(5)
    assert len(llm.sent) == 1


def test_it_doesnt_run_once_something_was_saved(tmp_path: Path) -> None:
    llm = DraftLlm()
    g, file = generator(tmp_path, llm)
    file.change(lambda c: with_goals(c, ["Mine."]))
    g.needed()
    g.wait(5)
    assert llm.sent == [] and file.read().customization.goals == ("Mine.",)


def test_a_save_made_while_it_runs_drops_its_result(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    llm = DraftLlm()
    llm.release = threading.Event()
    g, file = generator(tmp_path, llm)
    with caplog.at_level(logging.INFO, logger="imageskin.customization_draft"):
        g.needed()
        file.change(lambda c: with_goals(c, ["Mine."]))
        llm.release.set()
        g.wait(5)
    assert file.read().customization.goals == ("Mine.",)
    assert file.read().customization.identity.name == ""
    assert "Customization generation dropped" in caplog.text
    assert (tmp_path / GENERATED_FILE).exists()


def test_a_failed_draft_keeps_the_shipped_defaults(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    stalled = threading.Event()

    def stall(messages: list[Message], schema: dict[str, Any]) -> str:
        stalled.wait(5)
        return "{}"

    g, file = generator(tmp_path, stall, timeout_s=0.2)
    with caplog.at_level(logging.INFO, logger="imageskin.customization_draft"):
        g.needed()
        g.wait(5)
    stalled.set()
    read = file.read()
    assert read.shipped and read.customization == SHIPPED
    failed = next(r for r in caplog.records if r.message == "Customization generation failed")
    assert failed.reason == "no reply within 0.2 s"  # type: ignore[attr-defined]
    assert failed.duration_ms >= 200  # type: ignore[attr-defined]
    assert (tmp_path / GENERATED_FILE).exists()


def test_unreadable_inputs_draft_from_what_is_left(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def broken() -> str | None:
        raise OSError("disk gone")

    llm = DraftLlm()
    g = Generator(CustomizationFile(tmp_path), llm, broken, lambda: [])
    with caplog.at_level(logging.ERROR, logger="imageskin.customization_draft"):
        draft, _, _ = g.again()
    assert draft.identity.name == "Ada"
    assert "a person whose name and role weren't given" in llm.sent[0][-1]["content"]
    assert "Could not read what the customization is drafted from" in caplog.text


def test_generate_again_makes_a_draft_without_saving_it(tmp_path: Path) -> None:
    llm = DraftLlm(name="Grace")
    g, file = generator(tmp_path, llm)
    file.change(lambda c: with_guidelines(c, "teach me", EDITED))
    draft, keys, _ = g.again()
    assert draft.identity.name == "Grace" and "teach me" not in keys
    assert guidelines_of(draft, "teach me") == EDITED
    assert file.read().customization.identity.name == ""  # not saved


def test_who_are_you_is_answered_at_once_then_from_the_draft(tmp_path: Path) -> None:
    llm = DraftLlm()
    llm.release = threading.Event()
    client: Any = riemann_app(tmp_path, llm, generate_customization=True)
    first = chat(client, "Who are you?")
    assert "Ada" not in first["content"]  # the shipped answer, without waiting
    llm.release.set()
    client.app.state.customization_generator.wait(5)
    second = chat(client, "Who are you?")
    assert second["content"].startswith("I'm Ada.")
    asked = next(m[-1]["content"] for m in llm.sent if "AI tutor" in m[-1]["content"])
    assert "Zeta Function Integral" in asked  # the content's topics


def test_the_host_generates_again_and_saves_or_discards_the_draft(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    llm = DraftLlm(name="Grace")
    client: Any = riemann_app(tmp_path, llm)
    client.put("/api/customization/guidelines/teach%20me", json={"text": EDITED})
    with caplog.at_level(logging.INFO):
        made = client.post("/api/customization/draft")
        assert made.status_code == 200
        body = made.json()
        assert body["draft"]["identity"]["name"] == "Grace" and "teach me" not in body["drafted"]
        assert client.get("/api/customization").json()["identity"]["name"] == ""
        assert client.post("/api/customization/draft/discard").json() == {"discarded": True}
        draft = body["draft"]
        guidelines = {k: draft["guidelines"][k] for k in body["drafted"]}
        saved = client.put("/api/customization/draft", json=to_save(body, guidelines))
    assert saved.status_code == 200
    now = client.get("/api/customization").json()
    assert now["identity"]["name"] == "Grace"
    assert now["guidelines"]["teach me"] == EDITED
    assert now["guidelines"]["questions"] == "Drafted for questions."
    assert "questions" in now["generated"] and "teach me" not in now["generated"]
    assert "Customization draft discarded" in caplog.text
    saves = [r for r in caplog.records if r.message == "Customization saved"]
    assert saves[-1].part == "draft"  # type: ignore[attr-defined]
    assert TEACHING != EDITED


def to_save(body: dict[str, Any], guidelines: dict[str, Any]) -> dict[str, Any]:
    """What the page sends to save a draft from Generate again."""
    draft = body["draft"]
    return {
        "identity": draft["identity"],
        "goals": draft["goals"],
        "guidelines": guidelines,
        "based_on": body["based_on"],
    }


def test_a_draft_older_than_a_save_isnt_saved_over_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Codex's review on PR #255: a draft made, then a host edit saved (in another tab, or while
    the draft was written), then the draft saved, would have undone the edit."""
    client: Any = riemann_app(tmp_path, DraftLlm(name="Grace"))
    body = client.post("/api/customization/draft").json()
    edit = client.put("/api/customization/goals", json={"goals": ["Mine, saved since."]})
    assert edit.status_code == 200
    guidelines = {k: body["draft"]["guidelines"][k] for k in body["drafted"]}
    with caplog.at_level(logging.WARNING, logger="imageskin.app"):
        stale = client.put("/api/customization/draft", json=to_save(body, guidelines))
    assert stale.status_code == 409
    assert stale.json()["detail"] == (
        "Something was saved since this draft was made. Generate again to redraft."
    )
    now = client.get("/api/customization").json()
    assert now["goals"] == ["Mine, saved since."] and now["identity"]["name"] == ""
    assert "Customization draft out of date" in caplog.text
    # Drafted again from it, it is saved.
    body = client.post("/api/customization/draft").json()
    guidelines = {k: body["draft"]["guidelines"][k] for k in body["drafted"]}
    saved = client.put("/api/customization/draft", json=to_save(body, guidelines))
    assert saved.status_code == 200 and saved.json()["identity"]["name"] == "Grace"


def test_a_draft_that_fails_says_so(tmp_path: Path) -> None:
    def broken(messages: list[Message], schema: dict[str, Any] | None = None) -> str:
        raise OSError("no server")

    client: Any = riemann_app(tmp_path, Llm())
    client.app.state.customization_generator._ask = broken
    failed = client.post("/api/customization/draft")
    assert failed.status_code == 502
    assert (
        failed.json()["detail"]
        == "A draft could not be made: the LLM failed: no server. Try again."
    )
    with patch.object(client.app.state.customization_generator, "again") as again:
        again.side_effect = GenerationFailed("no reply within 120 s")
        assert client.post("/api/customization/draft").status_code == 504


def test_drafted_guidelines_are_drafted_again_until_the_host_changes_them(tmp_path: Path) -> None:
    llm = DraftLlm()
    g, file = generator(tmp_path, llm)
    g.needed()
    g.wait(5)
    first = file.read().customization
    assert set(first.generated) == set(FEATURES)
    assert features(first)[0]["generated"] is True
    file.change(lambda c: with_guidelines(c, "teach me", EDITED))
    assert "teach me" not in file.read().customization.generated
    draft, keys, _ = g.again()
    assert keys == [k for k in FEATURES if k != "teach me"]
    assert guidelines_of(draft, "teach me") == EDITED
    # Kept in the file, so a restart knows which were drafted.
    saved = json.loads(file.path.read_text())
    assert "teach me" not in saved["generated"] and "questions" in saved["generated"]
    assert from_dict(saved).generated == file.read().customization.generated


def test_a_file_whose_drafted_list_is_broken_cant_be_read() -> None:
    with pytest.raises(CustomizationUnreadable, match="generated is not a list of text"):
        from_dict({"generated": "questions"})
    assert from_dict({}).generated == ()
