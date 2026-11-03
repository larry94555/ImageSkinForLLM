"""Cancel, a failed payment and a paused site (roadmap R69): a subscription cancelled in
Settings ends at the end of the period paid for, when Stripe's event pauses the site; a failed
renewal is said to the host only; and subscribing again brings the site back."""

import logging
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_subscribing import (  # noqa: F401
    MAIN,
    SECRET,
    a_trial,
    completed,
    quick_hashes,
    send,
    served,
)

from imageskin.payments import UNAVAILABLE, PaymentError, Stripe, ends_at
from imageskin.sites import SUBSCRIPTION_ENDED, SiteDirectory

pytestmark = pytest.mark.real_hosts

ENDS = 1_796_000_000


class FakeStripe:
    """Stripe's API: a checkout, and a subscription set to cancel at the period's end or not."""

    def __init__(self) -> None:
        self.posted: list[tuple[str, dict[str, str]]] = []
        self.fail: Exception | None = None

    def __call__(self, url: str, form: dict[str, str], key: str) -> dict[str, Any]:
        self.posted.append((url, form))
        if self.fail is not None:
            raise self.fail
        if "/subscriptions/" in url:
            cancel = form["cancel_at_period_end"] == "true"
            return {
                "id": url.rsplit("/", 1)[1],
                "status": "active",
                "cancel_at_period_end": cancel,
                "cancel_at": ENDS if cancel else None,
            }
        return {"id": "cs_1", "url": "https://checkout.stripe.com/c/pay/cs_1"}


def subscribed(tmp_path: Path):  # type: ignore[no-untyped-def]
    fake = FakeStripe()
    sites, _, service = served(tmp_path, Stripe("sk_test", SECRET, "price_5gb", fake))
    dan, site = a_trial(sites, tmp_path / "home")
    code = site.removeprefix("/t/")
    main = TestClient(sites, base_url=MAIN)
    assert send(main, completed(code, "sub_1")).is_success
    return fake, sites, service, dan, site, code, main


def changed(status: str, kind: str = "updated", **more: Any) -> dict[str, Any]:
    return {
        "id": f"evt_{status}",
        "type": f"customer.subscription.{kind}",
        "data": {"object": {"id": "sub_1", "status": status, **more}},
    }


def test_cancel_keeps_the_site_until_the_end_then_stripe_pauses_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fake, sites, service, dan, site, code, main = subscribed(tmp_path)
    with caplog.at_level(logging.INFO):
        cancelled = dan.post(f"{site}/api/site/subscription/cancel")
    assert cancelled.json() == {"ends_at": ENDS}
    url, form = fake.posted[-1]
    assert url == "https://api.stripe.com/v1/subscriptions/sub_1"
    assert form == {"cancel_at_period_end": "true"}
    logged = next(r for r in caplog.records if r.message == "Subscription cancelled")
    assert logged.__dict__["site"] == code and logged.__dict__["ends_at"] == ENDS
    # Still working, and saying when it ends.
    shown = dan.get(f"{site}/api/site/subscription").json()
    assert shown["subscribed"] is True and shown["ends_at"] == ENDS
    assert service.sites.paused(code) is None
    visitor = TestClient(sites, base_url=MAIN)
    assert visitor.get(f"{site}/api/content").status_code == 200
    # Stripe's own event says the same.
    assert send(main, changed("active", cancel_at_period_end=True, cancel_at=ENDS)).is_success
    assert service.sites.subscription(code)["ends_at"] == ENDS

    # At the end, Stripe deletes the subscription: the site pauses.
    caplog.clear()
    with caplog.at_level(logging.INFO):
        assert send(main, changed("canceled", "deleted", cancel_at=ENDS)).is_success
    assert "Site paused" in caplog.messages
    assert service.sites.paused(code) == SUBSCRIPTION_ENDED
    assert visitor.get(f"{site}/api/content").json() == {"detail": "This site is paused."}
    # Its host still signs in and uses it, and subscribes again to bring it back.
    assert dan.get(f"{site}/api/content").status_code == 200
    shown = dan.get(f"{site}/api/site/subscription").json()
    assert shown["subscribed"] is False and shown["ends_at"] is None
    assert dan.post(f"{site}/api/site/subscribe").is_success
    assert send(main, completed(code, "sub_2")).is_success
    assert service.sites.paused(code) is None and service.sites.subscribed(code)
    assert visitor.get(f"{site}/api/content").status_code == 200


def test_keep_undoes_a_cancel_before_the_end(tmp_path: Path) -> None:
    fake, _, service, dan, site, code, main = subscribed(tmp_path)
    dan.post(f"{site}/api/site/subscription/cancel")
    kept = dan.post(f"{site}/api/site/subscription/keep")
    assert kept.json() == {"ends_at": None}
    assert fake.posted[-1][1] == {"cancel_at_period_end": "false"}
    assert dan.get(f"{site}/api/site/subscription").json()["ends_at"] is None
    assert send(main, changed("active", cancel_at_period_end=False)).is_success
    assert service.sites.subscription(code)["ends_at"] is None


def test_a_failed_renewal_is_said_to_the_host_only_and_the_site_keeps_working(
    tmp_path: Path,
) -> None:
    _, sites, service, dan, site, code, main = subscribed(tmp_path)
    assert send(main, changed("past_due")).is_success
    assert dan.get(f"{site}/api/site/subscription").json()["payment_failed"] is True
    assert service.sites.paused(code) is None
    assert TestClient(sites, base_url=MAIN).get(f"{site}/api/content").status_code == 200
    # Paid on Stripe's next try: the notice goes.
    assert send(main, changed("active")).is_success
    assert dan.get(f"{site}/api/site/subscription").json()["payment_failed"] is False
    # Never paid: when Stripe gives up, the site pauses.
    assert send(main, changed("past_due")).is_success
    assert send(main, changed("unpaid")).is_success
    assert service.sites.paused(code) == SUBSCRIPTION_ENDED


def test_cancel_is_refused_without_a_subscription_or_when_stripe_fails(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fake, _, service, dan, site, code, _ = subscribed(tmp_path)
    fake.fail = OSError("no network")
    with caplog.at_level(logging.ERROR):
        failed = dan.post(f"{site}/api/site/subscription/cancel")
    assert failed.status_code == 502 and failed.json()["detail"] == UNAVAILABLE
    assert "Stripe not reached" in caplog.messages
    assert service.sites.subscription(code).get("ends_at") is None
    fake.fail = None
    # Only for the signed-in host.
    stranger = TestClient(dan.app, base_url=MAIN)
    assert stranger.post(f"{site}/api/site/subscription/cancel").status_code == 401
    service.sites.subscription_changed("sub_1", "canceled")
    with caplog.at_level(logging.WARNING):
        refused = dan.post(f"{site}/api/site/subscription/cancel")
    assert refused.status_code == 409
    assert "Subscription not changed" in caplog.messages


def test_when_a_subscription_ends_is_read_from_stripes_object() -> None:
    assert ends_at({"cancel_at_period_end": False, "cancel_at": None}) is None
    assert ends_at({"cancel_at": 5}) == 5.0
    assert ends_at({"cancel_at_period_end": True, "current_period_end": 7}) == 7.0
    item = {"items": {"data": [{"current_period_end": 9}]}, "cancel_at_period_end": True}
    assert ends_at(item) == 9.0
    with pytest.raises(PaymentError):
        stripe = Stripe("sk", SECRET, "price", post=lambda *a: (_ for _ in ()).throw(ValueError()))
        stripe.set_cancel("a", "sub_1", True)


def test_a_late_event_never_brings_an_ended_subscription_back(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Stripe doesn't send events in order: an `updated` (active) arriving after the deletion,
    even after a restart, leaves the site paused and unsubscribed, and a new checkout still
    brings it back (Codex's review of PR #299)."""
    _, sites, service, dan, site, code, main = subscribed(tmp_path)
    assert send(main, {**changed("canceled", "deleted"), "created": 200}).is_success
    with caplog.at_level(logging.WARNING):
        assert send(main, {**changed("active"), "created": 100}).is_success
    ignored = next(r for r in caplog.records if r.message == "Old subscription event ignored")
    assert ignored.__dict__["why"] == "ended for good"
    # The same after a restart, which reads sites.json again; and with no time on the event.
    restarted = SiteDirectory(service.home, service.host_accounts)
    assert restarted.subscription_changed("sub_1", "active") == code
    for directory in (service.sites, restarted):
        assert directory.paused(code) == SUBSCRIPTION_ENDED
        assert not directory.subscribed(code)
    assert dan.get(f"{site}/api/site/subscription").json()["subscribed"] is False
    assert dan.post(f"{site}/api/site/subscribe").is_success
    assert send(main, completed(code, "sub_2")).is_success
    assert service.sites.subscribed(code) and service.sites.paused(code) is None
    assert TestClient(sites, base_url=MAIN).get(f"{site}/api/content").status_code == 200


def test_an_older_event_changes_nothing_and_a_paid_unpaid_one_unpauses(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _, _, service, dan, site, code, main = subscribed(tmp_path)
    assert send(main, {**changed("unpaid"), "created": 300}).is_success
    assert service.sites.paused(code) == SUBSCRIPTION_ENDED
    with caplog.at_level(logging.WARNING):
        assert send(main, {**changed("past_due"), "created": 200}).is_success
    ignored = next(r for r in caplog.records if r.message == "Old subscription event ignored")
    assert ignored.__dict__["why"] == "older"
    assert service.sites.subscription(code)["status"] == "unpaid"
    # Paid at last: Stripe makes it active again, and the site comes back.
    caplog.clear()
    with caplog.at_level(logging.INFO):
        assert send(main, {**changed("active"), "created": 400}).is_success
    assert "Site unpaused" in caplog.messages
    assert service.sites.paused(code) is None and service.sites.subscribed(code)
    assert dan.get(f"{site}/api/site/subscription").json()["payment_failed"] is False
