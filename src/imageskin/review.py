"""The user's review of the sample video: accepted, or not yet (feature item 7, roadmap R14).

Chat stays locked until a sample is accepted. The acceptance is saved as review.json in the
app's home folder, with the sample it was given for (the photo, the voice and when the sample was
made). Once the sample is made again, for any reason, that acceptance no longer counts and the
new sample needs reviewing.
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
    return {
        "photo_id": status.photo_id,
        "voice_id": status.voice_id,
        "finished_at": status.finished_at,
    }


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
    if key is None or not isinstance(data, dict) or data.get("sample") != key:
        return Review(accepted=False)
    accepted_at = data.get("accepted_at")
    return Review(accepted=True, accepted_at=accepted_at if isinstance(accepted_at, str) else None)


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
