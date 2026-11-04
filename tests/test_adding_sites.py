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

from imageskin.payments import PaymentError, Stripe
from imageskin.sites import ADDED, PICKED, SiteError, site_home

pytestmark = pytest.mark.real_hosts


def subscribed_trial(tmp_path: Path, fake: FakeStripe | None = None):  # type: ignore[no-untyped-def]
    """Dan's trial site, paid for by Stripe customer cus_1: Stripe, his browser, the site's path
    and code."""
    fake = fake or FakeStripe()
    stripe = Stripe("sk_test", SECRET, "price_5gb", fake, delete=fake.delete, get=fake.get)
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


def test_a_checkout_asked_for_again_is_the_same_one_and_a_second_payment_is_cancelled(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Codex's review of PR #304: Stripe makes the checkout but its answer is lost, and the host
    tries again. Stripe answers the same checkout, by its idempotency key; and were two
    checkouts for one site both paid, the second subscription is cancelled at once, so the host
    is never charged twice for one site."""
    fake, sites, service, dan, site, code = subscribed_trial(tmp_path)
    fake.lose_answer = True
    assert dan.post(f"{site}/api/host/sites", json={"name": "dans-two"}).status_code == 502
    fake.lose_answer = False
    again = dan.post(f"{site}/api/host/sites", json={"name": "dans-two"})
    assert again.status_code == 200
    token = service.sites.token_of("dans-two")
    assert fake.keys[-2:] == [f"add-{token}", f"add-{token}"]
    assert len(fake.made) == 1  # one checkout at Stripe, answered twice
    assert again.json()["url"] == fake.made[f"add-{token}"]["url"]
    # Two paid checkouts for the one site all the same: the first is kept, the second ended.
    main = TestClient(sites, base_url=MAIN)
    assert send(main, completed("dans-two", "sub_a")).is_success
    with caplog.at_level(logging.INFO):
        assert send(main, completed("dans-two", "sub_b")).is_success
    assert "Second subscription for a site" in caplog.messages
    assert "Second payment refunded" in caplog.messages
    assert fake.deleted == ["https://api.stripe.com/v1/subscriptions/sub_b"]
    # Its first payment is given back: one net payment for the site.
    assert list(fake.refunds) == ["refund-sub_b-pi_sub_b"]
    assert fake.refunds["refund-sub_b-pi_sub_b"]["payment_intent"] == "pi_sub_b"
    assert fake.refunds["refund-sub_b-pi_sub_b"]["reason"] == "duplicate"
    assert (service.sites.subscription("dans-two") or {})["id"] == "sub_a"
    # The same event again (Stripe resends it) changes nothing more.
    assert send(main, completed("dans-two", "sub_a")).is_success
    assert (service.sites.subscription("dans-two") or {})["id"] == "sub_a"


def test_a_second_payment_stripe_cant_refund_or_cancel_yet_is_done_once_when_sent_again(
    tmp_path: Path,
) -> None:
    """Stripe can't be reached as the second payment is refunded, then as it is cancelled: the
    event is answered 503 each time, so Stripe sends it again, and once both work the payment
    is refunded once and the subscription ended, the first one kept all along."""
    fake, sites, service, dan, site, code = subscribed_trial(tmp_path)
    main = TestClient(sites, base_url=MAIN)
    fake.refund_fails = OSError("Stripe not reached")
    assert send(main, completed(code, "sub_2")).status_code == 503
    assert fake.refunds == {} and fake.deleted == []
    fake.refund_fails = None

    def unreachable(url: str, key: str) -> dict[str, object]:
        raise OSError("Stripe not reached")

    object.__setattr__(service.payments, "delete", unreachable)
    assert send(main, completed(code, "sub_2")).status_code == 503
    assert list(fake.refunds) == ["refund-sub_2-pi_sub_2"]  # refunded, not cancelled yet
    object.__setattr__(service.payments, "delete", fake.delete)
    assert send(main, completed(code, "sub_2")).is_success
    assert send(main, completed(code, "sub_2")).is_success  # and once more, as Stripe may
    # One refund at Stripe however often it was asked for, by its idempotency key.
    assert list(fake.refunds) == ["refund-sub_2-pi_sub_2"]
    assert fake.deleted[-1] == "https://api.stripe.com/v1/subscriptions/sub_2"
    assert (service.sites.subscription(code) or {})["id"] == "sub_1"


def test_a_refund_reads_an_invoice_by_its_id_and_refunds_nothing_unpaid() -> None:
    posted: list[tuple[str, dict[str, str], str | None]] = []
    invoices: dict[str, dict[str, object]] = {
        "in_paid": {"charge": "ch_1", "amount_paid": 199},
        "in_free": {"payment_intent": None, "amount_paid": 0},
    }

    def get(url: str, key: str) -> dict[str, object]:
        if "/invoices/" in url:
            return dict(invoices[url.rsplit("/", 1)[1].split("?")[0]])
        sub = url.rsplit("/", 1)[1].split("?")[0]
        return {"latest_invoice": "in_paid" if sub == "sub_paid" else "in_free"}

    def post(
        url: str, form: dict[str, str], key: str, idempotency: str | None = None
    ) -> dict[str, object]:
        posted.append((url, form, idempotency))
        return {"id": "re_1"}

    stripe = Stripe("sk_test", SECRET, "price_5gb", post, get=get)
    assert stripe.refund_first_payment("a", "sub_paid") == ["re_1"]
    assert posted == [
        (
            "https://api.stripe.com/v1/refunds",
            {"charge": "ch_1", "reason": "duplicate", "metadata[site]": "a"},
            "refund-sub_paid-ch_1",
        )
    ]
    assert stripe.refund_first_payment("a", "sub_free") == [] and len(posted) == 1


def test_a_refund_finds_the_payment_in_the_invoice_payments_of_newer_stripe_apis() -> None:
    """Codex's review of PR #304: from Stripe's API 2025-03-31.basil on, an invoice names its
    payment only in its invoice payments, here listed by `/v1/invoice_payments` as the invoice
    read by its id has none expanded; a paid invoice naming no payment is never taken for
    refunded."""
    posted: list[dict[str, str]] = []
    listed: dict[str, dict[str, object]] = {
        "in_new": {
            "data": [
                {"status": "canceled", "payment": {"payment_intent": "pi_failed"}},
                {
                    "status": "paid",
                    "amount_paid": 199,
                    "payment": {"type": "charge", "charge": {"id": "ch_new"}},
                },
            ]
        },
        "in_lost": {"data": []},
    }

    def get(url: str, key: str) -> dict[str, object]:
        if "/invoice_payments?invoice=" in url:
            return dict(listed[url.split("invoice=", 1)[1].split("&")[0]])
        if "/invoices/" in url:
            invoice = url.rsplit("/", 1)[1].split("?")[0]
            return {"id": invoice, "amount_paid": 199}
        sub = url.rsplit("/", 1)[1].split("?")[0]
        return {"latest_invoice": "in_new" if sub == "sub_new" else "in_lost"}

    def post(
        url: str, form: dict[str, str], key: str, idempotency: str | None = None
    ) -> dict[str, object]:
        posted.append(form)
        return {"id": "re_new"}

    stripe = Stripe("sk_test", SECRET, "price_5gb", post, get=get)
    assert stripe.refund_first_payment("a", "sub_new") == ["re_new"]
    assert posted == [
        {"charge": "ch_new", "reason": "duplicate", "metadata[site]": "a", "amount": "199"}
    ]
    with pytest.raises(PaymentError):
        stripe.refund_first_payment("a", "sub_lost")
    assert len(posted) == 1


def test_a_second_payment_whose_refund_cant_be_found_is_never_acknowledged(
    tmp_path: Path,
) -> None:
    fake, sites, service, dan, site, code = subscribed_trial(tmp_path)

    def no_payment_named(url: str, key: str) -> dict[str, object]:
        if "/invoice_payments" in url:
            return {"data": []}
        return {"latest_invoice": {"id": "in_1", "amount_paid": 199}}

    object.__setattr__(service.payments, "get", no_payment_named)
    main = TestClient(sites, base_url=MAIN)
    # Not cancelled as if refunded: answered 503, so Stripe sends it again.
    assert send(main, completed(code, "sub_2")).status_code == 503
    assert fake.refunds == {} and fake.deleted == []


def two_partial_payments(sub: str, more: bool = False) -> dict[str, object]:
    """An invoice of $1.99 paid by two payments, $1.00 and $0.99 (Stripe's API from
    2025-03-31.basil on); `more` says Stripe listed only the first, so the rest is read page by
    page."""
    first = {
        "id": "inpay_1",
        "status": "paid",
        "amount_paid": 100,
        "payment": {"type": "payment_intent", "payment_intent": f"pi_{sub}_a"},
    }
    second = {
        "id": "inpay_2",
        "status": "paid",
        "amount_paid": 99,
        "payment": {"type": "charge", "charge": f"ch_{sub}_b"},
    }
    if more:
        return {
            "id": f"in_{sub}",
            "amount_paid": 199,
            "payments": {"data": [first], "has_more": True},
            "_rest": [first, second],
        }
    return {"id": f"in_{sub}", "amount_paid": 199, "payments": {"data": [first, second]}}


def test_a_second_payment_paid_in_parts_is_refunded_each_part_once_before_it_is_acknowledged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Codex's review of PR #304: the second subscription's invoice was paid by two partial
    payments. Stripe fails after the first is refunded: the event is answered 503 and not
    cancelled; sent again, each part is refunded exactly once, for what it paid, and only then
    is the subscription ended and the event acknowledged."""
    fake, sites, service, dan, site, code = subscribed_trial(tmp_path)
    fake.invoices["sub_2"] = two_partial_payments("sub_2")
    fake.refund_fails_for = {"refund-sub_2-ch_sub_2_b"}
    main = TestClient(sites, base_url=MAIN)
    assert send(main, completed(code, "sub_2")).status_code == 503
    assert list(fake.refunds) == ["refund-sub_2-pi_sub_2_a"] and fake.deleted == []
    fake.refund_fails_for = set()
    with caplog.at_level(logging.INFO):
        assert send(main, completed(code, "sub_2")).is_success
    assert "Second payment refunded" in caplog.messages
    assert send(main, completed(code, "sub_2")).is_success  # and once more, as Stripe may
    assert list(fake.refunds) == ["refund-sub_2-pi_sub_2_a", "refund-sub_2-ch_sub_2_b"]
    a, b = fake.refunds.values()
    assert (a["payment_intent"], a["amount"]) == ("pi_sub_2_a", "100")
    assert (b["charge"], b["amount"]) == ("ch_sub_2_b", "99")
    assert fake.deleted[-1] == "https://api.stripe.com/v1/subscriptions/sub_2"
    assert (service.sites.subscription(code) or {})["id"] == "sub_1"


def test_a_refund_reads_every_page_of_an_invoices_payments() -> None:
    """The invoice's expanded payments are only its first page: the rest are read from
    `/v1/invoice_payments`, page by page, and every paid one refunded."""
    invoice = two_partial_payments("sub_x", more=True)
    rest = invoice.pop("_rest")
    asked: list[str] = []
    posted: list[str | None] = []

    def get(url: str, key: str) -> dict[str, object]:
        asked.append(url)
        if "/invoice_payments?" in url:
            if "starting_after=inpay_1" in url:
                return {"data": rest[1:], "has_more": False}  # type: ignore[index]
            return {"data": rest[:1], "has_more": True}  # type: ignore[index]
        return {"latest_invoice": invoice}

    def post(
        url: str, form: dict[str, str], key: str, idempotency: str | None = None
    ) -> dict[str, object]:
        posted.append(idempotency)
        return {"id": f"re_{len(posted)}"}

    stripe = Stripe("sk_test", SECRET, "price_5gb", post, get=get)
    assert stripe.refund_first_payment("a", "sub_x") == ["re_1", "re_2"]
    assert posted == ["refund-sub_x-pi_sub_x_a", "refund-sub_x-ch_sub_x_b"]
    assert [u.split("?", 1)[1] for u in asked[1:]] == [
        "invoice=in_sub_x&limit=100",
        "invoice=in_sub_x&limit=100&starting_after=inpay_1",
    ]
