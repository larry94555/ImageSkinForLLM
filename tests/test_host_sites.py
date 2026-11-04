"""Several sites for one host: the server (roadmap R256, item 208). A host's record names a list
of sites; one sign-in is good on each of them, and only on theirs; the site used last is the one
a sign-in elsewhere goes to (R255)."""

import json
import logging
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_acting_as_host import administrator, link_for, opened
from test_disabled_host import signed_in
from test_email_change import emails, link_in
from test_site_addresses import PASSWORD, served

from imageskin import admin, cli
from imageskin.host_disk import Owners
from imageskin.hosts import (
    DEFAULT_SITE,
    HOST_COOKIE,
    NO_SITE,
    SITE,
    SITES,
    HostAccounts,
    sites_in,
)
from imageskin.sites import SiteError, site_home

pytestmark = pytest.mark.real_hosts

ANN, BOB = "ann@example.com", "bob@example.com"
SITE_A, SITE_B, SITE_C = "http://a.localhost", "http://b.localhost", "http://c.localhost"


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = admin.Secret("hash", admin.hash_password("nobody's password"))
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


def two_sites(tmp_path: Path, bob_too: bool = True):  # type: ignore[no-untyped-def]
    """Ann with sites a and b, and Bob with site c, or the main address's."""
    sites, made, service = served(tmp_path)
    service.sites.add("b", ANN)
    if bob_too:
        service.sites.add("c", BOB)
    return sites, made, service


def session(browser: TestClient) -> dict[str, object]:
    return dict(browser.get("/api/host/session").json())


def test_a_host_from_before_has_a_list_of_their_one_site() -> None:
    assert sites_in({}) == [DEFAULT_SITE]
    assert sites_in({SITE: "a"}) == ["a"]
    assert sites_in({SITE: "b", SITES: ["a", "b"]}) == ["a", "b"]
    assert sites_in({SITE: "b", SITES: ["a"]}) == ["b", "a"]  # their site is always in it
    assert sites_in({SITE: NO_SITE, SITES: ["a"]}) == []  # deleted (R69a)
    assert sites_in({SITE: "a", SITES: ["a", 3, NO_SITE]}) == ["a"]  # a hand-edited file


def test_a_host_is_given_a_second_site_and_their_sign_in_works_on_both(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        sites, _, service = two_sites(tmp_path)
    assert "Host site added" in caplog.messages
    accounts = service.host_accounts
    assert accounts.sites_of(ANN) == ["a", "b"] and accounts.site_of(ANN) == "a"
    assert service.sites.host("b") == ANN
    saved = json.loads((tmp_path / "home" / "hosts.json").read_text())["hosts"][ANN]
    assert (saved[SITE], saved[SITES]) == ("a", ["a", "b"])

    ann_a = signed_in(sites, SITE_A, ANN)
    listed = ann_a.get("/api/host/sites").json()["sites"]
    assert listed == [
        {"site": "a", "address": "http://a.localhost", "here": True},
        {"site": "b", "address": "http://b.localhost", "here": False},
    ]
    with caplog.at_level(logging.INFO):
        go = ann_a.post("/api/host/sites/b/open")
    assert go.status_code == 200, go.text
    assert go.json()["go_to"].startswith("http://b.localhost/api/host/sign-in/")
    assert "Host site opened" in caplog.messages
    ann_b = opened(sites, go.json()["go_to"])
    assert session(ann_b)["signed_in"] is True and session(ann_b)["email"] == ANN
    # Still signed in on the first, with the same account.
    assert session(ann_a)["signed_in"] is True
    # The site opened last is the one a sign-in elsewhere goes to (R255).
    assert accounts.site_of(ANN) == "b" and accounts.sites_of(ANN) == ["b", "a"]
    main = TestClient(sites, base_url="http://localhost")
    sent = main.post("/api/host/sign-in", json={"email": ANN, "password": PASSWORD}).json()
    assert sent["site"] == "b" and sent["sign_in_at"].startswith(f"{SITE_B}/api/host/sign-in/")
    # Signing in at a makes it the one used last again.
    signed_in(sites, SITE_A, ANN)
    assert accounts.site_of(ANN) == "a"


def test_another_hosts_site_still_refuses_them(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, _ = two_sites(tmp_path)
    ann_a = signed_in(sites, SITE_A, ANN)
    with caplog.at_level(logging.INFO):
        refused = ann_a.post("/api/host/sites/c/open")
    assert refused.status_code == 404
    assert refused.json()["detail"] == "That isn't one of your sites."
    assert "Host site not opened" in caplog.messages
    # Ann's own cookie, sent to Bob's site by hand, counts as no sign-in.
    token = ann_a.cookies.get(HOST_COOKIE)
    assert token
    by_hand = TestClient(sites, base_url=SITE_C, cookies={HOST_COOKIE: token})
    assert session(by_hand)["signed_in"] is False
    # A sign-in at Bob's site goes to Ann's own, not into Bob's.
    at_c = TestClient(sites, base_url=SITE_C)
    sent = at_c.post("/api/host/sign-in", json={"email": ANN, "password": PASSWORD}).json()
    assert sent["signed_in"] is False and sent["site"] == "a"
    # And Bob's sign-in isn't good on Ann's sites.
    bob_c = signed_in(sites, SITE_C, BOB)
    assert bob_c.post("/api/host/sites/a/open").status_code == 404
    assert bob_c.get("/api/host/sites").json()["sites"] == [
        {"site": "c", "address": "http://c.localhost", "here": True}
    ]


def test_a_second_site_is_never_a_free_trial(tmp_path: Path) -> None:
    _, _, service = two_sites(tmp_path)
    with pytest.raises(SiteError, match="already the host of a"):
        service.sites.add_trial(ANN)
    assert service.host_accounts.sites_of(ANN) == ["a", "b"]


def test_deleting_one_of_their_sites_keeps_the_others(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, service = two_sites(tmp_path)
    accounts = service.host_accounts
    signed_in(sites, SITE_B, ANN)  # b is the one used last
    ann_a = signed_in(sites, SITE_A, ANN)
    signed_in(sites, SITE_B, ANN)
    with caplog.at_level(logging.INFO):
        assert service.sites.delete("b", "test")
    assert "Host site removed" in caplog.messages
    assert accounts.sites_of(ANN) == ["a"] and accounts.site_of(ANN) == "a"
    assert accounts.deleted_site(ANN) is None
    assert session(ann_a)["signed_in"] is True  # their sign-ins stay good on the others
    # Their last one goes as R69a says: the account is kept with no site.
    assert service.sites.delete("a", "test")
    assert accounts.site_of(ANN) == NO_SITE and accounts.sites_of(ANN) == []
    assert (accounts.deleted_site(ANN) or {})["subdomain"] == "a"


def test_a_host_who_has_only_the_main_address_is_given_the_site_in_its_place(
    tmp_path: Path,
) -> None:
    accounts = HostAccounts(tmp_path)
    accounts.sign_up(ANN, PASSWORD, "test")
    assert accounts.add_site(ANN, "a") and accounts.sites_of(ANN) == ["a"]
    assert accounts.add_site(ANN, "b") and accounts.add_site(ANN, "b")  # twice is once
    assert accounts.sites_of(ANN) == ["a", "b"]
    assert not accounts.add_site("nobody@example.com", "c")
    assert not accounts.remove_site(ANN, "c")  # not theirs
    assert accounts.remove_site(ANN, "a") and accounts.sites_of(ANN) == ["b"]
    assert not accounts.remove_site(ANN, "b")  # their only one: deleted as R69a says
    assert accounts.set_site(ANN, "d") and accounts.sites_of(ANN) == ["d"]


def test_the_administrator_sees_each_hosts_sites_and_acts_on_all_of_them(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # The administrator signs in at the main address as its host, Bob (R191).
    sites, _, service = two_sites(tmp_path, bob_too=False)
    boss = administrator(sites, tmp_path)
    listed = boss.get("/api/admin/hosts").json()
    assert listed["sites"] == {ANN: ["a", "b"], BOB: ["main address"]}
    # Acting as Ann starts on the site she used last, and goes on to her other one.
    acting_a = opened(sites, link_for(boss))
    assert session(acting_a)["acting_as_admin"] is True
    with caplog.at_level(logging.INFO):
        go = acting_a.post("/api/host/sites/b/open")
    assert go.status_code == 200, go.text
    assert go.json()["go_to"].startswith("http://b.localhost:8000/api/host/act-as/")
    acting_b = opened(sites, go.json()["go_to"])
    assert session(acting_b)["acting_as_admin"] is True and session(acting_b)["email"] == ANN
    assert session(acting_a)["acting_as_admin"] is True  # both, as Ann's sites are
    # Acting never made Ann a sign-in of her own, nor changed the site she used last.
    assert service.host_accounts.site_of(ANN) == "a"
    # A disabled host still opens each of their sites, read-only on both (R44c).
    service.host_accounts.set_disabled(ANN, True)
    ann_a = signed_in(sites, SITE_A, ANN)
    assert ann_a.post("/api/host/sites/b/open").status_code == 200


def test_a_new_email_moves_every_site_of_theirs(tmp_path: Path) -> None:
    sites, _, service = two_sites(tmp_path)
    home = tmp_path / "home"
    new = "ann.new@example.com"
    Owners(site_home("a", home)).record("photos", "p1", ANN)
    Owners(site_home("b", home)).record("pdfs", "d1", ANN)
    ann_b = signed_in(sites, SITE_B, ANN)
    asked = ann_b.post("/api/host/email", json={"new_email": new, "password": PASSWORD})
    assert asked.status_code == 200, asked.text
    link = link_in(emails(home)[-1]["text"])
    assert link.startswith(f"{SITE_B}/api/host/email/confirm/")
    changed = ann_b.get(link, follow_redirects=False)
    assert changed.headers["location"] == "/#/host/email-changed"
    accounts = service.host_accounts
    assert accounts.sites_of(new) == ["b", "a"] and accounts.sites_of(ANN) == []
    assert (service.sites.host("a"), service.sites.host("b")) == (new, new)
    assert Owners(site_home("a", home)).read() == {"photos": {"p1": new}}
    assert Owners(site_home("b", home)).read() == {"pdfs": {"d1": new}}


def test_a_new_email_is_put_back_on_every_site_when_the_account_cant_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sites, _, service = two_sites(tmp_path)
    home = tmp_path / "home"
    Owners(site_home("a", home)).record("photos", "p1", ANN)
    ann_b = signed_in(sites, SITE_B, ANN)
    ann_b.post("/api/host/email", json={"new_email": "x@example.com", "password": PASSWORD})
    link = link_in(emails(home)[-1]["text"])
    monkeypatch.setattr(type(service.host_accounts), "change_email", lambda self, token: None)
    failed = ann_b.get(link, follow_redirects=False)
    assert failed.headers["location"] == "/#/host/email-failed"
    assert (service.sites.host("a"), service.sites.host("b")) == (ANN, ANN)
    assert Owners(site_home("a", home)).read() == {"photos": {"p1": ANN}}


def test_the_command_line_gives_a_host_another_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("IMAGESKIN_HOME", str(tmp_path))
    accounts = HostAccounts(tmp_path)
    accounts.sign_up(ANN, PASSWORD, "test")
    assert cli.main(["site", "add", "a", "--host", ANN]) == 0
    assert "now signs in there" in capsys.readouterr().out
    assert cli.main(["site", "add", "b", "--host", ANN]) == 0
    said = capsys.readouterr().out
    assert re.search(r"now has 2 sites, a, b, and signs in once for all of them", said)
    assert accounts.sites_of(ANN) == ["a", "b"]
