"""Delete my data (roadmap R31, feature item 23): one action removes from the app's home folder
everything made from the person: the uploaded photos and recordings, the prepared face and voice
with the sample, Goodbye and Welcome back, the reply videos, the conversation, the review, the
accent and the consent, so setup starts again from the beginning.

What isn't the person's is kept: the downloaded models, the PDFs and their wiki (the host's
content) and the Settings page's settings.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from imageskin.start_now import CHOICE_FILE, CHOICE_SAVING_FILE

logger = logging.getLogger(__name__)

# Folders and files in the home folder, with the files written on the way to a few of them.
PERSONAL = (
    "uploads",  # photos, recordings, the chosen photo and the voice sample
    "photoreal",  # the prepared face of each photo
    "clips",  # the sample video, Goodbye and Welcome back
    "prepare.json",
    "prepare.saving.json",
    "replies",  # reply videos and the idle video
    "conversation.json",
    "conversation.saving.json",
    "review.json",
    "accent.json",
    "consent.json",
    # The default person chosen (R24c). The downloaded people are kept: they are made up.
    CHOICE_FILE,
    CHOICE_SAVING_FILE,
)


@dataclass(frozen=True)
class Deleted:
    files: int = 0  # how many files were removed
    bytes: int = 0
    # Files that could not be removed (open in another program, as on Windows), from the home.
    left: list[str] = field(default_factory=list)


def delete_my_data(home: Path) -> Deleted:
    """Remove the person's data from `home`. A file that can't be removed is logged and listed
    in `left`, and the rest is removed anyway, so trying again removes only what is left."""
    start = time.perf_counter()
    logger.info("Deleting my data", extra={"home": str(home)})
    files, size, left = 0, 0, []
    for name in PERSONAL:
        path = home / name
        targets = [path] if path.is_file() else list(_files_in(path))
        for target in targets:
            try:
                n = target.stat().st_size
                target.unlink()
            except FileNotFoundError:
                continue
            except OSError as e:
                left.append(target.relative_to(home).as_posix())
                logger.warning(
                    "Could not delete a file",
                    extra={"file": left[-1], "error": str(e)},
                )
                continue
            files += 1
            size += n
        if path.is_dir():
            _remove_empty_folders(path)
        # Whatever is still there, such as a folder that couldn't be read, is left too, so the
        # delete never reports as complete what it couldn't see (review on PR #109).
        if os.path.lexists(path) and not any(_under(name, f) for f in left):
            left.append(name)
            logger.warning("Could not delete a folder", extra={"file": name})
    deleted = Deleted(files, size, left)
    logger.info(
        "Deleted my data",
        extra={
            "files": files,
            "bytes": size,
            "left": len(left),
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )
    return deleted


def _under(name: str, file: str) -> bool:
    return file == name or file.startswith(name + "/")


def _files_in(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []

    def unreadable(e: OSError) -> None:
        logger.warning(
            "Could not read a folder", extra={"folder": str(e.filename), "error": str(e)}
        )

    return [Path(root) / f for root, _, names in os.walk(folder, onerror=unreadable) for f in names]


def _remove_empty_folders(folder: Path) -> None:
    """Remove the folder and those in it, deepest first; one still holding a file is kept."""
    for root, _, _ in sorted(os.walk(folder), key=lambda w: len(w[0]), reverse=True):
        try:
            Path(root).rmdir()
        except OSError:
            pass  # a file in it could not be removed, and is listed already
