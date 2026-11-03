"""Resuming a cancelled subscription (roadmap R69b, feature 213): a host whose site paused signs
in and clicks Resume subscription. A new subscription is made for the Stripe customer the site
had, with the card Stripe keeps, so no card details are typed again, and the site is back at
once; with no card Stripe can charge, Stripe's page is asked for instead, for that customer."""

import io
import json
import logging
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_site_addresses import PASSWORD
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

from imageskin.payments import UNAVAILABLE, CardNeeded, PaymentError, Stripe
from imageskin.sites import site_home

pytestmark = pytest.mark.real_hosts

CHECKOUT = "https://checkout.stripe.com/c/pay/cs_1"


def refusal(code: int, error: dict[str, Any]) -> urllib.error.HTTPError:
    body = io.BytesIO(json.dumps({"error": error}).encode())
    return urllib.error.HTTPError("https://api.stripe.com", code, "refused", Message(), body)


class FakeStripe:
    """Stripe's API: a checkout, the old subscription with its card, and a new subscription."""

    def __init__(self) -> None:
        self.posted: list[tuple[str, dict[str, str]]] = []
        self.got: list[str] = []
        self.deleted: list[str] = []
        self.refuse: Exception | None = None  # how making the new subscription fails
        self.card: str | None = "pm_card"
        self.made: dict[str, dict[str, Any]] = {}  # by idempotency key, as Stripe keeps them
        self.lose_answer = False  # Stripe makes the subscription, but its answer is lost
        self.keys: list[str | None] = []

    def post(
        self, url: str, form: dict[str, str], key: str, idempotency: str | None = None
    ) -> dict[str, Any]:
        self.posted.append((url, form))
        if url.endswith("/v1/subscriptions"):
            self.keys.append(idempotency)
            if self.refuse is not None:
                raise self.refuse
            if idempotency not in self.made:
                self.made[str(idempotency)] = {
                    "id": f"sub_new{len(self.made) + 1}",
                    "status": "active",
                    "metadata": {"site": form["metadata[site]"]},
                }
            if self.lose_answer:
                raise OSError("the answer was lost")
            return self.made[str(idempotency)]
        return {"id": "cs_1", "url": CHECKOUT}

    def get(self, url: str, key: str) -> dict[str, Any]:
        self.got.append(url)
        if "?" in url:
            return {"data": list(self.made.values())}
        return {"id": url.rsplit("/", 1)[1], "default_payment_method": self.card}

    def delete(self, url: str, key: str) -> dict[str, Any]:
        self.deleted.append(url)
        return {"id": url.rsplit("/", 1)[1], "status": "canceled"}


def ended(status: str = "canceled") -> dict[str, Any]:
    return {
        "id": "evt_2",
        "type": "customer.subscription.deleted"
        if status == "canceled"
        else "customer.subscription.updated",
        "created": 1_800_000_000,
        "data": {"object": {"id": "sub_1", "status": status}},
    }


def paused(tmp_path: Path, status: str = "canceled"):  # type: ignore[no-untyped-def]
    """Dan's site, subscribed, then paused as Stripe ended its subscription: Dan's browser."""
    fake = FakeStripe()
    stripe = Stripe("sk_test", SECRET, "price_5gb", fake.post, delete=fake.delete, get=fake.get)
    sites, _, service = served(tmp_path, stripe)
    dan, site = a_trial(sites, tmp_path / "home")
    code = site.removeprefix("/t/")
    main = TestClient(sites, base_url=MAIN)
    assert send(main, completed(code, "sub_1")).is_success
    assert send(main, ended(status)).is_success
    assert service.sites.paused(code) == "subscription ended"
    (site_home(code, service.home) / "person.txt").write_text("Dan's person", encoding="utf-8")
    return fake, sites, service, dan, site, code


def test_resume_subscription_brings_the_paused_site_back_with_the_card_on_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fake, sites, service, dan, site, code = paused(tmp_path)
    shown = dan.get(f"{site}/api/site/subscription").json()
    assert shown["resumable"] is True and shown["subscribed"] is False
    with caplog.at_level(logging.INFO):
        answer = dan.post(f"{site}/api/site/subscription/resume")
    assert answer.status_code == 200 and answer.json() == {"resumed": True}
    # The card the last subscription was paid with, for the same customer: nothing typed. Stripe
    # had no subscription for it in force already.
    assert fake.got == [
        "https://api.stripe.com/v1/subscriptions/sub_1",
        "https://api.stripe.com/v1/subscriptions?customer=cus_1&status=all&limit=100",
    ]
    assert fake.keys == [f"resume-{code}-sub_1"]
    url, form = fake.posted[-1]
    assert url == "https://api.stripe.com/v1/subscriptions"
    assert form == {
        "customer": "cus_1",
        "items[0][price]": "price_5gb",
        "items[0][quantity]": "1",
        "metadata[site]": code,
        "payment_behavior": "error_if_incomplete",
        "off_session": "true",
        "default_payment_method": "pm_card",
    }
    # A canceled subscription is gone at Stripe already: nothing to end first.
    assert fake.deleted == []
    # Back at once, with everything on it.
    assert service.sites.paused(code) is None and service.sites.subscribed(code)
    assert service.sites.subscription(code)["id"] == "sub_new1"
    assert (site_home(code, service.home) / "person.txt").read_text() == "Dan's person"
    assert any(r.message == "Subscription resumed" for r in caplog.records)
    shown = dan.get(f"{site}/api/site/subscription").json()
    assert shown["resumable"] is False and shown["subscribed"] is True
    # Clicking again makes no second subscription.
    again = dan.post(f"{site}/api/site/subscription/resume")
    assert again.status_code == 409 and len(fake.made) == 1
    # Stripe's own event for the new subscription changes nothing more.
    assert send(TestClient(sites, base_url=MAIN), completed(code, "sub_new1")).is_success
    assert service.sites.subscription(code)["id"] == "sub_new1"


@pytest.mark.parametrize(
    "refused",
    [
        refusal(402, {"type": "card_error", "code": "card_declined", "message": "declined"}),
        refusal(
            400,
            {
                "type": "invalid_request_error",
                "message": "This customer has no attached payment source or default payment "
                "method.",
            },
        ),
    ],
)
def test_with_no_card_stripe_can_charge_stripes_page_is_asked_for(
    tmp_path: Path, refused: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    fake, sites, service, dan, site, code = paused(tmp_path)
    fake.refuse, fake.card = refused, None
    with caplog.at_level(logging.INFO):
        answer = dan.post(f"{site}/api/site/subscription/resume")
    assert answer.status_code == 200 and answer.json() == {"resumed": False, "url": CHECKOUT}
    # No card was known, so the customer's own default was tried.
    assert "default_payment_method" not in fake.posted[-2][1]
    # Stripe's page is for the same customer, filled in, never a new one.
    url, form = fake.posted[-1]
    assert url == "https://api.stripe.com/v1/checkout/sessions"
    assert form["customer"] == "cus_1" and "customer_email" not in form
    assert form["client_reference_id"] == code
    assert service.sites.paused(code) == "subscription ended"
    assert any(r.message == "Resume goes to Stripe" for r in caplog.records)


def test_a_lost_answer_then_a_retry_or_restart_makes_one_subscription(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Stripe made and charged the subscription, but its answer never came back: trying again,
    even after a restart, records that one and makes no second (Codex's review of PR #301)."""
    fake, sites, service, dan, site, code = paused(tmp_path)
    fake.lose_answer = True
    lost = dan.post(f"{site}/api/site/subscription/resume")
    assert lost.status_code == 502 and service.sites.paused(code) == "subscription ended"
    assert len(fake.made) == 1
    fake.lose_answer = False
    with caplog.at_level(logging.WARNING):
        assert dan.post(f"{site}/api/site/subscription/resume").json() == {"resumed": True}
    assert len(fake.made) == 1 and service.sites.subscription(code)["id"] == "sub_new1"
    assert any(r.message == "Subscription already made at Stripe" for r in caplog.records)
    # Its key is the same however often it is tried, so Stripe itself makes one too.
    assert fake.keys == [f"resume-{code}-sub_1"]


def test_a_past_due_subscription_at_stripe_is_never_taken_as_paid(tmp_path: Path) -> None:
    """Stripe has a `past_due` subscription for the site, whose payment failed: it is ended, not
    recorded as paid, and the resume charges a new one (Codex's review of PR #301)."""
    fake, sites, service, dan, site, code = paused(tmp_path)
    fake.made["other"] = {"id": "sub_due", "status": "past_due", "metadata": {"site": code}}
    assert dan.post(f"{site}/api/site/subscription/resume").json() == {"resumed": True}
    assert fake.deleted == ["https://api.stripe.com/v1/subscriptions/sub_due"]
    assert fake.keys == [f"resume-{code}-sub_1"]
    assert service.sites.subscription(code)["id"] == "sub_new2"


def test_a_new_subscription_stripe_hasnt_been_paid_for_keeps_the_site_paused(
    tmp_path: Path,
) -> None:
    fake, sites, service, dan, site, code = paused(tmp_path)
    fake.made[f"resume-{code}-sub_1"] = {"id": "sub_x", "status": "incomplete", "metadata": {}}
    answer = dan.post(f"{site}/api/site/subscription/resume")
    assert answer.status_code == 502 and service.sites.paused(code) == "subscription ended"


def test_a_later_resume_after_a_new_cancellation_has_a_new_key(tmp_path: Path) -> None:
    fake, sites, service, dan, site, code = paused(tmp_path)
    assert dan.post(f"{site}/api/site/subscription/resume").json() == {"resumed": True}
    # The resumed subscription ends too, and the host resumes again.
    main = TestClient(sites, base_url=MAIN)
    event = ended()
    event["data"]["object"]["id"] = "sub_new1"
    event["created"] += 1
    assert send(main, event).is_success
    fake.made["resume-old"] = {**fake.made.pop(f"resume-{code}-sub_1"), "status": "canceled"}
    assert dan.post(f"{site}/api/site/subscription/resume").json() == {"resumed": True}
    assert fake.keys == [f"resume-{code}-sub_1", f"resume-{code}-sub_new1"]
    assert service.sites.subscription(code)["id"] == "sub_new2"


def test_an_unpaid_subscription_is_ended_first_so_nothing_is_paid_twice(tmp_path: Path) -> None:
    fake, sites, service, dan, site, code = paused(tmp_path, status="unpaid")
    assert dan.post(f"{site}/api/site/subscription/resume").json() == {"resumed": True}
    assert fake.deleted == ["https://api.stripe.com/v1/subscriptions/sub_1"]
    assert service.sites.paused(code) is None


def test_a_cancelled_trial_with_no_customer_goes_to_stripes_page(tmp_path: Path) -> None:
    fake = FakeStripe()
    stripe = Stripe("sk_test", SECRET, "price_5gb", fake.post, delete=fake.delete, get=fake.get)
    sites, _, service = served(tmp_path, stripe)
    dan, site = a_trial(sites, tmp_path / "home")
    code = site.removeprefix("/t/")
    assert dan.post(f"{site}/api/site/cancel").is_success
    assert dan.get(f"{site}/api/site/subscription").json()["resumable"] is False
    answer = dan.post(f"{site}/api/site/subscription/resume")
    assert answer.json() == {"resumed": False, "url": CHECKOUT}
    assert fake.posted[-1][1]["customer_email"] == DAN and fake.got == []
    assert service.sites.paused(code) == "cancelled"


def test_resume_is_refused_where_it_doesnt_fit(tmp_path: Path) -> None:
    fake, sites, service, dan, site, code = paused(tmp_path)
    # Stripe can't be reached: the site stays paused and the host is told to try again.
    fake.refuse = OSError("down")
    answer = dan.post(f"{site}/api/site/subscription/resume")
    assert answer.status_code == 502 and answer.json()["detail"] == UNAVAILABLE
    # Another refusal from Stripe isn't a card problem.
    fake.refuse = refusal(500, {"type": "api_error", "message": "oops"})
    assert dan.post(f"{site}/api/site/subscription/resume").status_code == 502
    assert service.sites.paused(code) == "subscription ended"
    # A site that isn't paused, or a visitor, can't resume.
    fake.refuse = None
    assert dan.post(f"{site}/api/site/subscription/resume").json() == {"resumed": True}
    assert dan.post(f"{site}/api/site/subscription/resume").status_code == 409
    stranger = TestClient(sites, base_url=MAIN)
    assert stranger.post(f"{site}/api/site/subscription/resume").status_code == 401


def test_signing_in_to_a_paused_site_says_it_is_paused(tmp_path: Path) -> None:
    fake, sites, service, dan, site, code = paused(tmp_path)
    again = TestClient(sites, base_url=MAIN)
    answer = again.post(f"{site}/api/host/sign-in", json={"email": DAN, "password": PASSWORD})
    assert answer.status_code == 200 and answer.json()["paused"] is True
    assert dan.get(f"{site}/api/host/session").json()["paused"] is True


def test_resume_needs_stripe_set_up(tmp_path: Path) -> None:
    sites, _, service = served(tmp_path, None)
    dan, site = a_trial(sites, tmp_path / "home")
    assert dan.post(f"{site}/api/site/cancel").is_success
    answer = dan.post(f"{site}/api/site/subscription/resume")
    assert answer.status_code == 503


def test_the_card_of_a_subscription_stripe_lost_or_cant_read(tmp_path: Path) -> None:
    def missing(url: str, key: str) -> dict[str, Any]:
        raise refusal(404, {"type": "invalid_request_error", "code": "resource_missing"})

    def down(url: str, key: str) -> dict[str, Any]:
        raise refusal(500, {"type": "api_error"})

    def card_object(url: str, key: str) -> dict[str, Any]:
        return {"default_payment_method": {"id": "pm_9", "object": "payment_method"}}

    def unreachable(url: str, key: str) -> dict[str, Any]:
        raise OSError("down")

    assert Stripe("sk", SECRET, "p", get=missing).card_of("a", "sub_1") is None
    assert Stripe("sk", SECRET, "p", get=card_object).card_of("a", "sub_1") == "pm_9"
    assert Stripe("sk", SECRET, "p").card_of("a", None) is None
    for broken in (down, unreachable):
        with pytest.raises(PaymentError):
            Stripe("sk", SECRET, "p", get=broken).card_of("a", "sub_1")
        with pytest.raises(PaymentError):
            Stripe("sk", SECRET, "p", get=broken).live_subscription("a", "cus_1")
    assert issubclass(CardNeeded, PaymentError)


def test_the_real_get_request_sends_a_get(monkeypatch: pytest.MonkeyPatch) -> None:
    from imageskin import payments

    seen: list[tuple[str, str | None, str | None]] = []

    class Answer(io.BytesIO):
        def __enter__(self) -> "Answer":
            return self

        def __exit__(self, *a: object) -> None:
            pass

    def opened(request: Any, timeout: float) -> Answer:
        seen.append(
            (
                request.get_method(),
                request.get_header("Authorization"),
                request.get_header("Idempotency-key"),
            )
        )
        return Answer(b'{"id": "sub_1"}')

    monkeypatch.setattr("imageskin.payments.urllib.request.urlopen", opened)
    assert payments.get_request("https://api.stripe.com/v1/subscriptions/sub_1", "sk") == {
        "id": "sub_1"
    }
    assert payments.post_form("https://api.stripe.com/v1/subscriptions", {}, "sk", "k1") == {
        "id": "sub_1"
    }
    assert seen == [("GET", "Bearer sk", None), ("POST", "Bearer sk", "k1")]
