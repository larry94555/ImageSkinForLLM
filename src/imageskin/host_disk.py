"""The disk space a host has used (roadmap R192, item 152).

Each photo, recording and PDF stored is recorded with the host who added it, in `owners.json` in
the app's home folder. One stored before host accounts, with no record, counts for the first host
to sign up. A host's amounts are:

- **Images and voice recordings:** their photos and recordings as stored (already converted),
  with each one's info file, and the prepared face of each of their photos. The files prepared
  from the person as a whole (the voice sample, the sample video with Goodbye and Welcome back,
  the reply videos) go with the photo chosen for the video, so they count for its host; with no
  photo chosen, for the first host.
- **PDFs:** their PDFs, with all made from each: what was read, the wiki, its edits and saved
  versions.
- **Total:** the two added up.
"""

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Literal

from imageskin.photoreal_library import library_key

logger = logging.getLogger(__name__)

FILENAME = "owners.json"
Kind = Literal["photos", "sounds", "pdfs"]

# Prepared from the person as a whole, beside their uploads in the home folder.
PREPARED = (
    "uploads/voice-sample.wav",
    "uploads/chosen-photo.json",
    "clips",
    "prepare.json",
    "replies",
)


def size_of(path: Path) -> int:
    """Bytes in a file, or in every file under a folder; 0 when there is none."""
    if path.is_file():
        return path.stat().st_size
    total = 0
    for folder, _, files in os.walk(path):
        for name in files:
            try:
                total += (Path(folder) / name).stat().st_size
            except OSError:
                continue  # removed while counting
    return total


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
            # Counted as stored before host accounts, so it is still counted for someone.
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


def count(home: Path, owners: Owners, email: str, first_host: str | None) -> dict[str, int]:
    """The host's images and voice recordings, PDFs and total, in bytes."""
    started = time.perf_counter()
    recorded = owners.read()

    def theirs(kind: Kind, item: str) -> bool:
        return recorded.get(kind, {}).get(item, first_host) == email

    media = 0
    for kind in ("photos", "sounds"):
        folder = home / "uploads" / kind
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if not path.is_file() or not theirs(kind, path.stem):
                continue
            media += path.stat().st_size
            if kind == "photos" and path.suffix != ".json":
                media += size_of(home / "photoreal" / library_key(path))
    try:
        chosen = json.loads((home / "uploads" / "chosen-photo.json").read_text("utf-8"))["id"]
    except (OSError, ValueError, KeyError, TypeError):
        chosen = None
    prepared_by = recorded.get("photos", {}).get(chosen, first_host) if chosen else first_host
    if prepared_by == email:
        media += sum(size_of(home / name) for name in PREPARED)

    pdfs = 0
    content = home / "content"
    pdf_folder = content / "pdfs"
    ids = [p.stem for p in pdf_folder.glob("*.pdf")] if pdf_folder.is_dir() else []
    mine = {pdf_id for pdf_id in ids if theirs("pdfs", pdf_id)}
    if mine and content.is_dir():
        # Every file made from a PDF is named for its id: <id>.pdf, <id>.json, <id>.history ...
        for part in content.iterdir():
            if not part.is_dir():
                continue
            for path in part.iterdir():
                if path.name.split(".", 1)[0] in mine:
                    pdfs += size_of(path)

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
