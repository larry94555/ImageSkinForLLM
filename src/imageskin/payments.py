"""Subscribing through Stripe Checkout (roadmap R67, items 63 and 164).

A site's host subscribes on Stripe's own page, so card details and invoices stay with Stripe and
never reach this server. The server makes the Checkout Session and records the subscription from
the events Stripe sends to its webhook, each checked by its signature.

Set up with the monthly price of Milestone 30's subscription, the secret key and the webhook's
signing secret in the IMAGESKIN_STRIPE_PRICE_ID, IMAGESKIN_STRIPE_SECRET_KEY and
IMAGESKIN_STRIPE_WEBHOOK_SECRET environment variables only: `deploy/.env` on the hosted site,
which isn't checked in, so no tracked file holds them and `git pull` never meets a local edit
(Larry, 2026-11-03). Without all three, subscribing says it isn't set up yet.
"""

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

SECRET_KEY_VARIABLE = "IMAGESKIN_STRIPE_SECRET_KEY"
WEBHOOK_SECRET_VARIABLE = "IMAGESKIN_STRIPE_WEBHOOK_SECRET"
# The price, in .env beside the secrets, never in a tracked file.
PRICE_VARIABLE = "IMAGESKIN_STRIPE_PRICE_ID"
API = "https://api.stripe.com/v1"
# What is sold (Milestone 30, R201): the price itself is the one set up in Stripe, whose ID is
# IMAGESKIN_STRIPE_PRICE_ID, which should match these words.
SUBSCRIPTION = "5 GB for $1.99 a month"
# How old an event's signature may be, as Stripe's own libraries allow, so a recorded one can't
# be sent again later.
TOLERANCE_S = 5 * 60
NOT_SET_UP = "Subscribing isn't set up on this server yet. Please tell whoever runs it."
UNAVAILABLE = "Stripe couldn't be reached just now. Please try again in a minute."

# Posts a form to Stripe's API with the secret key: its JSON answer.
Post = Callable[[str, dict[str, str], str], dict[str, Any]]


class PaymentError(Exception):
    """Stripe refused or couldn't be reached; the message is safe to show."""


class BadEvent(Exception):
    """A webhook call that isn't a genuine, recent event from Stripe."""


def post_form(url: str, form: dict[str, str], secret_key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(form).encode(),
        headers={"Authorization": f"Bearer {secret_key}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 (Stripe's https)
        answer: dict[str, Any] = json.loads(response.read())
    return answer


@dataclass(frozen=True)
class Stripe:
    secret_key: str
    webhook_secret: str
    price_id: str
    post: Post = post_form
    clock: Callable[[], float] = time.time

    def checkout(self, site: str, email: str, success_url: str, cancel_url: str) -> str:
        """Start subscribing the site on Stripe's page: the page's address. The site is the
        session's reference, so its completion names the site it paid for."""
        start = time.perf_counter()
        form = {
            "mode": "subscription",
            "line_items[0][price]": self.price_id,
            "line_items[0][quantity]": "1",
            "client_reference_id": site,
            "customer_email": email,
            "metadata[site]": site,
            "subscription_data[metadata][site]": site,
            "success_url": success_url,
            "cancel_url": cancel_url,
        }
        try:
            session = self.post(f"{API}/checkout/sessions", form, self.secret_key)
        except urllib.error.HTTPError as e:
            logger.error(
                "Stripe refused the checkout",
                extra={
                    "site": site,
                    "status": e.code,
                    "error": e.read()[:500].decode(errors="replace"),
                },
            )
            raise PaymentError(UNAVAILABLE) from e
        except (OSError, ValueError) as e:
            logger.error("Stripe not reached", extra={"site": site, "error": str(e)})
            raise PaymentError(UNAVAILABLE) from e
        logger.info(
            "Checkout started",
            extra={
                "site": site,
                "session": session.get("id"),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return str(session["url"])

    def event(self, body: bytes, signature: str | None) -> dict[str, Any]:
        """The event Stripe sent, once its Stripe-Signature header is checked: signed with the
        webhook's secret, recently. BadEvent otherwise."""
        parts: dict[str, list[str]] = {}
        for item in (signature or "").split(","):
            key, _, value = item.strip().partition("=")
            parts.setdefault(key, []).append(value)
        try:
            signed_at = int(parts["t"][0])
        except (KeyError, ValueError) as e:
            raise BadEvent("no time in the signature") from e
        expected = hmac.new(
            self.webhook_secret.encode(), f"{signed_at}.".encode() + body, hashlib.sha256
        ).hexdigest()
        if not any(hmac.compare_digest(expected, v) for v in parts.get("v1", [])):
            raise BadEvent("the signature doesn't match")
        if abs(self.clock() - signed_at) > TOLERANCE_S:
            raise BadEvent("the signature is too old")
        try:
            event: dict[str, Any] = json.loads(body)
            event["type"], event["data"]["object"]  # noqa: B018 (checked to be there)
        except (ValueError, KeyError, TypeError) as e:
            raise BadEvent("not an event") from e
        return event


def stripe_from_environment() -> Stripe | None:
    """Stripe as the environment sets it up, or None when any part is missing."""
    price_id = os.environ.get(PRICE_VARIABLE, "").strip()
    secret_key = os.environ.get(SECRET_KEY_VARIABLE, "")
    webhook_secret = os.environ.get(WEBHOOK_SECRET_VARIABLE, "")
    if not (price_id and secret_key and webhook_secret):
        if price_id or secret_key or webhook_secret:
            logger.warning(
                "Subscribing not set up: a Stripe setting is missing",
                extra={
                    "price_id": bool(price_id),
                    "secret_key": bool(secret_key),
                    "webhook_secret": bool(webhook_secret),
                },
            )
        return None
    return Stripe(secret_key, webhook_secret, price_id)
