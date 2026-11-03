"""Deleting a site (roadmap R69a, feature 64): never at once, and nothing a host paid for is
taken away (Larry, 2026-11-03). Cancelling, or Delete site in Settings, only means no more
payment is expected: a subscribed site keeps working until the end of the period paid for, then
pauses (R69); a site with no paid time left, such as a free trial, pauses now. A site is deleted
once it has been paused for the admin settings' days, 30 to begin with, counted from when it
paused, not from when it was cancelled.

When a paused site is deleted, a subscription Stripe still keeps for it (one `unpaid` after
failed renewals) is cancelled first, so it is never charged for again; when Stripe can't be
reached nothing is deleted. Then the site goes: its record, its folder and everything in it.
Its subdomain is free again, a trial's code is never given again, and its host's account is
kept so they can sign in and resume (R69b, feature 213). Only Stripe keeps the billing records.
"""

import logging
import threading
import time
from collections.abc import Callable

from imageskin.admin_settings import DELETE_DAYS
from imageskin.payments import NOT_SET_UP, PaymentError, Stripe
from imageskin.sites import FINAL, SiteDirectory

logger = logging.getLogger(__name__)

DAY_S = 24 * 60 * 60
SWEEP_EVERY_S = 60 * 60  # how often the server looks for sites paused too long
PAUSED_TOO_LONG = "paused too long"


def cancel_now(sites: SiteDirectory, payments: Stripe | None, name: str) -> None:
    """Cancel the deleted site's subscription with Stripe, if Stripe still keeps one for it.
    PaymentError when Stripe can't. Only for a site paused for the admin settings' days, which
    has no paid time left."""
    found = sites.subscription(name)
    if found and found.get("id") and found.get("status") not in FINAL:
        if payments is None:
            logger.error(
                "Site not deleted",
                extra={"site": name, "why": "subscription and Stripe not set up"},
            )
            raise PaymentError(NOT_SET_UP)
        payments.cancel_now(name, str(found["id"]))


def delete_site(sites: SiteDirectory, payments: Stripe | None, name: str, why: str) -> bool:
    """Cancel the site's subscription with Stripe, if Stripe still keeps one for it, then delete
    the site: whether it was there. PaymentError, with nothing deleted, when Stripe can't
    cancel it."""
    cancel_now(sites, payments, name)
    return sites.delete(name, why)


def delete_paused(
    sites: SiteDirectory,
    payments: Stripe | None,
    now: Callable[[], float] = time.time,
    days: int = DELETE_DAYS,
) -> list[str]:
    """Delete each site paused for `days` or more (R69a): the ones deleted. One whose
    subscription Stripe can't cancel now is kept, and tried again at the next sweep."""
    start = time.perf_counter()
    deleted = []
    for name in sites.paused_since(now() - days * DAY_S):
        try:
            if delete_site(sites, payments, name, PAUSED_TOO_LONG):
                deleted.append(name)
        except PaymentError:
            logger.warning("Paused site kept for now", extra={"site": name, "why": "Stripe"})
        except OSError as e:
            logger.error("Paused site not deleted", extra={"site": name, "error": str(e)})
    if deleted:
        logger.info(
            "Paused sites deleted",
            extra={
                "sites": deleted,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
    return deleted


def keep_deleting_paused(
    sites: SiteDirectory,
    payments: Stripe | None,
    every_s: float = SWEEP_EVERY_S,
    now: Callable[[], float] = time.time,
    days: Callable[[], int] = lambda: DELETE_DAYS,
) -> threading.Thread:
    """Look for sites paused too long now and then every `every_s` seconds, in a thread of its
    own for as long as the server runs; `days` reads the admin settings' days each time, so a
    change applies at the next sweep."""

    def sweep() -> None:
        while True:
            try:
                delete_paused(sites, payments, now, days())
            except Exception:
                logger.exception("Paused sites sweep failed")
            time.sleep(every_s)

    thread = threading.Thread(target=sweep, name="delete-paused", daemon=True)
    thread.start()
    return thread
