"""The administrator's test accounts (roadmap R265 and R266, Milestone 31): signed in as the
administrator with a test email set, "-admin" added to any email on the host sign-up page makes
a test account for the email without it; otherwise, and anywhere else, it is an invalid email.
Every email for a test account goes to the test email (R266)."""

import json
import logging
import re
from email import message_from_bytes
from email.policy import default
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_email_change import ask
from test_email_change import signed_in as signed_in_as_ann
from test_free_trial import forget_account
from test_site_addresses import PASSWORD, served

from imageskin import admin
from imageskin.admin_settings import AdminSettings
from imageskin.admin_test_email import redirect_to_test_email
from imageskin.email_sending import Email, EmailFailed
from imageskin.hosts import (
    INVALID_EMAIL,
    TEST_ACCOUNT,
    HostAccounts,
    HostRefused,
    HostsUnreadable,
    ends_admin,
)
from imageskin.sites import TEST

pytestmark = pytest.mark.real_hosts

MAIN = "http://localhost:8000"
BOB = "bob@example.com"  # the main address's host
JOE = "joe.smith@gmail.com"
TEST_EMAIL = "larry.test@example.com"


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = admin.Secret("hash", admin.hash_password("nobody's password"))
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


def set_test_email(home: Path, address: str) -> None:
    (home / "admin-settings.json").write_text(json.dumps({"test_email": address}))


def administrator(sites: object, home: Path) -> TestClient:
    """Signed in as the administrator at the main address (and as its host, which R191 asks
    for before an admin sign-in)."""
    (home / "admin.toml").write_text('password = "secret"\n')
    browser = TestClient(sites, base_url=MAIN)  # type: ignore[arg-type]
    assert browser.post("/api/host/sign-in", json={"email": BOB, "password": PASSWORD}).is_success
    assert browser.post("/api/admin/sign-in", json={"password": "secret"}).is_success
    return browser


def sign_up(browser: TestClient, email: str) -> tuple[int, dict[str, object]]:
    response = browser.post("/api/host/sign-up", json={"email": email, "password": PASSWORD})
    return response.status_code, response.json()


def test_the_administrator_signs_up_a_test_account(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, _, service = served(tmp_path, sign_up_makes_site=True)
    home = tmp_path / "home"
    set_test_email(home, TEST_EMAIL)
    browser = administrator(sites, home)
    with caplog.at_level(logging.INFO):
        status, body = sign_up(browser, f" Joe.Smith@gmail.com{'-ADMIN'} ")
    assert status == 200, body
    # The account is the email without "-admin", which is nowhere to be seen.
    assert body["email"] == JOE
    code = str(body["site"])
    assert service.host_accounts.exists(JOE) and service.host_accounts.is_test_account(JOE)
    assert service.host_accounts.site_of(JOE) == code
    session = browser.get(f"/t/{code}/api/host/session").json()
    assert session["email"] == JOE
    for name in ("hosts.json", "sites.json"):
        assert "-admin" not in (home / name).read_text()
    assert "-admin" not in caplog.text
    signed_up = next(r for r in caplog.records if r.message == "Test account signed up")
    assert signed_up.__dict__["email"] == JOE and "duration_ms" in signed_up.__dict__
    # Its trial site is marked as a test's, and the email hasn't used up a free trial.
    assert json.loads((home / "sites.json").read_text())["sites"][code][TEST] is True
    assert not service.sites.trial_used(JOE)


def test_a_test_account_uses_up_no_free_trial_and_needs_none(tmp_path: Path) -> None:
    sites, _, service = served(tmp_path, sign_up_makes_site=True)
    home = tmp_path / "home"
    set_test_email(home, TEST_EMAIL)
    # Joe had a free trial once, and its account is gone.
    assert sign_up(TestClient(sites, base_url=MAIN), JOE)[0] == 200
    forget_account(home, JOE)
    assert service.sites.trial_used(JOE)
    # The administrator can still try sign-up with it, as often as they like.
    browser = administrator(sites, home)
    assert sign_up(browser, f"{JOE}-admin")[0] == 200
    forget_account(home, JOE)
    assert sign_up(administrator(sites, home), f"{JOE}-admin")[0] == 200
    # Reading sites.json again records no test site's host as having had a trial.
    assert not service.sites.trial_used("someone@example.com")
    saved = json.loads((home / "sites.json").read_text())
    assert len(saved["trials_used"]) == 1  # Joe's real trial only


def test_the_email_without_admin_must_be_new(tmp_path: Path) -> None:
    sites, _, _ = served(tmp_path, sign_up_makes_site=True)
    home = tmp_path / "home"
    set_test_email(home, TEST_EMAIL)
    browser = administrator(sites, home)
    status, body = sign_up(browser, f"{BOB}-admin")  # Bob is a host already
    assert status == 409 and "already signed up" in str(body["detail"])


@pytest.mark.parametrize(
    ("admin_signed_in", "test_email", "why"),
    [
        (False, TEST_EMAIL, "administrator not signed in"),
        (True, "", "no test email"),
        (True, "not-an-email", "no test email"),
    ],
)
def test_admin_is_an_invalid_email_otherwise(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    admin_signed_in: bool,
    test_email: str,
    why: str,
) -> None:
    sites, _, service = served(tmp_path, sign_up_makes_site=True)
    home = tmp_path / "home"
    set_test_email(home, test_email)
    browser = administrator(sites, home) if admin_signed_in else TestClient(sites, base_url=MAIN)
    with caplog.at_level(logging.INFO):
        status, body = sign_up(browser, f"{JOE}-admin")
    assert (status, body) == (400, {"detail": INVALID_EMAIL})
    refused = next(r for r in caplog.records if r.message == "Test sign-up refused")
    assert refused.__dict__["why"] == why
    assert JOE not in caplog.text and "-admin" not in caplog.text
    assert not service.host_accounts.exists(JOE)
    assert not service.host_accounts.exists(f"{JOE}-admin")


def test_admin_after_signing_out_as_the_administrator(tmp_path: Path) -> None:
    sites, _, _ = served(tmp_path, sign_up_makes_site=True)
    home = tmp_path / "home"
    set_test_email(home, TEST_EMAIL)
    browser = administrator(sites, home)
    browser.post("/api/admin/sign-out")
    assert sign_up(browser, f"{JOE}-admin") == (400, {"detail": INVALID_EMAIL})


def test_admin_on_a_sites_own_address_is_an_invalid_email(tmp_path: Path) -> None:
    sites, _, _ = served(tmp_path, sign_up_makes_site=True)
    home = tmp_path / "home"
    set_test_email(home, TEST_EMAIL)
    administrator(sites, home)
    elsewhere = TestClient(sites, base_url="http://a.localhost:8000")
    status, _ = sign_up(elsewhere, f"{JOE}-admin")
    assert status in (400, 403)  # a site's own address takes no sign-ups at all


def test_admin_is_an_invalid_email_at_sign_in_and_forgot_password(tmp_path: Path) -> None:
    sites, _, _ = served(tmp_path, sign_up_makes_site=True)
    home = tmp_path / "home"
    set_test_email(home, TEST_EMAIL)
    browser = administrator(sites, home)
    assert sign_up(browser, f"{JOE}-admin")[0] == 200
    signing_in = browser.post(
        "/api/host/sign-in", json={"email": f"{JOE}-admin", "password": PASSWORD}
    )
    assert signing_in.status_code == 401 and signing_in.json()["detail"] == INVALID_EMAIL
    forgot = browser.post("/api/host/forgot", json={"email": f"{JOE}-admin"})
    assert forgot.status_code == 400 and forgot.json()["detail"] == INVALID_EMAIL
    assert not list((home / "outbox").glob("*.eml")) or all(
        "Set it here" not in f.read_text() for f in (home / "outbox").glob("*.eml")
    )


def test_admin_is_an_invalid_email_when_changing_the_email(tmp_path: Path) -> None:
    sites, _, _ = served(tmp_path)
    browser = signed_in_as_ann(sites)
    assert ask(browser, "ann.new@example.com-admin") == (400, INVALID_EMAIL)


def test_the_accounts_refuse_admin_at_sign_up_too(tmp_path: Path) -> None:
    accounts = HostAccounts(tmp_path)
    with pytest.raises(HostRefused, match=INVALID_EMAIL):
        accounts.sign_up(f"{JOE}-admin", PASSWORD, "127.0.0.1", test_account=True)
    accounts.sign_up(JOE, PASSWORD, "127.0.0.1", test_account=True)
    assert accounts.is_test_account(JOE)
    assert json.loads((tmp_path / "hosts.json").read_text())["hosts"][JOE][TEST_ACCOUNT] is True
    accounts.sign_up(BOB, PASSWORD, "127.0.0.1")
    assert not accounts.is_test_account(BOB) and not accounts.is_test_account("no@one.com")


@pytest.mark.parametrize(
    ("email", "ends"),
    [
        ("a@b.com-admin", True),
        (" A@B.COM-Admin ", True),
        ("admin@b.com", False),
        ("a@b-admin.com", False),
    ],
)
def test_ends_admin(email: str, ends: bool) -> None:
    assert ends_admin(email) is ends


# Emails for a test account go to the test email (R266).


def outbox(home: Path) -> list[dict[str, str]]:
    """Every email written to the outbox, oldest first: who to, the subject and the words."""
    files = sorted((home / "outbox").glob("*.eml"), key=lambda p: p.stat().st_mtime_ns)
    mails = [message_from_bytes(f.read_bytes(), policy=default) for f in files]
    return [
        {"to": m["To"], "subject": m["Subject"], "text": m.get_body().get_content()}  # type: ignore[union-attr]
        for m in mails
    ]


def link_in(text: str, path: str) -> str:
    found = re.search(rf"https?://\S+{re.escape(path)}\S*", text)
    assert found is not None, text
    return found.group(0)


def joe_test_account(tmp_path: Path) -> tuple[object, Path, TestClient, str]:
    """Joe's test account, signed up by the administrator: the app, its home, the browser
    and the trial site's code."""
    sites, _, _ = served(tmp_path, sign_up_makes_site=True)
    home = tmp_path / "home"
    set_test_email(home, TEST_EMAIL)
    browser = administrator(sites, home)
    status, body = sign_up(browser, f"{JOE}-admin")
    assert status == 200, body
    return sites, home, browser, str(body["site"])


def test_the_confirmation_goes_to_the_test_email_and_confirms_the_account(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        _, home, browser, code = joe_test_account(tmp_path)
    sent = outbox(home)
    assert [m["to"] for m in sent] == [TEST_EMAIL]  # nothing to Joe
    assert sent[0]["text"].startswith(f"This is for the test account {JOE}.\n\n")
    redirected = next(r for r in caplog.records if r.message == "Email sent to the test email")
    assert redirected.__dict__["test_account"] == JOE
    assert redirected.__dict__["kind"] == "sign-up confirmation"
    assert "duration_ms" in redirected.__dict__
    assert browser.get(f"/t/{code}/api/host/me").status_code == 401  # not confirmed yet
    browser.get(link_in(sent[0]["text"], "/api/host/confirm/"), follow_redirects=False)
    assert browser.get(f"/t/{code}/api/host/me").status_code == 200


def test_forgot_password_goes_to_the_test_email(tmp_path: Path) -> None:
    sites, home, _, _ = joe_test_account(tmp_path)
    TestClient(sites, base_url=MAIN).post("/api/host/forgot", json={"email": JOE})  # type: ignore[arg-type]
    last = outbox(home)[-1]
    assert last["to"] == TEST_EMAIL and f"test account {JOE}" in last["text"]
    assert "Set it here" in last["text"]


def test_both_emails_of_changing_the_email_go_to_the_test_email(tmp_path: Path) -> None:
    _, home, browser, code = joe_test_account(tmp_path)
    browser.get(link_in(outbox(home)[0]["text"], "/api/host/confirm/"), follow_redirects=False)
    asked = browser.post(
        f"/t/{code}/api/host/email",
        json={"new_email": "joe.new@gmail.com", "password": PASSWORD},
    )
    assert asked.status_code == 200, asked.text
    change = outbox(home)[-1]
    assert change["to"] == TEST_EMAIL and f"test account {JOE}" in change["text"]
    browser.get(link_in(change["text"], "/api/host/email/confirm/"), follow_redirects=False)
    changed = outbox(home)[-1]
    assert changed["to"] == TEST_EMAIL and "was changed" in changed["text"]
    assert "test account joe.new@gmail.com" in changed["text"]
    assert all(m["to"] == TEST_EMAIL for m in outbox(home))  # never Joe's old or new address


def test_no_test_email_when_sending_sends_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, home, _, _ = joe_test_account(tmp_path)
    before = len(outbox(home))
    set_test_email(home, "")
    with caplog.at_level(logging.INFO):
        TestClient(sites, base_url=MAIN).post("/api/host/forgot", json={"email": JOE})  # type: ignore[arg-type]
    assert len(outbox(home)) == before
    failed = next(r for r in caplog.records if r.message == "Email for a test account not sent")
    assert failed.__dict__["why"] == "no test email"


def test_other_hosts_emails_are_unchanged(tmp_path: Path) -> None:
    sites, home, _, _ = joe_test_account(tmp_path)
    TestClient(sites, base_url=MAIN).post("/api/host/forgot", json={"email": BOB})  # type: ignore[arg-type]
    last = outbox(home)[-1]
    assert last["to"] == BOB and "test account" not in last["text"]


def test_unreadable_accounts_send_nothing(caplog: pytest.LogCaptureFixture) -> None:
    def unreadable(_: str) -> bool:
        raise HostsUnreadable()

    redirect = redirect_to_test_email(unreadable, lambda: AdminSettings(test_email=TEST_EMAIL))
    with pytest.raises(EmailFailed):
        redirect(Email(JOE, "Hello", "Words", "test"))
    assert "Email not sent: the accounts can't be read" in caplog.text
    plain = Email(BOB, "Hello", "Words", "test")
    assert redirect_to_test_email(lambda _: False, lambda: AdminSettings())(plain) is plain
