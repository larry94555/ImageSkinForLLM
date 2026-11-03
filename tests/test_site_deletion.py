"""Deleting a site (roadmap R69a): never at once (Larry, 2026-11-03). Delete site in Settings,
with the host's password, cancels the subscription now and pauses the site; a paused site's
content is deleted after the admin settings' days, 30 to begin with. Then its folder goes, its
subdomain is free and a trial's code is never given again. The host's account is kept (R69b)."""

import io
import json
import logging
import secrets
import time
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_acting_as_host import administrator, link_for, opened
from test_site_addresses import PASSWORD
from test_site_addresses import served as served_plain
from test_subscribing import (  # noqa: F401 (the fixture)
    DAN,
    MAIN,
    SECRET,
    a_trial,
    completed,
    quick_hashes,
    send,
    served,
)

from imageskin.email_change import WRONG_PASSWORD
from imageskin.hosts import NO_SITE, SITE_DELETED
from imageskin.payments import UNAVAILABLE, PaymentError, Stripe, delete_request
from imageskin.site_deletion import PAUSED_TOO_LONG, delete_paused, keep_deleting_paused
from imageskin.sites import DELETING, SiteApps, site_home

pytestmark = pytest.mark.real_hosts

DAY = 24 * 60 * 60


class FakeStripe:
    """Stripe's API: a checkout, and a subscription cancelled at once by DELETE."""

    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.fail: Exception | None = None

    def post(self, url: str, form: dict[str, str], key: str) -> dict[str, Any]:
        return {"id": "cs_1", "url": "https://checkout.stripe.com/c/pay/cs_1"}

    def delete(self, url: str, key: str) -> dict[str, Any]:
        self.deleted.append(url)
        if self.fail is not None:
            raise self.fail
        return {"id": url.rsplit("/", 1)[1], "status": "canceled"}


def subscribed(tmp_path: Path, pay: bool = True):  # type: ignore[no-untyped-def]
    """Dan's trial site, subscribed when `pay`, with something in its folder."""
    fake = FakeStripe()
    stripe = Stripe("sk_test", SECRET, "price_5gb", fake.post, delete=fake.delete)
    sites, _, service = served(tmp_path, stripe)
    dan, site = a_trial(sites, tmp_path / "home")
    code = site.removeprefix("/t/")
    if pay:
        assert send(TestClient(sites, base_url=MAIN), completed(code, "sub_1")).is_success
    (site_home(code, service.home) / "person.txt").write_text("Dan's person", encoding="utf-8")
    return fake, sites, service, dan, site, code


def test_the_host_deletes_their_site_with_their_password(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fake, sites, service, dan, site, code = subscribed(tmp_path)
    service.sites.pick_subdomain(code, "dans")
    folder = site_home(code, service.home)
    # The trial path has moved to the subdomain, so the host is there.
    browser = TestClient(sites, base_url="http://dans.localhost:8000")
    link = service.host_accounts.sign_in_link(DAN)
    assert browser.get(f"/api/host/sign-in/{link}", follow_redirects=False).status_code == 303
    wrong = browser.post("/api/site/delete", json={"password": "not it"})
    assert wrong.status_code == 401 and wrong.json()["detail"] == WRONG_PASSWORD
    assert folder.exists() and fake.deleted == []

    with caplog.at_level(logging.INFO):
        asked = browser.post("/api/site/delete", json={"password": PASSWORD})
    # Nothing is deleted yet: the subscription is cancelled now, and the site paused for 30
    # days, while its host still signs in and can come back.
    paused_at = service.sites.paused_at(code)
    assert paused_at is not None
    assert asked.status_code == 200
    assert asked.json() == {"paused": True, "deletes_at": paused_at + 30 * DAY}
    assert fake.deleted == ["https://api.stripe.com/v1/subscriptions/sub_1"]
    assert any(r.message == "Site deletion asked" for r in caplog.records)
    assert folder.exists() and service.sites.paused(code) == DELETING
    shown = browser.get("/api/site/subscription").json()
    assert shown["deletes_at"] == paused_at + 30 * DAY and shown["days_before_deleting"] == 30
    visitor = TestClient(sites, base_url="http://dans.localhost:8000")
    assert visitor.post("/api/chat/prompt", json={}).status_code == 403
    # Asking again doesn't put the deletion off.
    browser.post("/api/site/delete", json={"password": PASSWORD})
    assert service.sites.paused_at(code) == paused_at

    assert delete_paused(service.sites, service.payments, lambda: paused_at + 29 * DAY) == []
    with caplog.at_level(logging.INFO):
        deleted = delete_paused(service.sites, service.payments, lambda: paused_at + 30 * DAY + 1)
    assert deleted == [code]
    logged = next(r for r in caplog.records if r.message == "Site deleted")
    assert logged.__dict__["site"] == code and logged.__dict__["why"] == PAUSED_TOO_LONG
    assert logged.__dict__["subdomain"] == "dans"
    assert any(r.message == "Subscription cancelled at once" for r in caplog.records)

    # Everything it owns is gone, and the address with it.
    assert not folder.exists()
    assert service.sites.names() == [] and service.sites.site_at("dans") is None
    assert browser.get("/").status_code == 404
    assert browser.get("/api/host/session").status_code == 404
    # The subdomain is free; the trial's code never is.
    assert service.sites.name_problem("dans") is None
    assert service.sites.name_problem(code) == f"{code} is taken. Choose another name."

    # The host's account is kept, with no site, and still signs in: it says the site was
    # deleted, once the password is right.
    assert service.host_accounts.site_of(DAN) == NO_SITE
    main = TestClient(sites, base_url=MAIN)
    signing = main.post("/api/host/sign-in", json={"email": DAN, "password": PASSWORD})
    assert signing.status_code == 401 and signing.json()["detail"] == SITE_DELETED
    guess = main.post("/api/host/sign-in", json={"email": DAN, "password": "a wrong guess"})
    assert guess.json()["detail"] != SITE_DELETED
    # And a trial again is refused: one per email address (R66).
    assert service.sites.trial_used(DAN)


def test_a_trial_never_subscribed_is_deleted_without_stripe(tmp_path: Path) -> None:
    fake, sites, service, dan, site, code = subscribed(tmp_path, pay=False)
    asked = dan.post(f"{site}/api/site/delete", json={"password": PASSWORD})
    assert asked.status_code == 200 and site_home(code, service.home).exists()
    assert delete_paused(service.sites, None, lambda: time.time() + 31 * DAY) == [code]
    assert fake.deleted == [] and not site_home(code, service.home).exists()
    # The trial path is Site not found, and its sign-in is over.
    assert dan.get(f"{site}/").status_code == 404


def test_nothing_is_deleted_when_stripe_cant_cancel(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fake, sites, service, dan, site, code = subscribed(tmp_path)
    fake.fail = urllib.error.HTTPError(
        "https://api.stripe.com", 500, "error", Message(), io.BytesIO(b'{"error": {}}')
    )
    with caplog.at_level(logging.ERROR):
        refused = dan.post(f"{site}/api/site/delete", json={"password": PASSWORD})
    assert refused.status_code == 502 and refused.json()["detail"] == UNAVAILABLE
    assert any(r.message == "Stripe refused to cancel at once" for r in caplog.records)
    assert service.sites.names() == [code] and site_home(code, service.home).exists()
    assert service.sites.paused(code) is None and service.host_accounts.site_of(DAN) == code
    # A subscription Stripe has no more is cancelled already: the site is paused to delete.
    fake.fail = urllib.error.HTTPError(
        "https://api.stripe.com", 404, "missing", Message(), io.BytesIO(b"{}")
    )
    assert dan.post(f"{site}/api/site/delete", json={"password": PASSWORD}).status_code == 200
    assert service.sites.paused(code) == DELETING


def test_stripe_unreachable_or_not_set_up_keeps_the_site(tmp_path: Path) -> None:
    fake, _, service, _, _, code = subscribed(tmp_path)
    fake.fail = OSError("no network")
    stripe = Stripe("sk", SECRET, "price", fake.post, delete=fake.delete)
    with pytest.raises(PaymentError):
        stripe.cancel_now(code, "sub_1")
    from imageskin.site_deletion import delete_site

    with pytest.raises(PaymentError):
        delete_site(service.sites, None, code, "test")
    assert service.sites.names() == [code]


def test_the_days_before_deleting_are_an_admin_setting(tmp_path: Path) -> None:
    fake, sites, service, dan, site, code = subscribed(tmp_path, pay=False)
    service.admin_settings.change({"days_before_deleting": 7})
    asked = dan.post(f"{site}/api/site/delete", json={"password": PASSWORD}).json()
    paused_at = service.sites.paused_at(code)
    assert paused_at is not None and asked["deletes_at"] == paused_at + 7 * DAY
    shown = dan.get(f"{site}/api/site/subscription").json()
    assert shown["days_before_deleting"] == 7
    # The sweep reads the setting each time.
    thread = keep_deleting_paused(
        service.sites,
        None,
        every_s=0.01,
        now=lambda: paused_at + 7 * DAY + 1,
        days=lambda: service.admin_settings.current.days_before_deleting,
    )
    for _ in range(200):
        if not service.sites.names():
            break
        time.sleep(0.01)
    assert thread.daemon and service.sites.names() == []
    for bad in (0, 366, 1.5, "30", True):
        with pytest.raises(ValueError, match="whole number from 1 to 365"):
            service.admin_settings.change({"days_before_deleting": bad})


def test_a_site_paused_for_30_days_is_deleted(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fake, sites, service, dan, site, code = subscribed(tmp_path, pay=False)
    assert dan.post(f"{site}/api/site/cancel").json() == {"paused": True}
    now = time.time()
    assert delete_paused(service.sites, None, now=lambda: now + 29 * DAY) == []
    assert service.sites.names() == [code]
    with caplog.at_level(logging.INFO):
        assert delete_paused(service.sites, None, now=lambda: now + 30 * DAY + 1) == [code]
    logged = next(r for r in caplog.records if r.message == "Site deleted")
    assert logged.__dict__["why"] == PAUSED_TOO_LONG
    assert not site_home(code, service.home).exists()
    assert service.host_accounts.site_of(DAN) == NO_SITE


def test_a_paused_site_stripe_cant_cancel_is_kept_till_the_next_sweep(tmp_path: Path) -> None:
    fake, sites, service, dan, site, code = subscribed(tmp_path)
    send(
        TestClient(sites, base_url=MAIN),
        {
            "id": "evt_unpaid",
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_1", "status": "unpaid"}},
        },
    )
    assert service.sites.paused(code) is not None
    stripe = service.payments
    fake.fail = OSError("no network")
    later = time.time() + 31 * DAY
    assert delete_paused(service.sites, stripe, now=lambda: later) == []
    assert service.sites.names() == [code]
    fake.fail = None
    assert delete_paused(service.sites, stripe, now=lambda: later) == [code]
    assert fake.deleted == ["https://api.stripe.com/v1/subscriptions/sub_1"] * 2


def test_a_cancelled_subscription_isnt_cancelled_again(tmp_path: Path) -> None:
    fake, sites, service, dan, site, code = subscribed(tmp_path)
    send(
        TestClient(sites, base_url=MAIN),
        {
            "id": "evt_gone",
            "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_1", "status": "canceled"}},
        },
    )
    assert dan.post(f"{site}/api/site/delete", json={"password": PASSWORD}).status_code == 200
    assert fake.deleted == []


def test_the_sweep_runs_in_its_own_thread(tmp_path: Path) -> None:
    fake, sites, service, dan, site, code = subscribed(tmp_path, pay=False)
    dan.post(f"{site}/api/site/cancel")
    thread = keep_deleting_paused(service.sites, None, every_s=0.01, now=lambda: 10**12)
    for _ in range(200):
        if not service.sites.names():
            break
        time.sleep(0.01)
    assert thread.daemon and service.sites.names() == []


def test_the_main_address_cant_be_deleted_and_the_admin_uses_their_password(
    tmp_path: Path,
) -> None:
    apps, _, service = served_plain(tmp_path)
    boss = administrator(apps, tmp_path)
    assert boss.post("/api/site/delete", json={"password": PASSWORD}).status_code == 409
    acting = opened(apps, link_for(boss, "ann@example.com"))
    # Acting as Ann, the administrator gives their own password, not Ann's.
    assert acting.post("/api/site/delete", json={"password": PASSWORD}).status_code == 401
    assert acting.post("/api/site/delete", json={"password": "secret"}).status_code == 200
    assert service.sites.paused("a") == DELETING
    delete_paused(service.sites, None, lambda: time.time() + 31 * DAY)
    assert service.sites.names() == [] and not site_home("a", service.home).exists()
    # Its name is free again, and its host may have a site again.
    service.sites.add("a", "ann@example.com")
    assert service.sites.names() == ["a"]


def test_a_deleted_sites_app_is_forgotten_and_a_new_site_starts_afresh(tmp_path: Path) -> None:
    apps, made, service = served_plain(tmp_path)
    assert isinstance(apps, SiteApps)
    service.sites.on_deleted.append(apps.forget)
    first = apps.app("a")
    assert "a" in apps.sites()
    service.sites.delete("a", "test")
    assert "a" not in apps.sites()
    assert not service.sites.delete("a", "test")
    service.sites.add("a", "bob@example.com")
    assert apps.app("a") is not first


def test_deleted_trial_codes_are_kept_across_restarts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, service, _, _, code = subscribed(tmp_path, pay=False)
    service.sites.delete(code, "test")
    data = json.loads(service.sites.path.read_text())
    assert data["codes_kept"] == [code]
    from imageskin.sites import SiteDirectory, SiteError

    again = SiteDirectory(service.home, service.host_accounts)
    assert again.name_problem(code) is not None
    with pytest.raises(SiteError, match="already a site"):
        again.add(code, DAN)
    service.host_accounts.sign_up("eve@example.com", PASSWORD, "test")
    picks = iter(code + "y" * 12)
    monkeypatch.setattr(secrets, "choice", lambda letters: next(picks))
    assert again.add_trial("eve@example.com")[0] == "y" * 12


def test_the_real_delete_request_sends_a_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[Any] = []

    class Answer(io.BytesIO):
        def __enter__(self) -> "Answer":
            return self

        def __exit__(self, *a: object) -> None:
            pass

    def urlopen(request: Any, timeout: float) -> Answer:
        sent.append(request)
        return Answer(b'{"status": "canceled"}')

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    assert delete_request("https://api.stripe.com/v1/subscriptions/sub_1", "sk") == {
        "status": "canceled"
    }
    assert sent[0].get_method() == "DELETE"
    assert sent[0].headers["Authorization"] == "Bearer sk"
