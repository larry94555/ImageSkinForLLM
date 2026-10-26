"""The user's review of the sample video: accepted, or not yet (feature item 7, roadmap R14).

Chat stays locked until a sample is accepted. The acceptance is saved as review.json in the
app's home folder, with the sample it was given for (the photo, the voice and when the sample was
made). Once Prepare makes the sample again, for any reason, that acceptance no longer counts and
the new sample needs reviewing. Run the video test again in Settings (roadmap R27b) is the one
exception: it renders the same script from the same prepared photo and voice to watch it again,
so the sample keeps its acceptance; changing the photo, voice or accent (R28) needs a new one.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from imageskin.prepare_job import PrepareStatus

logger = logging.getLogger(__name__)

FILENAME = "review.json"
NOT_READY = "There is no sample video to accept yet. Click Prepare first."


@dataclass(frozen=True)
class Review:
    accepted: bool
    accepted_at: str | None = None  # ISO 8601, UTC


def sample_key(status: PrepareStatus) -> dict[str, str | None] | None:
    """What tells this sample apart from any other, or None when no sample is ready."""
    if status.state != "done":
        return None
    key = {
        "photo_id": status.photo_id,
        "voice_id": status.voice_id,
        "finished_at": status.finished_at,
    }
    # The face movement it was made with (R128a); left out for a sample made before R128a, so
    # one accepted then stays accepted while Off, what it was made with, is chosen.
    if status.face_movement is not None:
        key["face_movement"] = status.face_movement
    return key


def load_review(home: Path, status: PrepareStatus) -> Review:
    """Accepted when the sample ready now is the one that was accepted."""
    key = sample_key(status)
    path = home / FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Review(accepted=False)
    except (OSError, ValueError) as e:
        logger.error("Could not read the review", extra={"path": str(path), "error": str(e)})
        return Review(accepted=False)
    if not isinstance(data, dict):
        return Review(accepted=False)
    if key is None or data.get("sample") != key:
        # Nothing is accepted while no sample is ready, whatever the file says (review on PR #105).
        # Logged so a chat locked again after a change in setup (roadmap R28) says why.
        logger.info("Accepted sample is no longer current", extra={"changed": changed(data, key)})
        return Review(accepted=False)
    accepted_at = data.get("accepted_at")
    return Review(accepted=True, accepted_at=accepted_at if isinstance(accepted_at, str) else None)


def changed(data: dict[str, object], key: dict[str, str | None] | None) -> str:
    """What changed since the sample was accepted, for the log."""
    if key is None:
        return "not prepared"  # the photo, recordings or accent changed and Prepare hasn't run
    sample = data.get("sample")
    old = sample if isinstance(sample, dict) else {}
    names = ("photo_id", "voice_id", "face_movement")
    parts = [name for name in names if old.get(name) != key.get(name)]
    return ", ".join(parts) or "prepared again"


def accept(home: Path, status: PrepareStatus) -> Review:
    """Record that the user accepted the sample ready now. ValueError when none is ready."""
    key = sample_key(status)
    if key is None:
        raise ValueError(NOT_READY)
    review = Review(accepted=True, accepted_at=datetime.now(UTC).isoformat(timespec="seconds"))
    home.mkdir(parents=True, exist_ok=True)
    path = home / FILENAME
    path.write_text(
        json.dumps({"sample": key, "accepted_at": review.accepted_at}), encoding="utf-8"
    )
    logger.info("Sample accepted", extra={"path": str(path), **key})
    return review


def withdraw(home: Path, reason: str) -> Review:
    """Forget the acceptance: the user rejected the image or the voice, or changes the accent."""
    path = home / FILENAME
    try:
        path.unlink()
        logger.info("Sample acceptance withdrawn", extra={"reason": reason})
    except FileNotFoundError:
        logger.info("Sample not accepted; nothing to withdraw", extra={"reason": reason})
    return Review(accepted=False)
