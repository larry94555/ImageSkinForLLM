"""The settings only the administrator can see or change (roadmap R155, items 123 and 125).

Kept in `admin-settings.json` in the app's home folder, apart from the Settings page's
`ui-settings.json`: the minutes without activity before the administrator is signed out, the
thresholds for the resource dashboard's colours, and whether hosts may use a custom image and a
custom voice (R239). Delete my data leaves them, as they are the
site's, not a user's. A change applies at once, to the sign-in going now and to the colours.

The file also holds the test email (R264, Milestone 31): the address that gets every email meant
for the administrator's test accounts. It is set only in the file, never from the page, and the
file is read again whenever it changes, so a test email added there works with no restart.
"""

import json
import logging
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal

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

# Set only in the file (R264), like the administrator's password, so the page can't change it.
TEST_EMAIL = "test_email"
FILE_ONLY = f"The test email is set only in {FILENAME}, in the admin folder."
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


class AdminSettingsStore:
    """The admin settings, kept in memory, saved at each change, and read again when the file
    is changed by hand (R264)."""

    def __init__(self, home: Path) -> None:
        self.path = home / FILENAME
        self._lock = threading.Lock()
        self._stamp = self._file_stamp()
        self._current = self._load(fallback=None)

    @property
    def current(self) -> AdminSettings:
        """The settings now: read from the file again first if it changed since last read."""
        stamp = self._file_stamp()
        if stamp != self._stamp:
            with self._lock:
                if stamp != self._stamp:
                    self._stamp = stamp
                    self._current = self._load(fallback=self._current)
        return self._current

    def _file_stamp(self) -> tuple[int, int] | None:
        try:
            info = self.path.stat()
        except OSError:
            return None
        return (info.st_mtime_ns, info.st_size)

    def _load(self, fallback: AdminSettings | None) -> AdminSettings:
        """The file's settings. One that can't be used gives the recommended settings at start,
        and keeps the ones in use when read again, as a file being edited may be half saved."""
        start = time.perf_counter()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("The file doesn't hold the admin settings.")
            test_email = self._test_email(data.pop(TEST_EMAIL, ""))
            settings = replace(checked(DEFAULTS, data), test_email=test_email)
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
        logger.info(
            "Admin test email read",
            extra={
                "path": str(self.path),
                "test_email_set": bool(settings.test_email),
                "again": fallback is not None,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return settings

    def _test_email(self, value: object) -> str:
        """The file's test email (R264), or "" for none; one that isn't an address is never
        used."""
        if value is None or value == "":
            return ""
        if isinstance(value, str) and EMAIL.fullmatch(value.strip()):
            return value.strip()
        logger.warning(
            "Admin test email ignored",
            extra={"path": str(self.path), "why": "not an email address"},
        )
        return ""

    def change(self, changes: dict[str, Any]) -> AdminSettings:
        """The settings with `changes` saved; the test email in the file is kept as it is."""
        before = self.current  # read again first, so a test email just added is kept
        with self._lock:
            after = checked(before, changes)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            part = self.path.with_suffix(".part")
            part.write_text(json.dumps(after.as_dict()), encoding="utf-8")
            os.replace(part, self.path)
            self._current = after
            # The app's own save isn't read back as a change by hand.
            self._stamp = self._file_stamp()
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
        return after
