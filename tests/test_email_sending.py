"""Sending email through a mail service, or to the outbox without one (roadmap R215)."""

import email
import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import pytest

from imageskin import cli
from imageskin.config import ConfigError, load_settings
from imageskin.email_sending import (
    FAILED,
    PASSWORD_VARIABLE,
    Email,
    EmailFailed,
    Mailer,
    MailService,
    connect,
    mail_service,
)

SECRET_LINK = "https://me0.ai/confirm/s3cret"
EMAIL = Email(
    "ann@example.com", "Confirm your email", f"Open {SECRET_LINK}", "sign-up confirmation"
)
SERVICE = MailService("smtp.example.com", 587, "apikey", "me0.ai <noreply@me0.ai>", "pw")


class FakeSmtp:
    def __init__(self, fail: list[Exception]) -> None:
        self.fail = fail
        self.logins: list[tuple[str, str]] = []
        self.sent: list[EmailMessage] = []
        self.quit_called = 0

    def login(self, user: str, password: str) -> None:
        self.logins.append((user, password))

    def send_message(self, msg: EmailMessage) -> None:
        if self.fail:
            raise self.fail.pop(0)
        self.sent.append(msg)

    def quit(self) -> None:
        self.quit_called += 1


def mailer(tmp_path: Path, smtp: FakeSmtp, service: MailService = SERVICE) -> Mailer:
    sleeps: list[float] = []
    return Mailer(tmp_path, service, connect=lambda s: smtp, sleep=sleeps.append)


def test_with_no_mail_service_each_email_is_written_to_the_outbox(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        written = Mailer(tmp_path, None).send(EMAIL)
    assert written is not None and written.parent == tmp_path / "outbox"
    assert written.name.endswith("-sign-up-confirmation-" + written.name[-12:])
    msg = email.message_from_bytes(written.read_bytes())
    assert msg["To"] == "ann@example.com" and msg["Subject"] == "Confirm your email"
    assert SECRET_LINK in msg.get_payload(decode=True).decode()  # type: ignore[union-attr]
    record = next(r for r in caplog.records if r.message == "Email written to outbox")
    assert record.__dict__["file"] == str(written)
    assert SECRET_LINK not in caplog.text  # never the words or a link


def test_an_email_is_sent_through_the_mail_service(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    smtp = FakeSmtp([])
    with caplog.at_level(logging.INFO):
        assert mailer(tmp_path, smtp).send(EMAIL) is None
    assert smtp.logins == [("apikey", "pw")] and smtp.quit_called == 1
    assert smtp.sent[0]["From"].addresses[0].addr_spec == "noreply@me0.ai"
    assert not (tmp_path / "outbox").exists()
    record = next(r for r in caplog.records if r.message == "Email sent")
    assert record.__dict__["kind"] == "sign-up confirmation" and "duration_ms" in record.__dict__
    assert SECRET_LINK not in caplog.text


def test_a_failed_send_is_tried_once_more(tmp_path: Path) -> None:
    smtp = FakeSmtp([smtplib.SMTPServerDisconnected("gone")])
    assert mailer(tmp_path, smtp).send(EMAIL) is None
    assert len(smtp.sent) == 1 and smtp.quit_called == 2


def test_a_send_that_fails_twice_is_logged_and_the_caller_told(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    smtp = FakeSmtp([smtplib.SMTPAuthenticationError(535, b"bad password")] * 2)
    with caplog.at_level(logging.WARNING), pytest.raises(EmailFailed, match=FAILED):
        mailer(tmp_path, smtp).send(EMAIL)
    failed = next(r for r in caplog.records if r.message == "Email failed")
    assert "SMTPAuthenticationError" in failed.__dict__["error"]
    assert failed.__dict__["attempt"] == 2 and SECRET_LINK not in caplog.text


def test_a_service_that_cant_be_reached_fails_too(tmp_path: Path) -> None:
    def refuse(service: MailService) -> Any:
        raise ConnectionRefusedError("no server")

    with pytest.raises(EmailFailed):
        Mailer(tmp_path, SERVICE, connect=refuse, sleep=lambda s: None).send(EMAIL)


def test_an_outbox_that_cant_be_written_fails(tmp_path: Path) -> None:
    (tmp_path / "outbox").write_text("a file, not a folder")
    with pytest.raises(EmailFailed):
        Mailer(tmp_path, None).send(EMAIL)


def test_the_password_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    assert mail_service("", 587, "", "") is None
    monkeypatch.setenv(PASSWORD_VARIABLE, "from-env")
    service = mail_service("smtp.example.com", 465, "u", "a@b.c")
    assert service is not None and service.password == "from-env" and service.port == 465


def test_connect_uses_tls_from_the_start_on_465_and_starttls_otherwise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    made: list[tuple[str, int]] = []

    class Plain:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            made.append(("plain", port))

        def starttls(self, context: Any) -> None:
            made.append(("starttls", 0))

    class Tls:
        def __init__(self, host: str, port: int, timeout: float, context: Any) -> None:
            made.append(("tls", port))

    monkeypatch.setattr(smtplib, "SMTP", Plain)
    monkeypatch.setattr(smtplib, "SMTP_SSL", Tls)
    connect(SERVICE)
    connect(MailService("h", 465, "", "a@b.c", ""))
    assert made == [("plain", 587), ("starttls", 0), ("tls", 465)]


def test_a_service_without_starttls_is_refused_and_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[bool] = []

    class Plain:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            pass

        def starttls(self, context: Any) -> None:
            raise smtplib.SMTPNotSupportedError("STARTTLS extension not supported by server.")

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(smtplib, "SMTP", Plain)
    with pytest.raises(smtplib.SMTPNotSupportedError):
        connect(SERVICE)
    assert closed == [True]


def test_the_mail_service_is_set_in_the_config(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        'smtp_host = "smtp.example.com"\nsmtp_port = 465\nsmtp_user = "apikey"\n'
        'mail_from = "me0.ai <noreply@me0.ai>"\n'
    )
    settings = load_settings(config)
    assert (settings.smtp_host, settings.smtp_port, settings.smtp_user) == (
        "smtp.example.com",
        465,
        "apikey",
    )
    config.write_text('smtp_host = "smtp.example.com"\n')
    with pytest.raises(ConfigError, match="mail_from"):
        load_settings(config)
    config.write_text("smtp_port = 0\n")
    with pytest.raises(ConfigError, match="smtp_port"):
        load_settings(config)
    config.write_text("smtp_user = 1\n")
    with pytest.raises(ConfigError, match="smtp_user"):
        load_settings(config)


def test_a_test_email_is_sent_from_the_command_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("IMAGESKIN_HOME", str(tmp_path))
    assert cli.main(["email-test", "ann@example.com"]) == 0
    out = capsys.readouterr().out
    assert "written to" in out and len(list((tmp_path / "outbox").glob("*-test-*.eml"))) == 1

    def refuse(self: Mailer, email: Email) -> None:
        raise EmailFailed(FAILED)

    monkeypatch.setattr(Mailer, "send", refuse)
    assert cli.main(["email-test", "ann@example.com"]) == 1
    assert "could not be sent" in capsys.readouterr().err


def test_a_test_email_through_a_service_says_where_it_went(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "config.toml"
    config.write_text('smtp_host = "smtp.example.com"\nmail_from = "a@me0.ai"\n')
    monkeypatch.setattr(Mailer, "send", lambda self, email: None)
    assert cli.main(["--config", str(config), "email-test", "ann@example.com"]) == 0
    assert "through smtp.example.com" in capsys.readouterr().out
