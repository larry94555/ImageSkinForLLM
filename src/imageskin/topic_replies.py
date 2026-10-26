"""Replies to the example questions under the prompt box, kept once made (roadmap R130a).

The example questions (R41g) are the same for everyone until the PDFs change, so the first time
one is answered and its clips are all rendered, the reply and its clips are kept in
<data folder>/replies/topics. Asked again, it is said from those at once, with no LLM call and
no rendering. What a reply was made with, its `context` (the person's photo and voice, the
prepare it came from, the wiki, and whether general prompts are allowed), is kept with it: a
reply made with another context is never played, and is removed when a new one is kept.
"""

import hashlib
import json
import logging
import os
import shutil
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

REPLY_FILE = "reply.json"


def context_of(*parts: object) -> str:
    """A short digest of what a reply was made with."""
    text = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


@dataclass(frozen=True)
class Kept:
    """A reply kept: its text, as the conversation keeps it, and its clips, in order."""

    text: str
    clips: list[Path]


class TopicReplies:
    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def _entry(self, question: str) -> Path:
        name = hashlib.sha256(question.strip().casefold().encode("utf-8")).hexdigest()[:16]
        return self.folder / name

    def get(self, question: str, context: str) -> Kept | None:
        """The reply kept for the question, if it was made with this context and its clips are
        all there."""
        entry = self._entry(question)
        try:
            saved = json.loads((entry / REPLY_FILE).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            logger.warning(
                "Kept topic reply can't be read", extra={"entry": entry.name, "error": str(e)}
            )
            return None
        if saved.get("context") != context or not isinstance(saved.get("text"), str):
            return None
        clips = [entry / f"{n}.mp4" for n in range(1, int(saved.get("clips", 0)) + 1)]
        if not clips or not all(c.is_file() for c in clips):
            return None
        return Kept(saved["text"], clips)

    def keep(self, question: str, context: str, text: str, clips: Sequence[Path]) -> None:
        """Keep the reply and copies of its clips, in place of any kept for the question, and
        remove the replies kept with another context. Failures are logged only: the question is
        then answered by the LLM again next time."""
        start = time.perf_counter()
        entry = self._entry(question)
        writing = entry.with_name(f"{entry.name}.writing")
        try:
            shutil.rmtree(writing, ignore_errors=True)
            writing.mkdir(parents=True)
            for n, clip in enumerate(clips, 1):
                shutil.copyfile(clip, writing / f"{n}.mp4")
            saved = {"question": question, "context": context, "text": text, "clips": len(clips)}
            (writing / REPLY_FILE).write_text(json.dumps(saved), encoding="utf-8")
            shutil.rmtree(entry, ignore_errors=True)
            os.replace(writing, entry)
        except OSError as e:
            shutil.rmtree(writing, ignore_errors=True)
            logger.error(
                "Could not keep a topic reply",
                extra={"question": question, "entry": entry.name, "error": str(e)},
            )
            return
        removed = self._remove_others(context)
        logger.info(
            "Topic reply kept",
            extra={
                "question": question,
                "clips": len(clips),
                "stale_removed": removed,
                "duration_ms": ms_since(start),
            },
        )

    def _remove_others(self, context: str) -> int:
        """Remove the replies kept with another context; returns how many."""
        removed = 0
        for entry in self.folder.iterdir():
            try:
                saved = json.loads((entry / REPLY_FILE).read_text(encoding="utf-8"))
                if saved.get("context") == context:
                    continue
            except (OSError, ValueError):
                if entry.name.endswith(".writing"):  # another being written
                    continue
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
        return removed
