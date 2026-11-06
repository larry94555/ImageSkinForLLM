"""The settings only the administrator can see or change (roadmap R155, items 123 and 125).

Kept in `admin-settings.json` in the app's home folder, apart from the Settings page's
`ui-settings.json`: the minutes without activity before the administrator is signed out, the
thresholds for the resource dashboard's colours, and whether hosts may use a custom image and a
custom voice (R239). Delete my data leaves them, as they are the
site's, not a user's. A change applies at once, to the sign-in going now and to the colours.

The test email (R264, Milestone 31), the address that gets every email meant for the
administrator's test accounts, is not in that file: it is `test_email` in `admin.toml`, beside
the administrator's password (Larry, on PR 313), where the administrator can edit it on the
hosted machine. It is set only there, never from the page, and that file is read again whenever
it changes, so a test email added there works with no restart.
"""

import json
import logging
import os
import re
import threading
import time
import tomllib
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal

from imageskin.admin import FILENAME as ADMIN_FILENAME
from imageskin.admin import TIMEOUT_MINUTES
from imageskin.resources import RECOMMENDED, Thresholds

logger = logging.getLogger(__name__)

FILENAME = "admin-settings.json"
MINUTES = (5, 240)
# How long a paused site is kept before its content is deleted (R69a; Larry, 2026-11-03).
DELETE_DAYS = 30
DAYS = (1, 365)
ORDER = (
    "The thresholds must go in order, each a percentage from 1 to 99: red below orange, and "
    "orange below blue."
)


CHECKBOXES = ("disable_custom_image", "disable_custom_voice")

# Set only in admin.toml (R264), beside the administrator's password, so the page can't change it.
TEST_EMAIL = "test_email"
FILE_ONLY = f"The test email is set only in {ADMIN_FILENAME}, in the admin folder."
# The same check as a host's email (hosts.EMAIL), which can't be imported here: hosts imports
# this module.
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


@dataclass(frozen=True)
class AdminSettings:
    timeout_minutes: int = TIMEOUT_MINUTES
    thresholds: Thresholds = RECOMMENDED
    # Hosts (R239): both checked by default, so a host uses a default person and a ready-made
    # voice unless the administrator allows their own. A file from before R239 has neither, so
    # it gets both checked.
    disable_custom_image: bool = True
    disable_custom_voice: bool = True
    # Days a paused site, cancelled or deleted by its host, is kept before its content is
    # deleted (R69a), so a host who missed a payment can come back.
    days_before_deleting: int = DELETE_DAYS
    # Where every email for a test account goes (R264); empty when not set.
    test_email: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULTS = AdminSettings()


def number(value: object) -> bool:
    # type() rather than isinstance(): bool is a subclass of int, and true is not a number here.
    return type(value) in (int, float)


def checked(settings: AdminSettings, changes: dict[str, Any]) -> AdminSettings:
    """The settings with the changes made; ValueError with a plain message if one is wrong."""
    if TEST_EMAIL in changes:
        raise ValueError(FILE_ONLY)
    unknown = sorted(
        set(changes) - {"timeout_minutes", "thresholds", "days_before_deleting", *CHECKBOXES}
    )
    if unknown:
        raise ValueError(f"There is no admin setting called {unknown[0]}.")
    if "timeout_minutes" in changes:
        minutes = changes["timeout_minutes"]
        low, high = MINUTES
        if type(minutes) is not int or not low <= minutes <= high:
            raise ValueError(
                f"The minutes without activity must be a whole number from {low} to {high}."
            )
        settings = replace(settings, timeout_minutes=minutes)
    if "days_before_deleting" in changes:
        days = changes["days_before_deleting"]
        low, high = DAYS
        if type(days) is not int or not low <= days <= high:
            raise ValueError(
                f"The days before a paused site is deleted must be a whole number from {low} to"
                f" {high}."
            )
        settings = replace(settings, days_before_deleting=days)
    if "thresholds" in changes:
        given = changes["thresholds"]
        if not isinstance(given, dict) or set(given) - set(asdict(RECOMMENDED)):
            raise ValueError(ORDER)
        values = {**asdict(settings.thresholds), **given}
        if not all(number(v) for v in values.values()):
            raise ValueError(ORDER)
        thresholds = Thresholds(**values)
        if not 1 <= thresholds.red_below < thresholds.orange_below < thresholds.blue_above <= 99:
            raise ValueError(ORDER)
        settings = replace(settings, thresholds=thresholds)
    for name in CHECKBOXES:
        if name in changes:
            if type(changes[name]) is not bool:
                raise ValueError(f"{name} must be true or false.")
            settings = replace(settings, **{name: changes[name]})
    return settings


# A host's own choice for a custom image or voice (R242), over the checkbox; None follows it.
Choice = Literal["allow", "deny"] | None


@dataclass(frozen=True)
class CustomUse:
    """Whether one host may use their own photo and their own voice."""

    image: bool
    voice: bool


def custom_use(
    settings: AdminSettings, image_choice: Choice = None, voice_choice: Choice = None
) -> CustomUse:
    """The rule every later PR asks (R239): the host's own Allow or Deny if they have one,
    otherwise the Admin settings' checkbox. Until R242 no host has one of their own."""

    def allowed(choice: Choice, disabled: bool) -> bool:
        return choice == "allow" if choice is not None else not disabled

    return CustomUse(
        image=allowed(image_choice, settings.disable_custom_image),
        voice=allowed(voice_choice, settings.disable_custom_voice),
    )


Stamp = tuple[int, int] | None


def file_stamp(path: Path) -> Stamp:
    """The file's modification time and size, or None with no file: a change means read it."""
    try:
        info = path.stat()
    except OSError:
        return None
    return (info.st_mtime_ns, info.st_size)


class AdminSettingsStore:
    """The admin settings, kept in memory, saved at each change, and read again when the file
    is changed by hand (R264). The test email comes from the administrator's `admin.toml`
    (`admin_file`), read again when it changes."""

    def __init__(self, home: Path, admin_file: Path | None = None) -> None:
        self.path = home / FILENAME
        self.admin_file = admin_file or home / ADMIN_FILENAME
        self._lock = threading.Lock()
        self._stamp = file_stamp(self.path)
        self._current = self._load(fallback=None)
        self._admin_stamp = file_stamp(self.admin_file)
        self._test_email = self._load_test_email(again=False)

    @property
    def current(self) -> AdminSettings:
        """The settings now: each file read again first if it changed since last read."""
        if file_stamp(self.path) != self._stamp or file_stamp(self.admin_file) != self._admin_stamp:
            with self._lock:
                self._refresh()
        return replace(self._current, test_email=self._test_email)

    def _refresh(self) -> None:
        """Read each file again if it changed since last read. Called holding `_lock`."""
        stamp = file_stamp(self.path)
        if stamp != self._stamp:
            self._stamp = stamp
            self._current = self._load(fallback=self._current)
        stamp = file_stamp(self.admin_file)
        if stamp != self._admin_stamp:
            self._admin_stamp = stamp
            self._test_email = self._load_test_email(again=True)

    def _load(self, fallback: AdminSettings | None) -> AdminSettings:
        """The file's settings. One that can't be used gives the recommended settings at start,
        and keeps the ones in use when read again, as a file being edited may be half saved."""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("The file doesn't hold the admin settings.")
            if data.pop(TEST_EMAIL, ""):
                # Where R264 first put it: say where it goes now rather than drop it silently.
                logger.warning(
                    "Admin test email in the wrong file; set it in admin.toml",
                    extra={"path": str(self.path), "admin_file": str(self.admin_file)},
                )
            return checked(DEFAULTS, data)
        except FileNotFoundError:
            return DEFAULTS
        except (OSError, ValueError) as e:
            if fallback is not None:
                logger.error(
                    "Admin settings are not valid; keeping the ones in use",
                    extra={"path": str(self.path), "error": str(e)},
                )
                return fallback
            logger.error(
                "Admin settings are not valid; using the recommended ones",
                extra={"path": str(self.path), "error": str(e)},
            )
            return DEFAULTS

    def _load_test_email(self, again: bool) -> str:
        """The test email in admin.toml (R264), or "" for none. A file that can't be read when
        read again keeps the one in use, as a file being edited may be half saved."""
        start = time.perf_counter()
        try:
            with self.admin_file.open("rb") as f:
                value = tomllib.load(f).get(TEST_EMAIL, "")
        except FileNotFoundError:
            value = ""
        except (OSError, tomllib.TOMLDecodeError) as e:
            logger.error(
                "Admin test email not read",
                extra={"path": str(self.admin_file), "error": str(e), "again": again},
            )
            return self._test_email if again else ""
        test_email = self._checked_test_email(value)
        logger.info(
            "Admin test email read",
            extra={
                "path": str(self.admin_file),
                "test_email_set": bool(test_email),
                "again": again,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return test_email

    def _checked_test_email(self, value: object) -> str:
        """The test email, or "" for none; one that isn't an address is never used."""
        if value is None or value == "":
            return ""
        if isinstance(value, str) and EMAIL.fullmatch(value.strip()):
            return value.strip()
        logger.warning(
            "Admin test email ignored",
            extra={"path": str(self.admin_file), "why": "not an email address"},
        )
        return ""

    def change(self, changes: dict[str, Any]) -> AdminSettings:
        """The settings with `changes` saved; the test email, in admin.toml, is not touched."""
        with self._lock:
            # Read again first, all under the one lock, so two changes at once each start from
            # the other's result (Codex's review).
            self._refresh()
            before = self._current
            after = checked(before, changes)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            part = self.path.with_suffix(".part")
            saved = after.as_dict()
            del saved[TEST_EMAIL]
            part.write_text(json.dumps(saved), encoding="utf-8")
            os.replace(part, self.path)
            self._current = after
            # The app's own save isn't read back as a change by hand.
            self._stamp = file_stamp(self.path)
            test_email = self._test_email
        # Each checkbox's old and new value on its own too, so a change of who may use a custom
        # image or voice is easy to find in the log (R239).
        logger.info(
            "Admin settings changed",
            extra={
                "before": before.as_dict(),
                "after": after.as_dict(),
                **{
                    f"{name}_change": [getattr(before, name), getattr(after, name)]
                    for name in CHECKBOXES
                },
            },
        )
        return replace(after, test_email=test_email)
