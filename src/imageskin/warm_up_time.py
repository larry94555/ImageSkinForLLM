"""How long the replies' warm-up took the last time it ran (R183), kept in the app's home folder,
so while it runs again after a restart the chat can say how many seconds are left."""

import json
import logging
import math
from pathlib import Path

logger = logging.getLogger(__name__)

FILENAME = "warm-up.json"


def last_warm_up_s(home: Path) -> float | None:
    """The last warm-up's length in seconds, or None when there was none or it can't be read."""
    path = home / FILENAME
    try:
        seconds = json.loads(path.read_text(encoding="utf-8"))["seconds"]
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError) as e:
        logger.warning("Could not read the last warm-up time", extra={"error": str(e)})
        return None
    if not isinstance(seconds, int | float) or seconds < 0:
        logger.warning("Last warm-up time is not a time", extra={"seconds": seconds})
        return None
    return float(seconds)


def save_warm_up_s(home: Path, seconds: float) -> None:
    """Keep how long the warm-up took. Failures are logged only: the chat then says no time."""
    try:
        home.mkdir(parents=True, exist_ok=True)
        (home / FILENAME).write_text(json.dumps({"seconds": round(seconds, 1)}), encoding="utf-8")
    except OSError as e:
        logger.warning("Could not keep the warm-up time", extra={"error": str(e)})


def seconds_left(expected: float | None, elapsed: float) -> int | None:
    """Whole seconds left if this warm-up takes as long as the last; None when that isn't known
    or it is already taking longer."""
    if expected is None:
        return None
    left = math.ceil(expected - elapsed)
    return left if left > 0 else None
