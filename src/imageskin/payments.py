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
# Stripe's statuses of a subscription in force, as the sites keep them (R67).
IN_FORCE = ("active", "trialing", "past_due")
NOT_SET_UP = "Subscribing isn't set up on this server yet. Please tell whoever runs it."
UNAVAILABLE = "Stripe couldn't be reached just now. Please try again in a minute."

# Posts a form to Stripe's API with the secret key, and an idempotency key when one is given:
# its JSON answer.
Post = Callable[..., dict[str, Any]]
# Sends a DELETE to Stripe's API with the secret key: its JSON answer.
Delete = Callable[[str, str], dict[str, Any]]
# Sends a GET to Stripe's API with the secret key: its JSON answer.
Get = Callable[[str, str], dict[str, Any]]


class PaymentError(Exception):
    """Stripe refused or couldn't be reached; the message is safe to show."""


class CardNeeded(PaymentError):
    """Stripe has no card it can charge for the customer, or declined the one it has (R69b):
    the host gives one on Stripe's page instead."""


class BadEvent(Exception):
    """A webhook call that isn't a genuine, recent event from Stripe."""


def post_form(
    url: str, form: dict[str, str], secret_key: str, idempotency_key: str | None = None
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {secret_key}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    request = urllib.request.Request(
        url, data=urllib.parse.urlencode(form).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 (Stripe's https)
        answer: dict[str, Any] = json.loads(response.read())
    return answer


def delete_request(url: str, secret_key: str, method: str = "DELETE") -> dict[str, Any]:
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {secret_key}"}, method=method
    )
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 (Stripe's https)
        answer: dict[str, Any] = json.loads(response.read())
    return answer


def get_request(url: str, secret_key: str) -> dict[str, Any]:
    return delete_request(url, secret_key, "GET")


def _stripe_error(e: urllib.error.HTTPError) -> dict[str, Any]:
    """The `error` of Stripe's answer to a refused call, or {} when it has none."""
    try:
        found = json.loads(e.read()[:2000]).get("error")
    except (ValueError, AttributeError, OSError):
        return {}
    return found if isinstance(found, dict) else {}


@dataclass(frozen=True)
class Stripe:
    secret_key: str
    webhook_secret: str
    price_id: str
    post: Post = post_form
    clock: Callable[[], float] = time.time
    delete: Delete = delete_request
    get: Get = get_request

    def checkout(
        self,
        site: str,
        email: str,
        success_url: str,
        cancel_url: str,
        customer: str | None = None,
    ) -> str:
        """Start subscribing the site on Stripe's page: the page's address. The site is the
        session's reference, so its completion names the site it paid for. With the `customer`
        the site had (R69b), Stripe's page is for them, filled in, and no new customer is made."""
        start = time.perf_counter()
        form = {
            "mode": "subscription",
            "line_items[0][price]": self.price_id,
            "line_items[0][quantity]": "1",
            "client_reference_id": site,
            **({"customer": customer} if customer else {"customer_email": email}),
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

    def set_cancel(self, site: str, subscription_id: str, cancel: bool) -> float | None:
        """Cancel the subscription at the end of the period paid for, or keep it after all (R69):
        when it ends, or None when it is kept. Stripe then sends the subscription's change, and,
        at the end, its deletion, which pauses the site."""
        start = time.perf_counter()
        form = {"cancel_at_period_end": "true" if cancel else "false"}
        try:
            answer = self.post(f"{API}/subscriptions/{subscription_id}", form, self.secret_key)
        except urllib.error.HTTPError as e:
            logger.error(
                "Stripe refused the cancellation",
                extra={
                    "site": site,
                    "cancel": cancel,
                    "status": e.code,
                    "error": e.read()[:500].decode(errors="replace"),
                },
            )
            raise PaymentError(UNAVAILABLE) from e
        except (OSError, ValueError) as e:
            logger.error("Stripe not reached", extra={"site": site, "error": str(e)})
            raise PaymentError(UNAVAILABLE) from e
        ends = ends_at(answer) if cancel else None
        logger.info(
            "Subscription cancelled" if cancel else "Subscription kept",
            extra={
                "site": site,
                "subscription": subscription_id,
                "ends_at": ends,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return ends

    def cancel_now(self, site: str, subscription_id: str) -> None:
        """Cancel the subscription at once, as its site is deleted (R69a): nothing more is
        charged. One Stripe has no more (404) is cancelled already. PaymentError otherwise, and
        the site isn't deleted, so it is never left charging for a site that's gone."""
        start = time.perf_counter()
        try:
            answer = self.delete(f"{API}/subscriptions/{subscription_id}", self.secret_key)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                logger.warning(
                    "Subscription already gone at Stripe",
                    extra={"site": site, "subscription": subscription_id},
                )
                return
            logger.error(
                "Stripe refused to cancel at once",
                extra={
                    "site": site,
                    "subscription": subscription_id,
                    "status": e.code,
                    "error": e.read()[:500].decode(errors="replace"),
                },
            )
            raise PaymentError(UNAVAILABLE) from e
        except (OSError, ValueError) as e:
            logger.error("Stripe not reached", extra={"site": site, "error": str(e)})
            raise PaymentError(UNAVAILABLE) from e
        logger.info(
            "Subscription cancelled at once",
            extra={
                "site": site,
                "subscription": subscription_id,
                "status": answer.get("status"),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )

    def card_of(self, site: str, subscription_id: str | None) -> str | None:
        """The card the site's last subscription was paid with (R69b): its payment method's id,
        or None when Stripe has none for it, so the customer's own default is used."""
        if not subscription_id:
            return None
        try:
            found = self.get(f"{API}/subscriptions/{subscription_id}", self.secret_key)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            logger.error(
                "Stripe refused to read the subscription",
                extra={"site": site, "subscription": subscription_id, "status": e.code},
            )
            raise PaymentError(UNAVAILABLE) from e
        except (OSError, ValueError) as e:
            logger.error("Stripe not reached", extra={"site": site, "error": str(e)})
            raise PaymentError(UNAVAILABLE) from e
        card = found.get("default_payment_method")
        if isinstance(card, dict):
            card = card.get("id")
        return str(card) if card else None

    def live_subscription(self, site: str, customer: str) -> dict[str, Any] | None:
        """A subscription in force that Stripe already has for the customer and this site
        (R69b), as one made by a resume whose answer was lost: it is recorded rather than a
        second one made (Codex's review of PR #301). None when there is none."""
        query = urllib.parse.urlencode({"customer": customer, "status": "all", "limit": "100"})
        try:
            found = self.get(f"{API}/subscriptions?{query}", self.secret_key)
        except urllib.error.HTTPError as e:
            logger.error(
                "Stripe refused to list the subscriptions",
                extra={"site": site, "customer": customer, "status": e.code},
            )
            raise PaymentError(UNAVAILABLE) from e
        except (OSError, ValueError) as e:
            logger.error("Stripe not reached", extra={"site": site, "error": str(e)})
            raise PaymentError(UNAVAILABLE) from e
        for subscription in found.get("data") or []:
            if (subscription.get("metadata") or {}).get("site") == site and subscription.get(
                "status"
            ) in IN_FORCE:
                logger.warning(
                    "Subscription already made at Stripe",
                    extra={"site": site, "subscription": subscription.get("id")},
                )
                return dict(subscription)
        return None

    def resume(
        self, site: str, customer: str, card: str | None, attempt: str = ""
    ) -> dict[str, Any]:
        """Subscribe the site again for the Stripe customer it had, charging the card Stripe
        keeps for them, so the host types no card details (R69b): the new subscription, paid.
        CardNeeded when Stripe has no card it can charge or declines it; nothing is left
        unpaid, as an incomplete subscription is refused rather than made. `attempt` names this
        resume, the same each time it is tried again, so Stripe makes one subscription however
        often an answer is lost (its `Idempotency-Key`; Codex's review of PR #301)."""
        start = time.perf_counter()
        form = {
            "customer": customer,
            "items[0][price]": self.price_id,
            "items[0][quantity]": "1",
            "metadata[site]": site,
            "payment_behavior": "error_if_incomplete",
            "off_session": "true",
            **({"default_payment_method": card} if card else {}),
        }
        try:
            made = self.post(
                f"{API}/subscriptions", form, self.secret_key, f"resume-{site}-{attempt}"
            )
        except urllib.error.HTTPError as e:
            error = _stripe_error(e)
            card_problem = e.code == 402 or error.get("type") == "card_error"
            no_card = e.code == 400 and (
                error.get("param") in ("default_payment_method", "customer")
                or "payment" in str(error.get("message", "")).lower()
            )
            (logger.warning if card_problem or no_card else logger.error)(
                "Stripe refused to resume",
                extra={
                    "site": site,
                    "customer": customer,
                    "status": e.code,
                    "code": error.get("code") or error.get("decline_code"),
                    "error": str(error.get("message", ""))[:500],
                },
            )
            if card_problem or no_card:
                raise CardNeeded(UNAVAILABLE) from e
            raise PaymentError(UNAVAILABLE) from e
        except (OSError, ValueError) as e:
            logger.error("Stripe not reached", extra={"site": site, "error": str(e)})
            raise PaymentError(UNAVAILABLE) from e
        logger.info(
            "Subscription made with the card on file",
            extra={
                "site": site,
                "customer": customer,
                "subscription": made.get("id"),
                "status": made.get("status"),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return made

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


def ends_at(subscription: dict[str, Any]) -> float | None:
    """When a subscription set to cancel ends, from Stripe's subscription object: its
    `cancel_at`, or the end of the period paid for, which newer API versions keep on its item.
    None when it isn't set to end."""
    if not subscription.get("cancel_at_period_end") and not subscription.get("cancel_at"):
        return None
    items = (subscription.get("items") or {}).get("data") or [{}]
    for when in (
        subscription.get("cancel_at"),
        subscription.get("current_period_end"),
        items[0].get("current_period_end"),
    ):
        if isinstance(when, int | float):
            return float(when)
    return None


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
