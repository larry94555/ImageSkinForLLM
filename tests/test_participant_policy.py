"""Where each participant may go (roadmap R261, item 211): the host's policy for every
participant, and for any one in its place, of which sites they may open and the site a sign-in
sends them to."""

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_host_content import ANN, BOB, Served, quick_hashes

from imageskin.participant_policy import (
    FILENAME,
    LANDING_NOT_ALLOWED,
    NONE_ALLOWED,
    NOT_A_PARTICIPANT,
    NOT_YOUR_SITE,
    Rule,
    allowed_sites,
    landing_site,
)

pytestmark = pytest.mark.real_hosts
__all__ = ["quick_hashes"]  # the fixture, used by name

PAT, SAM, PASSWORD = "pat@example.com", "sam@example.com", "a long secret"
A, B, C = "http://a.me0.ai", "http://b.me0.ai", "http://c.me0.ai"
POLICY = "/api/host/participant-policy"


def sign_in(s: Served, address: str, email: str = PAT) -> dict[str, object]:
    browser = TestClient(s.apps, base_url=address)
    answer = browser.post("/api/participant/sign-in", json={"email": email, "password": PASSWORD})
    assert answer.status_code == 200, answer.text
    found: dict[str, object] = answer.json()
    return found


def with_participants(tmp_path: Path) -> Served:
    s = Served(tmp_path)
    for email in (PAT, SAM):
        browser = TestClient(s.apps, base_url=A)
        assert browser.post(
            "/api/participant/sign-up", json={"email": email, "password": PASSWORD}
        ).is_success
    return s


def test_until_the_host_sets_one_every_site_is_open_and_they_go_to_the_first(
    tmp_path: Path,
) -> None:
    s = with_participants(tmp_path)
    assert "go_to" not in sign_in(s, A)  # already on Ann's first site
    assert sign_in(s, B)["go_to"] == f"{A}/"
    ann = s.host(A, ANN)
    answer = ann.get(POLICY).json()
    assert answer == {
        "sites": [{"site": "a", "address": A}, {"site": "b", "address": B}],
        "participants": [PAT, SAM],
        "policy": {
            "every": {"sites": None, "landing": None},
            "participants": {},
        },
    }


def test_the_policy_sends_each_participant_to_their_site(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    s = with_participants(tmp_path)
    ann = s.host(A, ANN)
    policy = {
        "every": {"sites": ["b"], "landing": "b"},
        "participants": {SAM: {"sites": ["a", "b"], "landing": "a"}},
    }
    with caplog.at_level(logging.INFO):
        saved = ann.put(POLICY, json=policy)
    assert saved.status_code == 200, saved.text
    assert saved.json()["policy"] == policy
    assert "Participant policy changed" in caplog.text
    kept = json.loads((s.library(ANN) / FILENAME).read_text())
    assert kept["every"] == {"sites": ["b"], "landing": "b"}
    # Pat is only allowed b, so is sent there from a; Sam's own rule sends Sam to a.
    with caplog.at_level(logging.INFO):
        assert sign_in(s, A)["go_to"] == f"{B}/"
    assert "Participant sent to their site" in caplog.text
    assert "go_to" not in sign_in(s, B)
    assert "go_to" not in sign_in(s, A, SAM)
    assert sign_in(s, B, SAM)["go_to"] == f"{A}/"
    # A change applies at the next sign-in.
    policy["every"] = {"sites": None, "landing": "a"}
    assert ann.put(POLICY, json=policy).status_code == 200
    assert "go_to" not in sign_in(s, A)
    assert sign_in(s, B)["go_to"] == f"{A}/"


@pytest.mark.parametrize(
    ("policy", "says"),
    [
        ({"every": {"sites": [], "landing": None}}, NONE_ALLOWED),
        ({"every": {"sites": ["a"], "landing": "b"}}, LANDING_NOT_ALLOWED),
        ({"every": {"sites": ["c"], "landing": None}}, NOT_YOUR_SITE),
        ({"every": {"sites": None, "landing": "c"}}, NOT_YOUR_SITE),
        ({"participants": {"who@example.com": {"sites": None}}}, NOT_A_PARTICIPANT),
        ({"every": {"sites": "a"}}, "can't be kept"),
        ({"participants": ["x"]}, "can't be kept"),
    ],
)
def test_a_policy_that_cant_be_kept_says_why(
    tmp_path: Path, policy: dict[str, object], says: str
) -> None:
    s = with_participants(tmp_path)
    ann = s.host(A, ANN)
    refused = ann.put(POLICY, json=policy)
    assert refused.status_code == 400 and says in refused.json()["detail"]
    assert not (s.library(ANN) / FILENAME).exists()


def test_only_the_host_sees_and_sets_their_policy(tmp_path: Path) -> None:
    s = with_participants(tmp_path)
    stranger = TestClient(s.apps, base_url=A)
    assert stranger.get(POLICY).status_code == 401
    assert stranger.put(POLICY, json={}).status_code == 401
    # Bob's policy is his own: his sites, and none of Ann's participants.
    bob = s.host(C, BOB)
    assert bob.get(POLICY).json()["sites"] == [{"site": "c", "address": C}]
    assert bob.get(POLICY).json()["participants"] == []
    assert bob.put(POLICY, json={"every": {"sites": ["a"]}}).status_code == 400


def test_a_policy_that_cant_be_read_sends_no_one_anywhere(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    s = with_participants(tmp_path)
    (s.library(ANN) / FILENAME).write_text("{broken")
    with caplog.at_level(logging.ERROR):
        assert "go_to" not in sign_in(s, B)
    assert "Could not read the participant policy" in caplog.text
    assert s.host(A, ANN).get(POLICY).status_code == 503


def test_a_site_the_host_no_longer_has_never_counts() -> None:
    rule = Rule(("gone", "b"), "gone")
    assert allowed_sites(rule, ["a", "b"]) == ["b"]
    assert landing_site(rule, ["a", "b"]) == "b"
    assert landing_site(Rule(("gone",)), ["a", "b"]) is None
    assert landing_site(Rule(), []) is None
