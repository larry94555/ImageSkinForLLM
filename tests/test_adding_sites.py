"""Several sites for one host: the pages (roadmap R257, items 208 and 65). Add a site, on the
account page, picks the new site's subdomain with R63's checks and subscribes it through R67:
the site is made paused until it is paid for, and Stripe's event unpauses it."""

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_site_addresses import PASSWORD, with_hosts
from test_subscribing import (  # noqa: F401 (the fixture)
    DAN,
    MAIN,
    SECRET,
    FakeStripe,
    a_trial,
    completed,
    quick_hashes,
    send,
    served,
)

from imageskin.payments import Stripe
from imageskin.sites import ADDED, PICKED, SiteError, site_home

pytestmark = pytest.mark.real_hosts


def subscribed_trial(tmp_path: Path, fake: FakeStripe | None = None):  # type: ignore[no-untyped-def]
    """Dan's trial site, paid for by Stripe customer cus_1: Stripe, his browser, the site's path
    and code."""
    fake = fake or FakeStripe()
    stripe = Stripe("sk_test", SECRET, "price_5gb", fake)
    sites, _, service = served(tmp_path, stripe)
    dan, site = a_trial(sites, tmp_path / "home")
    code = site.removeprefix("/t/")
    assert send(TestClient(sites, base_url=MAIN), completed(code, "sub_1")).is_success
    assert service.sites.subscribed(code)
    return fake, sites, service, dan, site, code


def test_a_host_adds_a_site_paid_for_on_stripe_with_their_card_filled_in(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fake, sites, service, dan, site, code = subscribed_trial(tmp_path)
    with caplog.at_level(logging.INFO):
        added = dan.post(f"{site}/api/host/sites", json={"name": "Dans-Two"})
    assert added.status_code == 200, added.text
    assert added.json() == {
        "site": "dans-two",
        "url": "https://checkout.stripe.com/c/pay/cs_test_1",
    }
    assert "Site added, to be paid for" in caplog.messages
    url, form, _ = fake.posted[-1]
    assert url.endswith("/v1/checkout/sessions")
    # For the customer who pays for Dan's other site, so Stripe's page has his card.
    assert form["customer"] == "cus_1" and "customer_email" not in form
    assert form["client_reference_id"] == "dans-two"
    assert form["success_url"] == f"http://localhost:8000{site}/#/host/account"
    # Made at once, his, paused until paid for: never a free trial (R66).
    assert service.sites.paused("dans-two") == ADDED
    assert not service.sites.is_trial("dans-two")
    assert (site_home("dans-two", service.home)).is_dir()
    assert service.host_accounts.sites_of(DAN) == [code, "dans-two"]
    listed = dan.get(f"{site}/api/host/sites").json()["sites"]
    assert [(s["site"], s["paused"]) for s in listed] == [(code, False), ("dans-two", True)]
    assert listed[1]["address"] == "http://dans-two.localhost:8000"
    # Its own Settings says what it is waiting for.
    two = TestClient(sites, base_url="http://dans-two.localhost:8000")
    two.post("/api/host/sign-in", json={"email": DAN, "password": PASSWORD})
    assert two.get("/api/site/subscription").json()["added"] is True
    # Stripe's event for its checkout unpauses it.
    assert send(TestClient(sites, base_url=MAIN), completed("dans-two", "sub_2")).is_success
    assert service.sites.paused("dans-two") is None and service.sites.subscribed("dans-two")
    assert two.get("/api/site/subscription").json()["added"] is False


@pytest.mark.parametrize(
    ("name", "says"),
    [
        ("www", "kept for the service"),
        ("-x", "letters, digits and hyphens"),
        ("<code>", "is taken"),  # a trial's code is never given as a subdomain (R63)
    ],
)
def test_a_name_that_cant_be_had_is_refused_and_nothing_is_made(
    tmp_path: Path, name: str, says: str
) -> None:
    fake, _, service, dan, site, code = subscribed_trial(tmp_path)
    before, posted = service.sites.names(), len(fake.posted)
    refused = dan.post(f"{site}/api/host/sites", json={"name": name.replace("<code>", code)})
    assert refused.status_code == 409 and says in refused.json()["detail"]
    assert service.sites.names() == before and len(fake.posted) == posted
    assert service.host_accounts.sites_of(DAN) == [code]


def test_when_stripe_doesnt_answer_the_new_site_is_kept_and_trying_again_goes_on_with_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Codex's review of PR #304: Stripe may have made the checkout all the same, so the name is
    never freed for another host while it could still be paid for."""
    fake, sites, service, dan, site, code = subscribed_trial(tmp_path)
    fake.fail = OSError("the answer was lost")
    with caplog.at_level(logging.INFO):
        failed = dan.post(f"{site}/api/host/sites", json={"name": "dans-two"})
    assert failed.status_code == 502
    assert "Site added, its checkout not started" in caplog.messages
    assert service.sites.paused("dans-two") == ADDED
    assert service.host_accounts.sites_of(DAN) == [code, "dans-two"]
    # Taken for anyone else, but Dan's to try again: no second site is made.
    assert service.sites.name_problem("dans-two") is not None
    check = dan.get(f"{site}/api/site/subdomain/check", params={"name": "dans-two"}).json()
    assert check["problem"] is None
    fake.fail = None
    again = dan.post(f"{site}/api/host/sites", json={"name": "dans-two"})
    assert again.status_code == 200 and again.json()["site"] == "dans-two"
    assert service.host_accounts.sites_of(DAN) == [code, "dans-two"]
    with pytest.raises(SiteError, match="already a site called dans-two"):
        service.sites.add("dans-two", "bob@example.com")


def test_a_late_payment_for_a_deleted_site_never_pays_for_the_next_site_of_that_name(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Codex's review of PR #304: a checkout started for Dan's new site, which was deleted since
    and its name given to another host, is paid late: the new host's site stays unpaid."""
    fake, sites, service, dan, site, code = subscribed_trial(tmp_path)
    assert dan.post(f"{site}/api/host/sites", json={"name": "dans-two"}).status_code == 200
    started = fake.posted[-1][1]
    token = started["metadata[site_token]"]
    assert token == service.sites.token_of("dans-two")
    assert service.sites.delete("dans-two", "left unpaid")
    service.host_accounts.sign_up("eve@example.com", PASSWORD, "test")
    service.sites.add("dans-two", "eve@example.com")
    assert service.sites.token_of("dans-two") not in (None, token)
    late = completed("dans-two", "sub_late", token=token)
    with caplog.at_level(logging.INFO):
        assert send(TestClient(sites, base_url=MAIN), late).is_success
    assert "Payment for another site of that name" in caplog.messages
    assert service.sites.subscription("dans-two") is None
    # A paid checkout with no token at all is refused the same way for a site that has one.
    bare = completed("dans-two", "sub_x")
    bare["data"]["object"]["metadata"] = {"site": "dans-two"}
    assert send(TestClient(sites, base_url=MAIN), bare).is_success
    assert service.sites.subscription("dans-two") is None
    # Its own checkout, with its own token, does pay for it.
    assert send(TestClient(sites, base_url=MAIN), completed("dans-two", "sub_eve")).is_success
    assert service.sites.subscribed("dans-two")


def test_only_the_host_adds_a_site_and_only_where_subscribing_is_set_up(tmp_path: Path) -> None:
    sites, _, service = served(tmp_path, None)
    dan, site = a_trial(sites, tmp_path / "home")
    refused = dan.post(f"{site}/api/host/sites", json={"name": "dans-two"})
    assert refused.status_code == 503 and not service.sites.exists("dans-two")


def test_a_name_a_site_changed_away_from_is_given_to_the_new_site_as_its_subdomain(
    tmp_path: Path,
) -> None:
    service = with_hosts(tmp_path, "ann@example.com", "bob@example.com")
    service.sites.add("ann", "ann@example.com")
    service.sites.change_subdomain("ann", "ann-new")
    # "ann" is free as a subdomain, though it is still that site's name inside (R64).
    made = service.sites.add_paid("ann@example.com", "ann")
    assert made != "ann" and service.sites.subdomain(made) == "ann"
    assert service.sites.paused(made) == ADDED
    assert service.host_accounts.sites_of("ann@example.com") == ["ann", made]
    # Added again while not paid for yet, it is the same site; for another host it is taken.
    assert service.sites.add_paid("ann@example.com", "ann") == made
    service.sites.add("bobs", "bob@example.com")
    with pytest.raises(SiteError, match="ann is taken"):
        service.sites.add_paid("bob@example.com", "ann")
    # A host with only the main address adds one from the command line instead.
    service.host_accounts.sign_up("cy@example.com", PASSWORD, "test")
    with pytest.raises(SiteError, match="site of their own"):
        service.sites.add_paid("cy@example.com", "cys")
    assert PICKED == "subdomain"
