"""Starting a deleted site again (roadmap R69c, feature 213): a host whose site was deleted still
signs in, and Start my site again makes them a new, empty site, at its old subdomain if still
free, paused until Resume subscription pays for it with the card Stripe keeps (R69b)."""

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_resuming import FakeStripe, paused
from test_site_addresses import PASSWORD
from test_subscribing import (  # noqa: F401 (the fixture)
    DAN,
    MAIN,
    SECRET,
    a_trial,
    quick_hashes,
    served,
)

from imageskin.hosts import DELETED, NO_SITE, site_deleted_words
from imageskin.payments import Stripe
from imageskin.sites import RESTARTED, SiteError, site_home

pytestmark = pytest.mark.real_hosts


def deleted(tmp_path: Path, subdomain: str | None = "dans"):  # type: ignore[no-untyped-def]
    """Dan's paid site, at the subdomain picked, paused and then deleted (R69a)."""
    fake, sites, service, dan, site, code = paused(tmp_path, subdomain=subdomain)
    assert service.sites.delete(code, "test")
    return fake, sites, service


def sign_in(browser: TestClient) -> object:
    return browser.post("/api/host/sign-in", json={"email": DAN, "password": PASSWORD})


def test_a_deleted_sites_host_starts_it_again_at_its_old_subdomain(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fake, sites, service = deleted(tmp_path)
    # What the site was is kept with the host's account.
    assert service.host_accounts.deleted_site(DAN) == {
        "subdomain": "dans",
        "customer": "cus_1",
        "subscription": "sub_1",
    }
    main = TestClient(sites, base_url=MAIN)
    refused = main.post("/api/host/sign-in", json={"email": DAN, "password": PASSWORD})
    assert refused.status_code == 401
    assert refused.json() == {"detail": site_deleted_words(), "deleted": True}
    assert refused.json()["detail"] == (
        "Your site was paused for 30 days, so its content was deleted. You can start a new, "
        "empty site at the same address if it is still free."
    )
    # The days are the admin settings' (Larry, on PR #302).
    service.admin_settings.change({"days_before_deleting": 7})
    assert "paused for 7 days" in sign_in(main).json()["detail"]  # type: ignore[attr-defined]

    with caplog.at_level(logging.INFO):
        started = main.post("/api/host/restart", json={"email": DAN, "password": PASSWORD})
    assert started.status_code == 200 and started.json()["site"] == "dans"
    assert any(r.message == "Site started again" for r in caplog.records)
    # Empty, paused until paid for, with the deleted site's customer for Resume subscription.
    assert service.sites.paused("dans") == RESTARTED
    assert not (site_home("dans", service.home) / "person.txt").exists()
    assert service.sites.subscription("dans") == {
        "id": "sub_1",
        "customer": "cus_1",
        "status": "canceled",
    }
    assert service.host_accounts.site_of(DAN) == "dans"
    assert service.host_accounts.deleted_site(DAN) is None

    # The link signs Dan in at the new site, where Resume subscription brings it live.
    link = started.json()["sign_in_at"]
    assert link.startswith("http://dans.localhost:8000/api/host/sign-in/")
    there = TestClient(sites, base_url="http://dans.localhost:8000")
    assert there.get(link.removeprefix("http://dans.localhost:8000"), follow_redirects=False)
    assert there.get("/api/host/session").json()["paused"] is True
    shown = there.get("/api/site/subscription").json()
    assert shown["resumable"] is True and shown["restarted"] is True
    assert there.post("/api/site/subscription/resume").json() == {"resumed": True}
    assert fake.posted[-1][1]["customer"] == "cus_1"
    assert fake.posted[-1][1]["default_payment_method"] == "pm_card"
    assert service.sites.paused("dans") is None and service.sites.subscribed("dans")


def test_a_taken_subdomain_gives_a_new_random_one(tmp_path: Path) -> None:
    fake, sites, service = deleted(tmp_path)
    service.host_accounts.sign_up("eve@example.com", PASSWORD, "127.0.0.1")
    service.sites.add("dans", "eve@example.com")
    main = TestClient(sites, base_url=MAIN)
    started = main.post("/api/host/restart", json={"email": DAN, "password": PASSWORD})
    name = started.json()["site"]
    assert name != "dans" and len(name) == 12 and service.sites.paused(name) == RESTARTED
    assert service.sites.subdomain(name) == name  # which Dan can change (R64)


def test_a_deleted_trial_never_paid_for_subscribes_on_stripes_page(tmp_path: Path) -> None:
    fake = FakeStripe()
    stripe = Stripe("sk_test", SECRET, "price_5gb", fake.post, delete=fake.delete, get=fake.get)
    sites, _, service = served(tmp_path, stripe)
    dan, site = a_trial(sites, tmp_path / "home")
    code = site.removeprefix("/t/")
    assert service.sites.delete(code, "test")
    assert service.host_accounts.deleted_site(DAN) == {
        "subdomain": None,
        "customer": None,
        "subscription": None,
    }
    main = TestClient(sites, base_url=MAIN)
    name = main.post("/api/host/restart", json={"email": DAN, "password": PASSWORD}).json()["site"]
    assert name != code and service.sites.subscription(name) is None
    assert service.sites.paused(name) == RESTARTED


def test_start_again_is_refused_where_it_doesnt_fit(tmp_path: Path) -> None:
    fake, sites, service = deleted(tmp_path)
    main = TestClient(sites, base_url=MAIN)
    wrong = main.post("/api/host/restart", json={"email": DAN, "password": "not it at all"})
    assert wrong.status_code == 401 and service.host_accounts.site_of(DAN) == NO_SITE
    assert main.post("/api/host/restart", json={"email": DAN, "password": PASSWORD}).is_success
    # Started once: a second time, the host has a site again.
    again = main.post("/api/host/restart", json={"email": DAN, "password": PASSWORD})
    assert again.status_code == 409
    with pytest.raises(SiteError):
        service.sites.restart(DAN)


def test_a_restart_that_fails_says_so(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake, sites, service = deleted(tmp_path)

    def broken(email: str) -> str:
        raise OSError("disk full")

    monkeypatch.setattr(service.sites, "restart", broken)
    main = TestClient(sites, base_url=MAIN)
    # The router was made with the real one; a fresh app picks up the broken one.
    sites.forget("default")
    answer = main.post("/api/host/restart", json={"email": DAN, "password": PASSWORD})
    assert answer.status_code == 503
    assert service.host_accounts.site_of(DAN) == NO_SITE


def test_a_new_site_of_their_own_drops_what_the_deleted_one_was(tmp_path: Path) -> None:
    fake, sites, service = deleted(tmp_path)
    service.host_accounts.set_site(DAN, "anything")
    assert service.host_accounts.deleted_site(DAN) is None
    hosts = service.host_accounts._load()["hosts"]  # noqa: SLF001
    assert DELETED not in hosts[DAN]


def test_a_host_whose_site_was_deleted_breaks_nothing_else(tmp_path: Path) -> None:
    """Startup's move of hosts to their own sites, the administrator's Act as this host and a
    host's disk space all leave a host with no site alone (R69a)."""
    from test_acting_as_host import administrator
    from test_site_addresses import served as served_plain

    from imageskin.site_moves import move_hosts_to_sites

    apps, _, service = served_plain(tmp_path)
    boss = administrator(apps, tmp_path)
    assert service.sites.delete("a", "test")
    assert service.host_accounts.site_of("ann@example.com") == NO_SITE
    assert move_hosts_to_sites(service.home, service.host_accounts, service.sites) == []
    assert service.host_accounts.site_of("ann@example.com") == NO_SITE
    acting = boss.post("/api/admin/act-as", json={"email": "ann@example.com"})
    assert acting.status_code == 409
    disk = boss.get("/api/host/disk", params={"email": "ann@example.com"})
    assert disk.status_code == 404 and disk.json()["detail"] == "This host's site was deleted."


def test_a_sites_file_that_cant_be_written_starts_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The new site is added paused, with its customer, in one write: when it fails, nothing is
    added and the host keeps what the deleted site was (Codex's review of PR #302)."""
    fake, sites, service = deleted(tmp_path)

    def full(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    real = service.sites._write  # noqa: SLF001
    monkeypatch.setattr(service.sites, "_write", full)
    with pytest.raises(OSError):
        service.sites.restart(DAN)
    assert "dans" not in service.sites.names()
    assert service.host_accounts.site_of(DAN) == NO_SITE
    assert service.host_accounts.deleted_site(DAN) is not None
    monkeypatch.setattr(service.sites, "_write", real)
    assert service.sites.restart(DAN) == "dans"
    assert service.sites.subscription("dans")["customer"] == "cus_1"


def test_a_restart_stopped_between_the_two_files_is_finished_never_made_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The server stopped after sites.json had the new site and before the host's account was
    given it: the site was never served unpaid, and starting again finishes that one."""
    fake, sites, service = deleted(tmp_path)
    real = service.host_accounts.set_site

    def stopped(email: str, site: str) -> bool:
        raise OSError("the server stopped")

    monkeypatch.setattr(service.host_accounts, "set_site", stopped)
    with pytest.raises(OSError):
        service.sites.restart(DAN)
    # Added paused, with the deleted site's customer: visitors see it paused.
    assert service.sites.paused("dans") == RESTARTED
    assert service.sites.subscription("dans")["customer"] == "cus_1"
    assert service.host_accounts.deleted_site(DAN) is not None
    monkeypatch.setattr(service.host_accounts, "set_site", real)
    main = TestClient(sites, base_url=MAIN)
    started = main.post("/api/host/restart", json={"email": DAN, "password": PASSWORD})
    assert started.json()["site"] == "dans" and service.sites.names().count("dans") == 1
    assert len([n for n in service.sites.names() if service.sites.host(n) == DAN]) == 1
    assert service.host_accounts.site_of(DAN) == "dans"
