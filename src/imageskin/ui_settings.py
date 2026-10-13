"""The settings anyone can change from the Settings menu in the top bar (roadmap R41a).

Saved as ui-settings.json in the app's home folder, so they are the same after a reload or a
restart and on every browser (feature items 49 and 51). R44's sign-on restricts them later.
"""

import json
import logging
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FILENAME = "ui-settings.json"


@dataclass(frozen=True)
class UiSettings:
    # The timing readout under the video and the other timings on the pages (item 49).
    show_metrics: bool = False
    # Which screens are shown (item 50, R41b): every page and option, or the chat and a read-only
    # wiki with its PDFs. Only the screens change: the server doesn't check it, since anyone can
    # switch it for now.
    view: str = "teacher"


# The values each setting can take.
CHOICES: dict[str, tuple[object, ...]] = {
    "show_metrics": (True, False),
    "view": ("teacher", "student"),
}


def load_ui_settings(home: Path) -> UiSettings:
    """The saved settings, the defaults for any not saved, or all the defaults when the file
    is missing or can't be read."""
    path = home / FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return UiSettings()
    except (OSError, ValueError) as e:
        logger.error("Could not read the settings", extra={"path": str(path), "error": str(e)})
        return UiSettings()
    try:
        return checked(UiSettings(), data if isinstance(data, dict) else {})
    except ValueError as e:
        logger.error("Saved settings are not valid", extra={"path": str(path), "error": str(e)})
        return UiSettings()


def checked(settings: UiSettings, changes: dict[str, Any]) -> UiSettings:
    """The settings with the changes made; ValueError for an unknown name or a wrong value."""
    for name, value in changes.items():
        if name not in CHOICES:
            raise ValueError(f"There is no setting called {name}.")
        # type() too, so 1 isn't taken as True
        if not any(type(value) is type(c) and value == c for c in CHOICES[name]):
            choices = ", ".join(map(str, CHOICES[name]))
            raise ValueError(f"The setting {name} must be one of: {choices}.")
    return replace(settings, **changes)


def save_ui_settings(home: Path, changes: dict[str, Any]) -> UiSettings:
    """Make the changes to the saved settings and save them; ValueError if one is invalid."""
    settings = checked(load_ui_settings(home), changes)
    home.mkdir(parents=True, exist_ok=True)
    path = home / FILENAME
    path.write_text(json.dumps(asdict(settings)), encoding="utf-8")
    logger.info("Settings changed", extra={"path": str(path), **changes})
    return settings
