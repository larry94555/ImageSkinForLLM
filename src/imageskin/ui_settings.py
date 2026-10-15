"""The settings anyone can change from the Settings menu in the top bar (roadmap R41a).

Saved as ui-settings.json in the app's home folder, so they are the same after a reload or a
restart and on every browser (feature items 49 and 51). R44's sign-on restricts them later.
"""

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FILENAME = "ui-settings.json"
# One change at a time, so two changes made together (from two browsers, say) both stay: each
# reads the file the other wrote (review on PR #77).
_saving = threading.Lock()


@dataclass(frozen=True)
class UiSettings:
    # The timing readout under the video and the other timings on the pages (item 49).
    show_metrics: bool = False
    # Which screens are shown (item 50, R41b): every page and option, or the chat and a read-only
    # wiki with its PDFs. Only the screens change: the server doesn't check it, since anyone can
    # switch it for now.
    view: str = "teacher"
    # The Teach me button and lessons in the chat (R41h); off unless a teacher turns it on
    # (Larry, 2026-10-15).
    teach_me: bool = False
    # The Quiz me button and quizzes in the chat (R41i); off like Teach me until turned on.
    quiz_me: bool = False
    # The Assessment button and assessments in the chat (R41j); off like Quiz me until turned on.
    assessment: bool = False
    # Tools for looking into problems, such as copying the chat to paste it elsewhere; off unless
    # turned on (Larry, 2026-10-15).
    debug: bool = False


# The values each setting can take.
CHOICES: dict[str, tuple[object, ...]] = {
    "show_metrics": (True, False),
    "view": ("teacher", "student"),
    "teach_me": (True, False),
    "quiz_me": (True, False),
    "assessment": (True, False),
    "debug": (True, False),
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
    with _saving:
        settings = checked(load_ui_settings(home), changes)
        home.mkdir(parents=True, exist_ok=True)
        path = home / FILENAME
        # Written beside it, then put in its place, so a read never sees half a file.
        part = path.with_suffix(".part")
        part.write_text(json.dumps(asdict(settings)), encoding="utf-8")
        os.replace(part, path)
    logger.info("Settings changed", extra={"path": str(path), **changes})
    return settings
