"""The disk space a host has used (roadmap R192, item 152).

Each photo, recording and PDF stored is recorded with the host signed in when it was added, in
`owners.json` in the app's home folder. For now only those files count (Larry, 2026-10-30): a
host's photos and recordings as stored, their PDFs, and the total of the two. What is made from
them, and files stored before host accounts, count for no host.
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

FILENAME = "owners.json"
Kind = Literal["photos", "sounds", "pdfs"]


class Owners:
    """Who added each photo, recording and PDF, kept in owners.json."""

    def __init__(self, home: Path) -> None:
        self.path = home / FILENAME
        self._lock = threading.Lock()

    def read(self) -> dict[str, dict[str, str]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            # Counted for no host until it is fixed; the files themselves are untouched.
            logger.error("Could not read who added each file", extra={"error": str(e)})
            return {}
        return data if isinstance(data, dict) else {}

    def record(self, kind: Kind, item: str, email: str) -> None:
        with self._lock:
            data = self.read()
            data.setdefault(kind, {})[item] = email
            writing = self.path.with_suffix(".writing")
            writing.write_text(json.dumps(data, indent=1), encoding="utf-8")
            writing.replace(self.path)
        logger.info("File owner recorded", extra={"kind": kind, "id": item, "email": email})


def count(home: Path, owners: Owners, email: str) -> dict[str, int]:
    """The host's photos and recordings, PDFs and total, in bytes."""
    started = time.perf_counter()
    recorded = owners.read()

    def added(kind: Kind, folder: Path, suffixes: tuple[str, ...]) -> int:
        """Bytes in the files of `folder` the host added, by their ids."""
        theirs = {item for item, who in recorded.get(kind, {}).items() if who == email}
        if not theirs or not folder.is_dir():
            return 0
        return sum(
            p.stat().st_size
            for p in folder.iterdir()
            if p.is_file() and p.suffix not in suffixes and p.stem in theirs
        )

    media = sum(added(kind, home / "uploads" / kind, (".json",)) for kind in ("photos", "sounds"))
    pdfs = added("pdfs", home / "content" / "pdfs", (".json", ".old", ".writing"))
    amounts = {"images_and_recordings": media, "pdfs": pdfs, "total": media + pdfs}
    logger.info(
        "Host disk space counted",
        extra={
            "email": email,
            **amounts,
            "took_ms": round((time.perf_counter() - started) * 1000, 1),
        },
    )
    return amounts
