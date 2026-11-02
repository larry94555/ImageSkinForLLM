"""Sending email (roadmap R215, feature item 169).

The server sends email over SMTP to a transactional email service set in config.toml
(`smtp_host`, `smtp_port`, `smtp_user` and `mail_from`), with the password from the
IMAGESKIN_SMTP_PASSWORD environment variable, never from the file. Port 465 is TLS from the
start; any other port is upgraded with STARTTLS, which a service must offer. With no mail
service set, as on a laptop, each email is written as a file to the `outbox` folder in the app's
home folder instead, so every email can be tested without a service. A send that fails is tried
once more, then logged, and the caller is told, so its page can say so.

The log never has an email's words or a link in it: only its kind, the time taken, the file or
the error.
"""

import contextlib
import logging
import os
import smtplib
import ssl
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

PASSWORD_VARIABLE = "IMAGESKIN_SMTP_PASSWORD"
OUTBOX = "outbox"
TIMEOUT_S = 20.0
RETRY_AFTER_S = 2.0
TLS_PORT = 465
FAILED = "The email could not be sent. Please try again later."


class EmailFailed(Exception):
    """The email was not sent; the message is for the person who asked for it."""


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str
    kind: str  # what it is for, for the log: "test", "sign-up confirmation", ...


@dataclass(frozen=True)
class MailService:
    host: str
    port: int
    user: str
    sender: str
    password: str


class Smtp(Protocol):
    def login(self, user: str, password: str) -> object: ...
    def send_message(self, msg: EmailMessage) -> object: ...
    def quit(self) -> object: ...


def connect(service: MailService) -> Smtp:
    """An SMTP connection to the service, encrypted before anything is sent."""
    context = ssl.create_default_context()
    if service.port == TLS_PORT:
        return smtplib.SMTP_SSL(service.host, service.port, timeout=TIMEOUT_S, context=context)
    smtp = smtplib.SMTP(service.host, service.port, timeout=TIMEOUT_S)
    try:
        smtp.starttls(context=context)
    except BaseException:
        smtp.close()
        raise
    return smtp


def mail_service(host: str, port: int, user: str, sender: str) -> MailService | None:
    """The mail service set in config.toml, or None when none is set (email goes to the
    outbox). Its password comes from the environment."""
    if not host:
        return None
    return MailService(host, port, user, sender, os.environ.get(PASSWORD_VARIABLE, ""))


class Mailer:
    def __init__(
        self,
        home: Path,
        service: MailService | None,
        connect: Callable[[MailService], Smtp] = connect,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.outbox = home / OUTBOX
        self.service = service
        self._connect = connect
        self._sleep = sleep

    def message(self, email: Email) -> EmailMessage:
        msg = EmailMessage()
        sender = self.service.sender if self.service else "ImageSkinForLLM <noreply@localhost>"
        msg["From"] = sender
        msg["To"] = email.to
        msg["Subject"] = email.subject
        msg["Date"] = formatdate(localtime=False, usegmt=True)
        msg["Message-ID"] = make_msgid()
        msg.set_content(email.text)
        return msg

    def send(self, email: Email) -> Path | None:
        """Send the email, or write it to the outbox with no mail service set: the file, or
        None when sent. Raises EmailFailed when it couldn't be sent, after a second try."""
        start = time.perf_counter()
        msg = self.message(email)
        if self.service is None:
            return self._write(email, msg, start)
        for attempt in (1, 2):
            try:
                smtp = self._connect(self.service)
                try:
                    if self.service.user:
                        smtp.login(self.service.user, self.service.password)
                    smtp.send_message(msg)
                finally:
                    with contextlib.suppress(OSError, smtplib.SMTPException):
                        smtp.quit()
            except (OSError, smtplib.SMTPException) as e:
                logger.log(
                    logging.WARNING if attempt == 1 else logging.ERROR,
                    "Email not sent" if attempt == 1 else "Email failed",
                    extra={
                        "kind": email.kind,
                        "attempt": attempt,
                        "error": f"{type(e).__name__}: {e}",
                        "duration_ms": ms_since(start),
                    },
                )
                if attempt == 2:
                    raise EmailFailed(FAILED) from e
                self._sleep(RETRY_AFTER_S)
                continue
            logger.info(
                "Email sent",
                extra={"kind": email.kind, "attempt": attempt, "duration_ms": ms_since(start)},
            )
            return None
        raise AssertionError("unreachable")  # pragma: no cover

    def _write(self, email: Email, msg: EmailMessage, start: float) -> Path:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        kind = "".join(c if c.isalnum() else "-" for c in email.kind)
        path = self.outbox / f"{stamp}-{kind}-{uuid.uuid4().hex[:8]}.eml"
        try:
            self._own_outbox()
            # Created only by this call, readable by the app's own user alone: its links let
            # whoever opens it confirm an email or reset a password (Codex's review of PR #278).
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(bytes(msg))
        except OSError as e:
            logger.error("Email failed", extra={"kind": email.kind, "error": str(e)})
            raise EmailFailed(FAILED) from e
        logger.info(
            "Email written to outbox",
            extra={"kind": email.kind, "file": str(path), "duration_ms": ms_since(start)},
        )
        return path

    def _own_outbox(self) -> None:
        """The outbox, made or kept the app's own user's alone (0700), whatever the umask."""
        self.outbox.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not self.outbox.is_dir() or self.outbox.is_symlink():
            raise NotADirectoryError(f"{self.outbox} is not a folder")
        if os.name == "posix" and self.outbox.stat().st_mode & 0o077:
            os.chmod(self.outbox, 0o700)
            logger.warning("Outbox made private", extra={"path": str(self.outbox)})


def ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)
