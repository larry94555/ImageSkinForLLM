"""The step the setup wizard has reached (roadmap R131), saved as wizard.json in the app's home
folder with the rest of the setup's progress, so leaving and coming back opens it there.

The log has `Wizard step` with each step as it is opened, and how long the user spent on the
step before it.
"""

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

FILENAME = "wizard.json"
# In order. The photo and the voice are picked as files until R132 and R133 add the camera and
# the microphone.
STEPS = ("start", "photo", "voice", "accent", "prepare", "review")


def load_step(home: Path) -> str:
    """The step reached, or the first one when none is saved or the file can't be read."""
    path = home / FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return STEPS[0]
    except (OSError, ValueError) as e:
        logger.error("Could not read the wizard's step", extra={"path": str(path), "error": str(e)})
        return STEPS[0]
    step = data.get("step") if isinstance(data, dict) else None
    if step not in STEPS:
        logger.error("Wizard file has no known step", extra={"path": str(path), "step": step})
        return STEPS[0]
    return str(step)


def save_step(home: Path, step: str) -> str:
    """Save `step` as the one reached, logging how long was spent on the one before."""
    if step not in STEPS:
        raise ValueError(f"No wizard step called {step!r}.")
    path = home / FILENAME
    before: object = None
    try:
        before = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass  # the first step, or an unreadable file: nothing to time
    if not isinstance(before, dict):
        before = {}
    opened = before.get("opened")
    now = time.time()
    spent = round(now - opened, 1) if isinstance(opened, (int, float)) else None
    home.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"step": step, "opened": now}), encoding="utf-8")
    logger.info(
        "Wizard step",
        extra={"step": step, "from": before.get("step"), "spent_on_previous_s": spent},
    )
    return step


# Why the camera wasn't used (R132), as the browser reports it.
CAMERA_REASONS = ("insecure", "unsupported", "refused", "no-camera", "failed")


def log_camera(
    taken: bool,
    reason: str | None = None,
    width: int | None = None,
    height: int | None = None,
    camera: str | None = None,
) -> None:
    """Log a photo taken with the camera in the wizard, with its size and the camera's name, or
    why the camera wasn't used. The picture itself is never logged."""
    if taken:
        logger.info(
            "Camera photo taken", extra={"width": width, "height": height, "camera": camera}
        )
        return
    if reason not in CAMERA_REASONS:
        raise ValueError(f"No camera reason called {reason!r}.")
    logger.info("Camera not used", extra={"reason": reason})
