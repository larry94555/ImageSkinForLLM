"""Emails for the administrator's test accounts go to the test email (roadmap R266, Milestone 31).

A test account (R265) is a host signed up by the administrator with "-admin", for any address,
real or made up. Every email meant for one goes instead to the test email set in
`admin-settings.json` (R264), so the account's own address never gets anything. This is done
in one place, as the mailer sends, so every email, from the sign-up confirmation to any added
later, is covered with no change to each.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import replace

from imageskin.admin_settings import AdminSettings
from imageskin.email_sending import FAILED, Email, EmailFailed
from imageskin.hosts import HostsUnreadable

logger = logging.getLogger(__name__)


def for_test_account(account: str, text: str) -> str:
    """The email's words, starting with the test account they are for."""
    return f"This is for the test account {account}.\n\n{text}"


def redirect_to_test_email(
    is_test_account: Callable[[str], bool], settings: Callable[[], AdminSettings]
) -> Callable[[Email], Email]:
    """What the mailer sends in place of `email`: the same, unless it is for a test account,
    whose email goes to the test email instead. EmailFailed, and nothing sent, when it is for a
    test account and no test email is set, or when the accounts can't be read to tell."""

    def redirect(email: Email) -> Email:
        start = time.perf_counter()
        account = email.account or email.to
        try:
            test = is_test_account(account)
        except HostsUnreadable as e:
            # Never sent where it might reach a test account's own address.
            logger.error(
                "Email not sent: the accounts can't be read",
                extra={"kind": email.kind, "error": str(e)},
            )
            raise EmailFailed(FAILED) from e
        if not test:
            return email
        test_email = settings().test_email
        if not test_email:
            logger.error(
                "Email for a test account not sent",
                extra={"test_account": account, "kind": email.kind, "why": "no test email"},
            )
            raise EmailFailed(FAILED)
        logger.info(
            "Email sent to the test email",
            extra={
                "test_account": account,
                "kind": email.kind,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return replace(email, to=test_email, text=for_test_account(account, email.text))

    return redirect
