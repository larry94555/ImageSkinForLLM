"""The user's confirmation that the person in the photos and recordings agreed to be cloned.

Setup is blocked until it is given (feature item 22). It is saved as consent.json in the app's
home folder, so it survives a restart.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

FILENAME = "consent.json"


@dataclass(frozen=True)
class Consent:
    agreed: bool
    agreed_at: str | None = None  # ISO 8601, UTC


def load_consent(home: Path) -> Consent:
    """The saved consent, or not agreed when none is saved or the file can't be read."""
    path = home / FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Consent(agreed=False)
    except (OSError, ValueError) as e:
        logger.error("Could not read consent", extra={"path": str(path), "error": str(e)})
        return Consent(agreed=False)
    agreed_at = data.get("agreed_at") if isinstance(data, dict) else None
    if not isinstance(agreed_at, str):
        logger.error("Consent file has no agreed_at", extra={"path": str(path)})
        return Consent(agreed=False)
    return Consent(agreed=True, agreed_at=agreed_at)


def save_consent(home: Path) -> Consent:
    """Record that the user confirmed consent now."""
    consent = Consent(agreed=True, agreed_at=datetime.now(UTC).isoformat(timespec="seconds"))
    home.mkdir(parents=True, exist_ok=True)
    path = home / FILENAME
    path.write_text(json.dumps({"agreed_at": consent.agreed_at}), encoding="utf-8")
    logger.info("Consent recorded", extra={"path": str(path), "agreed_at": consent.agreed_at})
    return consent
