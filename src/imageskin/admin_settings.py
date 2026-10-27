"""The settings only the administrator can see or change (roadmap R155, items 123 and 125).

Kept in `admin-settings.json` in the app's home folder, apart from the Settings page's
`ui-settings.json`: the minutes without activity before the administrator is signed out, and the
thresholds for the resource dashboard's colours. Delete my data leaves them, as they are the
site's, not a user's. A change applies at once, to the sign-in going now and to the colours.
"""

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from imageskin.admin import TIMEOUT_MINUTES
from imageskin.resources import RECOMMENDED, Thresholds

logger = logging.getLogger(__name__)

FILENAME = "admin-settings.json"
MINUTES = (5, 240)
ORDER = (
    "The thresholds must go in order, each a percentage from 1 to 99: red below orange, and "
    "orange below blue."
)


@dataclass(frozen=True)
class AdminSettings:
    timeout_minutes: int = TIMEOUT_MINUTES
    thresholds: Thresholds = RECOMMENDED

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULTS = AdminSettings()


def number(value: object) -> bool:
    # type() rather than isinstance(): bool is a subclass of int, and true is not a number here.
    return type(value) in (int, float)


def checked(settings: AdminSettings, changes: dict[str, Any]) -> AdminSettings:
    """The settings with the changes made; ValueError with a plain message if one is wrong."""
    unknown = sorted(set(changes) - {"timeout_minutes", "thresholds"})
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
    return settings


class AdminSettingsStore:
    """The admin settings, read once and kept in memory, and saved at each change."""

    def __init__(self, home: Path) -> None:
        self.path = home / FILENAME
        self._lock = threading.Lock()
        self.current = self._load()

    def _load(self) -> AdminSettings:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("The file doesn't hold the admin settings.")
            return checked(DEFAULTS, data)
        except FileNotFoundError:
            return DEFAULTS
        except (OSError, ValueError) as e:
            logger.error(
                "Admin settings are not valid; using the recommended ones",
                extra={"path": str(self.path), "error": str(e)},
            )
            return DEFAULTS

    def change(self, changes: dict[str, Any]) -> AdminSettings:
        with self._lock:
            before = self.current
            after = checked(before, changes)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            part = self.path.with_suffix(".part")
            part.write_text(json.dumps(after.as_dict()), encoding="utf-8")
            os.replace(part, self.path)
            self.current = after
        logger.info(
            "Admin settings changed", extra={"before": before.as_dict(), "after": after.as_dict()}
        )
        return after
