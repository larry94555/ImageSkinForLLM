"""Payment and subscribing (roadmap R67): a site's host subscribes on Stripe's page, and the
server records the subscription from Stripe's signed events, never seeing card details."""

import dataclasses
import hashlib
import hmac
import io
import json
import logging
import time
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_customer_sign_up import confirmation_link, sign_up
from test_site_addresses import lesson, with_hosts

from imageskin import admin, payments
from imageskin.app import create_app
from imageskin.config import ConfigError, load_settings
from imageskin.payments import (
    NOT_SET_UP,
    SUBSCRIPTION,
    UNAVAILABLE,
    BadEvent,
    PaymentError,
    Stripe,
    stripe_from_environment,
)
from imageskin.sites import Service, SiteApps, site_home, site_matcher
from imageskin.uploads import PhotoResult

pytestmark = pytest.mark.real_hosts

DAN = "dan@example.com"
MAIN = "http://localhost:8000"
SECRET = "whsec_test"


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = admin.Secret("hash", admin.hash_password("nobody's password"))
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


class FakeStripe:
    """Stripe's API as a list of what was posted, answering with a Checkout Session."""

    def __init__(self, fail: Exception | None = None) -> None:
        self.posted: list[tuple[str, dict[str, str], str]] = []
        self.fail = fail
        # Stripe keeps what an idempotency key made, and answers it again (R257).
        self.made: dict[str, dict[str, Any]] = {}
        self.keys: list[str | None] = []
        self.lose_answer = False  # Stripe makes the checkout, but its answer is lost
        self.deleted: list[str] = []

    def __call__(
        self, url: str, form: dict[str, str], key: str, idempotency: str | None = None
    ) -> dict[str, Any]:
        self.posted.append((url, form, key))
        self.keys.append(idempotency)
        if self.fail is not None:
            raise self.fail
        number = len(self.made) + 1
        session = {
            "id": f"cs_test_{number}",
            "url": f"https://checkout.stripe.com/c/pay/cs_test_{number}",
        }
        if idempotency is not None:
            session = self.made.setdefault(idempotency, session)
        if self.lose_answer:
            raise OSError("the answer was lost")
        return session

    def delete(self, url: str, key: str) -> dict[str, Any]:
        self.deleted.append(url)
        return {"id": url.rsplit("/", 1)[1], "status": "canceled"}


# The service last served, whose sites' tokens a completed checkout carries, as Stripe sends back
# the metadata each checkout was started with (R257).
SERVED: list[Service] = []


def served(tmp_path: Path, stripe: Stripe | None) -> tuple[SiteApps, dict[str, FastAPI], Service]:
    home = tmp_path / "home"
    service = dataclasses.replace(with_hosts(home), payments=stripe)
    SERVED[:] = [service]
    made: dict[str, FastAPI] = {}

    def make(site: str) -> FastAPI:
        made[site] = create_app(
            site_home(site, home),
            check_photo=lambda p: PhotoResult([], 80),
            prepare_voice=lambda: None,
            prepare_face=lambda photo, progress: None,
            render_clip=lambda photo, text, output: None,
            ask_llm=MagicMock(),
            read_pdf=lesson,
            build_wiki=MagicMock(),
            service=service,
            site=site,
            sign_up_makes_site=True,
        )
        return made[site]

    return SiteApps(make, site_matcher(service.sites, "me0.ai")), made, service


def a_trial(sites: SiteApps, home: Path) -> tuple[TestClient, str]:
    """Dan's trial site, signed up and confirmed: his browser and the site's path."""
    dan = TestClient(sites, base_url=MAIN)
    code = str(sign_up(dan, DAN)["site"])
    dan.get(confirmation_link(home), follow_redirects=False)
    return dan, f"/t/{code}"


def signed(
    event: dict[str, Any], at: float | None = None, secret: str = SECRET
) -> tuple[bytes, str]:
    body = json.dumps(event).encode()
    t = int(time.time() if at is None else at)
    v1 = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return body, f"t={t},v1={v1}"


def send(browser: TestClient, event: dict[str, Any], **kw: Any) -> Any:
    body, signature = signed(event, **kw)
    return browser.post(
        "/api/payments/stripe/events", content=body, headers={"stripe-signature": signature}
    )


def completed(code: str, subscription: str = "sub_1", token: str | None = None) -> dict[str, Any]:
    """Stripe's event for a paid checkout of the site `code`, with the token its checkout was
    started with: the site's own, unless another is given."""
    if token is None and SERVED:
        token = SERVED[0].sites.token_of(code)
    return {
        "id": "evt_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "mode": "subscription",
                "client_reference_id": code,
                "payment_status": "paid",
                "subscription": subscription,
                "customer": "cus_1",
                "metadata": {"site": code, **({"site_token": token} if token else {})},
            }
        },
    }


def test_a_host_subscribes_on_stripes_page_and_the_event_records_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fake = FakeStripe()
    sites, _, service = served(tmp_path, Stripe("sk_test", SECRET, "price_5gb", fake))
    dan, site = a_trial(sites, tmp_path / "home")
    code = site.removeprefix("/t/")
    assert dan.get(f"{site}/api/site/subscription").json() == {
        "available": True,
        "price": SUBSCRIPTION,
        "status": None,
        "subscribed": False,
        "ends_at": None,
        "payment_failed": False,
        "subdomain": None,
        "pick_subdomain": False,
        "change_subdomain": False,
        "deletable": True,
        "days_before_deleting": 30,
        "deletes_at": None,
        "resumable": False,
        "restarted": False,
        "added": False,
    }
    # Cancelled first, so the payment brings the paused site back (R69's subscribe again).
    assert dan.post(f"{site}/api/site/cancel").is_success
    with caplog.at_level(logging.INFO):
        started = dan.post(f"{site}/api/site/subscribe")
    assert started.json() == {"url": "https://checkout.stripe.com/c/pay/cs_test_1"}
    assert "Checkout started" in caplog.messages
    [(url, form, key)] = fake.posted
    assert url == "https://api.stripe.com/v1/checkout/sessions" and key == "sk_test"
    assert form["mode"] == "subscription" and form["line_items[0][price]"] == "price_5gb"
    assert form["client_reference_id"] == code and form["customer_email"] == DAN
    assert form["success_url"] == f"{MAIN}{site}/#/settings" == form["cancel_url"]
    # No card details pass through the server: only Stripe's event says it is paid.
    assert service.sites.paused(code) == "cancelled"
    main = TestClient(sites, base_url=MAIN)
    with caplog.at_level(logging.INFO):
        assert send(main, completed(code)).json() == {"received": True}
    assert "Stripe event" in caplog.messages and "Site subscribed" in caplog.messages
    assert service.sites.paused(code) is None and service.sites.subscribed(code)
    session = dan.get(f"{site}/api/host/session").json()
    assert session["subscribed"] is True and "trial" not in session and "paused" not in session
    assert dan.get(f"{site}/api/site/subscription").json()["status"] == "active"
    # Visitors use it again.
    assert TestClient(sites, base_url=MAIN).get(f"{site}/api/content").status_code == 200
    # The same event again changes nothing; subscribing again, or cancelling the trial, is refused.
    assert send(main, completed(code)).is_success
    assert dan.post(f"{site}/api/site/subscribe").json()["detail"] == (
        "This site is subscribed already."
    )
    assert dan.post(f"{site}/api/site/cancel").status_code == 409
    assert len(fake.posted) == 1


def test_a_changed_subscription_is_recorded(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, service = served(tmp_path, Stripe("sk_test", SECRET, "price_5gb", FakeStripe()))
    dan, site = a_trial(sites, tmp_path / "home")
    code = site.removeprefix("/t/")
    main = TestClient(sites, base_url=MAIN)
    send(main, completed(code, "sub_9"))
    changed = {
        "id": "evt_2",
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_9", "status": "canceled"}},
    }
    with caplog.at_level(logging.INFO):
        assert send(main, changed).is_success
    record = next(r for r in caplog.records if r.message == "Subscription changed")
    assert record.__dict__["site"] == code and record.__dict__["status"] == "canceled"
    assert not service.sites.subscribed(code)
    assert service.sites.subscription(code) == {
        **(service.sites.subscription(code) or {}),
        "id": "sub_9",
        "customer": "cus_1",
        "status": "canceled",
    }
    # A subscription no site has, and events not about subscribing, are only logged.
    other = {**changed, "data": {"object": {"id": "sub_x", "status": "active"}}}
    assert send(main, other).is_success
    assert send(main, {"id": "evt_3", "type": "invoice.paid", "data": {"object": {}}}).is_success
    unpaid = completed(code, "sub_10")
    unpaid["data"]["object"]["payment_status"] = "unpaid"
    assert send(main, unpaid).is_success and not service.sites.subscribed(code)
    gone = completed("nosuchsite", "sub_11")
    with caplog.at_level(logging.ERROR):
        assert send(main, gone).is_success
    assert "Subscription for no site" in caplog.messages


def test_an_event_not_signed_by_stripe_is_refused(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, service = served(tmp_path, Stripe("sk_test", SECRET, "price_5gb", FakeStripe()))
    _, site = a_trial(sites, tmp_path / "home")
    code = site.removeprefix("/t/")
    main = TestClient(sites, base_url=MAIN)
    with caplog.at_level(logging.WARNING):
        forged = send(main, completed(code), secret="whsec_someone_else")
        old = send(main, completed(code), at=time.time() - 600)
        none = main.post("/api/payments/stripe/events", content=b"{}")
    assert forged.status_code == old.status_code == none.status_code == 400
    whys = [r.__dict__["why"] for r in caplog.records if r.message == "Stripe event refused"]
    assert whys == [
        "the signature doesn't match",
        "the signature is too old",
        "no time in the signature",
    ]
    assert not service.sites.subscribed(code)
    # Only at the main address: a site's own address has no such route.
    assert main.post(f"{site}/api/payments/stripe/events", content=b"{}").status_code in (404, 405)


def test_a_signed_body_that_isnt_an_event_is_refused() -> None:
    stripe = Stripe("sk", SECRET, "price", FakeStripe())
    body, signature = signed({"no": "type"})
    with pytest.raises(BadEvent, match="not an event"):
        stripe.event(body, signature)


def test_subscribing_without_stripe_set_up_says_so(tmp_path: Path) -> None:
    sites, _, _ = served(tmp_path, None)
    dan, site = a_trial(sites, tmp_path / "home")
    assert dan.get(f"{site}/api/site/subscription").json()["available"] is False
    refused = dan.post(f"{site}/api/site/subscribe")
    assert refused.status_code == 503 and refused.json()["detail"] == NOT_SET_UP
    events = TestClient(sites, base_url=MAIN).post("/api/payments/stripe/events", content=b"{}")
    assert events.status_code == 503
    # Signed out, nothing is offered.
    assert TestClient(sites, base_url=MAIN).post(f"{site}/api/site/subscribe").status_code == 401


@pytest.mark.parametrize(
    "fail",
    [
        urllib.error.HTTPError(
            "u", 400, "Bad Request", Message(), io.BytesIO(b'{"error": "no such price"}')
        ),
        urllib.error.URLError("no network"),
    ],
)
def test_stripe_unreachable_or_refusing_says_try_again(
    tmp_path: Path, fail: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, _ = served(tmp_path, Stripe("sk", SECRET, "price", FakeStripe(fail)))
    dan, site = a_trial(sites, tmp_path / "home")
    with caplog.at_level(logging.ERROR):
        answer = dan.post(f"{site}/api/site/subscribe")
    assert answer.status_code == 502 and answer.json()["detail"] == UNAVAILABLE
    assert {"Stripe refused the checkout", "Stripe not reached"} & set(caplog.messages)
    with pytest.raises(PaymentError):
        Stripe("sk", SECRET, "price", FakeStripe(fail)).checkout("a", DAN, "u", "u")


def test_stripe_is_set_up_from_the_environment_only(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    for name in (
        payments.SECRET_KEY_VARIABLE,
        payments.WEBHOOK_SECRET_VARIABLE,
        payments.PRICE_VARIABLE,
    ):
        monkeypatch.delenv(name, raising=False)
    assert stripe_from_environment() is None
    monkeypatch.setenv(payments.PRICE_VARIABLE, "price_5gb")
    with caplog.at_level(logging.WARNING):
        assert stripe_from_environment() is None
    assert "Subscribing not set up: a Stripe setting is missing" in caplog.messages
    monkeypatch.setenv(payments.SECRET_KEY_VARIABLE, "sk_live_x")
    monkeypatch.setenv(payments.WEBHOOK_SECRET_VARIABLE, "whsec_x")
    stripe = stripe_from_environment()
    assert (
        stripe is not None and stripe.price_id == "price_5gb" and stripe.secret_key == "sk_live_x"
    )
    # Never in a tracked file (Larry, 2026-11-03): config.toml with the price is refused, saying
    # where it goes.
    config = tmp_path / "config.toml"
    config.write_text('stripe_price_id = "price_5gb"\n')
    with pytest.raises(ConfigError, match="IMAGESKIN_STRIPE_PRICE_ID"):
        load_settings(config)


def test_the_api_is_called_with_the_secret_key_and_the_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Any] = []

    class Answer(io.BytesIO):
        def __enter__(self) -> "Answer":
            return self

        def __exit__(self, *_: object) -> None:
            pass

    def urlopen(request: Any, timeout: float) -> Answer:
        seen.append((request.full_url, request.data, request.headers, timeout))
        return Answer(b'{"id": "cs_1", "url": "https://checkout.stripe.com/x"}')

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    answer = payments.post_form("https://api.stripe.com/v1/x", {"a": "b c"}, "sk_test")
    assert answer["url"] == "https://checkout.stripe.com/x"
    [(url, data, headers, timeout)] = seen
    assert url == "https://api.stripe.com/v1/x" and data == b"a=b+c" and timeout == 20
    assert headers["Authorization"] == "Bearer sk_test"


def test_a_replayed_checkout_doesnt_bring_back_a_cancelled_subscription(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Codex's review of PR #293: Stripe sends events at least once and in any order, so the
    # first checkout sent again after the cancellation must leave it cancelled.
    stripe = Stripe("sk_test", SECRET, "price_5gb", FakeStripe())
    sites, _, service = served(tmp_path, stripe)
    _, site = a_trial(sites, tmp_path / "home")
    code = site.removeprefix("/t/")
    main = TestClient(sites, base_url=MAIN)
    send(main, completed(code))
    deleted = {
        "id": "evt_2",
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_1", "status": "canceled"}},
    }
    assert send(main, deleted).is_success
    with caplog.at_level(logging.WARNING):
        assert send(main, completed(code)).is_success
    assert "Old checkout ignored" in caplog.messages
    assert not service.sites.subscribed(code)
    assert (service.sites.subscription(code) or {})["status"] == "canceled"

    # The same after a restart: a new service reads sites.json afresh.
    sites, _, service = served(tmp_path, stripe)
    main = TestClient(sites, base_url=MAIN)
    assert send(main, completed(code)).is_success
    assert (service.sites.subscription(code) or {})["status"] == "canceled"

    # A new subscription, from subscribing again, is recorded, and then the old one stays old.
    assert send(main, completed(code, "sub_2")).is_success
    assert service.sites.subscribed(code)
    assert (service.sites.subscription(code) or {})["id"] == "sub_2"
    assert send(main, completed(code)).is_success
    assert (service.sites.subscription(code) or {})["id"] == "sub_2"
