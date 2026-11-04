"""The page for a site a participant may not use (roadmap R262, item 212): a signed-in participant
the host's policy (R261) doesn't let open a site is told only that it is not yet active, and the
site's calls refuse them with 403, naming neither the host nor anything of the site."""

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_host_content import ANN, Served, quick_hashes
from test_site_addresses import PASSWORD as HOST_PASSWORD

from imageskin.app import NOT_ACTIVE_WORDS
from imageskin.participant_policy import FILENAME

pytestmark = pytest.mark.real_hosts
__all__ = ["quick_hashes"]  # the fixture, used by name

PAT, SAM, PASSWORD = "pat@example.com", "sam@example.com", "a long secret"
A, B = "http://a.me0.ai", "http://b.me0.ai"
# What a site's pages ask for, each of which would say something of the host or the site.
SITE_CALLS = [
    ("GET", "/api/host/session"),
    ("GET", "/api/settings"),
    ("GET", "/api/consent"),
    ("GET", "/api/chat"),
    ("POST", "/api/chat"),
    ("GET", "/api/participant/progress"),
    ("GET", "/api/content"),
]


def signed_up(s: Served, email: str) -> TestClient:
    browser = TestClient(s.apps, base_url=A)
    answer = browser.post("/api/participant/sign-up", json={"email": email, "password": PASSWORD})
    assert answer.status_code == 200, answer.text
    return browser


def only_b_for_pat(s: Served) -> None:
    policy = {"every": {"sites": None}, "participants": {PAT: {"sites": ["b"], "landing": "b"}}}
    assert s.host(A, ANN).put("/api/host/participant-policy", json=policy).status_code == 200


def test_a_participant_not_allowed_here_is_told_only_that_it_is_not_active(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    s = Served(tmp_path)
    pat, sam = signed_up(s, PAT), signed_up(s, SAM)
    only_b_for_pat(s)
    assert pat.get(f"{A}/api/participant/session").json() == {
        "signed_in": True,
        "email": PAT,
        "allowed": False,
    }
    with caplog.at_level(logging.WARNING):
        for method, path in SITE_CALLS:
            answer = pat.request(method, f"{A}{path}", json={"prompt": "hi"})
            assert answer.status_code == 403, path
            assert answer.json() == {"detail": NOT_ACTIVE_WORDS}, path
            # Nothing of the host or the site: not her name, email or the site's.
            assert "ann" not in answer.text.lower() and "a.me0" not in answer.text
    refused = [r for r in caplog.records if r.getMessage() == "Participant not allowed here"]
    assert len(refused) == len(SITE_CALLS)
    assert {getattr(r, "path", None) for r in refused} == {p for _, p in SITE_CALLS}
    # On b, which Pat may open, nothing is refused; Sam, with every site, is refused nowhere.
    assert "allowed" not in pat.get(f"{B}/api/participant/session").json()
    assert pat.get(f"{B}/api/settings").status_code == 200
    assert sam.get(f"{A}/api/settings").status_code == 200
    assert "allowed" not in sam.get(f"{A}/api/participant/session").json()
    # Signing out still works, and then they are an anonymous visitor here again.
    assert pat.post(f"{A}/api/participant/sign-out").status_code == 200
    assert pat.get(f"{A}/api/settings").status_code == 200


def test_the_host_signed_in_on_that_browser_is_never_refused(tmp_path: Path) -> None:
    s = Served(tmp_path)
    signed_up(s, PAT)
    only_b_for_pat(s)
    ann = s.host(A, ANN)
    ann.post("/api/participant/sign-in", json={"email": PAT, "password": PASSWORD})
    assert ann.get("/api/host/session").status_code == 200
    assert "allowed" not in ann.get("/api/participant/session").json()
    # Signing in as the host on a participant's browser is open too.
    pat = TestClient(s.apps, base_url=A)
    pat.post("/api/participant/sign-in", json={"email": PAT, "password": PASSWORD})
    assert pat.get("/api/settings").status_code == 403
    signed = pat.post("/api/host/sign-in", json={"email": ANN, "password": HOST_PASSWORD})
    assert signed.status_code == 200, signed.text
    assert pat.get("/api/settings").status_code == 200


def test_a_policy_that_cant_be_read_refuses_no_one(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    s = Served(tmp_path)
    pat = signed_up(s, PAT)
    only_b_for_pat(s)
    (s.library(ANN) / FILENAME).write_text("{broken")
    with caplog.at_level(logging.ERROR):
        assert pat.get(f"{A}/api/settings").status_code == 200
    assert "Could not read the participant policy" in caplog.text
    (s.library(ANN) / FILENAME).write_text(json.dumps({"every": {"sites": None}}))
    assert pat.get(f"{A}/api/settings").status_code == 200
