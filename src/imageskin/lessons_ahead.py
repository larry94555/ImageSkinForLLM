"""Each topic's first lesson part, written ahead (roadmap R98a, items 12, 54).

Picking a topic sends "Teach me about …", and the LLM wrote that lesson's first part, the topic's
main ideas, from scratch each time, so "thinking…" ran about as long as any answer from the wiki.
Once the wiki is built, that part is written here for every topic in the background and saved
with the wiki (`lessons.json` in its folder), and a topic picked later is said from it at once.

Each saved part is kept with a key made from what the LLM was asked for it: the instruction and
the material, which come from the topic's wiki entries and what the content has on it. A part is
said only while what a lesson would ask now has the same key, so a topic whose pages are edited,
rebuilt or gone back to is taught as before until its part is written again, and one whose PDF
is removed is dropped at the next round. A round runs after the wiki is built or changed, at the
start, and when Teach me is turned on; it waits while a wiki is being built, and its requests to
the LLM go after the chat's (`RepliesFirst.wiki`, R99), so a reply never waits for one.
"""

import contextlib
import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from imageskin.chat import LlmError, Teach, ms_since
from imageskin.sentences import SentenceSplitter

logger = logging.getLogger(__name__)

LESSONS_FILE = "lessons.json"
LESSONS_FORMAT = 1
RETRY_S = 60.0  # after the LLM couldn't be reached, the next round starts this much later


def key(teach: Teach) -> str:
    """What the LLM is asked for the part, as a key: the same exactly when the ask is."""
    asked = json.dumps([teach.instruction, teach.material], ensure_ascii=False)
    return hashlib.sha256(asked.encode("utf-8")).hexdigest()


def sentences(text: str) -> list[str]:
    """The saved part as sentences, split as a streamed reply's are."""
    splitter = SentenceSplitter()
    return [s for s in [*splitter.feed(text), *splitter.flush()] if s.strip()]


class LessonsAhead:
    def __init__(
        self,
        folder: Path,
        first_parts: Callable[[], dict[str, Teach]],  # each topic's first part, as asked now
        write: Callable[[Teach], str],  # the LLM's answer to one
        wanted: Callable[[], bool],  # whether Teach me is on
        busy: Callable[[], bool],  # whether a wiki is being built
        retry_s: float = RETRY_S,
    ) -> None:
        self.path = folder / LESSONS_FILE
        self._first_parts = first_parts
        self._write = write
        self._wanted = wanted
        self._busy = busy
        self.retry_s = retry_s
        self._lock = threading.Lock()
        self._again = False  # a round was asked for since the last one began
        self._ready = False  # the last round saved every topic's part, with none asked since
        self._worker: threading.Thread | None = None

    def saved(self, topic: str, teach: Teach) -> list[str] | None:
        """The topic's saved part as sentences, if it was written from what `teach` asks."""
        lesson = self._load().get(topic)
        if lesson is None or lesson.get("key") != key(teach):
            return None
        return sentences(str(lesson.get("text", ""))) or None

    def status(self) -> dict[str, Any]:
        """Whether Teach me is on, whether a round is running, whether every topic's part is
        saved, and the topics saved (`imageskin time-pdf` waits for `ready`)."""
        with self._lock:
            writing, ready = self._worker is not None, self._ready
        return {
            "wanted": self._wanted(),
            "writing": writing,
            "ready": ready and not writing,
            "saved": sorted(self._load()),
        }

    def refresh(self) -> None:
        """Write the parts missing or out of date, in the background. Answers at once; asked
        for while a round runs, another follows it."""
        with self._lock:
            self._again = True
            self._ready = False
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, name="lessons", daemon=True)
                self._worker.start()

    def wait(self, timeout: float = 30) -> None:
        """Until the rounds asked for are done (tests)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self._lock:
                worker = self._worker
            if worker is None:
                return
            worker.join(max(0.0, end - time.monotonic()))

    def _run(self) -> None:
        while True:
            with self._lock:
                if not self._again:
                    self._worker = None
                    return
                self._again = False
            try:
                self._round()
            except Exception as e:  # the next round tries again
                logger.exception("Could not write the lessons ahead", extra={"error": repr(e)})

    def _round(self) -> None:
        if not self._wanted():
            logger.info("Lessons not written ahead: Teach me is off")
            return
        if self._busy():
            logger.info("Lessons wait for the wiki to be built")  # a round follows the build
            return
        start = time.perf_counter()
        firsts = self._first_parts()
        saved = self._load()
        kept = {topic: lesson for topic, lesson in saved.items() if topic in firsts}
        if len(kept) < len(saved):
            self._save(kept)
            logger.info("Lessons dropped", extra={"topics": sorted(set(saved) - set(kept))})
        written = 0
        stopped = None  # why the round stopped before the last topic
        for topic, teach in firsts.items():
            with self._lock:
                changed = self._again
            # The wiki changed, is being built or Teach me was turned off: the next round,
            # after it, starts again or says so.
            if changed:
                stopped = "wiki changed"
            elif self._busy():
                stopped = "wiki being built"
            elif not self._wanted():
                stopped = "Teach me turned off"
            if stopped is not None:
                break
            k = key(teach)
            if kept.get(topic, {}).get("key") == k:
                continue
            began = time.perf_counter()
            try:
                text = self._write(teach).strip()
            except LlmError as e:
                logger.error(
                    "Lesson not saved",
                    extra={"topic": topic, "error": str(e), "retry_s": self.retry_s},
                )
                retry = threading.Timer(self.retry_s, self.refresh)
                retry.daemon = True
                retry.start()
                stopped = "LLM error"
                break
            if not text:
                logger.warning("Lesson not saved: the LLM wrote nothing", extra={"topic": topic})
                continue
            kept[topic] = {"key": k, "text": text}
            if not self._save(kept):
                stopped = "not saved"
                break
            written += 1
            logger.info(
                "Lesson saved",
                extra={"topic": topic, "chars": len(text), "duration_ms": ms_since(began)},
            )
        missing = sum(
            1 for topic, teach in firsts.items() if kept.get(topic, {}).get("key") != key(teach)
        )
        with self._lock:
            self._ready = stopped is None and missing == 0 and not self._again
        logger.info(
            "Lessons written ahead",
            extra={
                "topics": len(firsts),
                "written": written,
                "saved": len(kept),
                "missing": missing,
                "stopped": stopped,
                "duration_ms": ms_since(start),
            },
        )

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            logger.error("Could not read the saved lessons", extra={"error": str(e)})
            return {}
        if not isinstance(saved, dict) or saved.get("format") != LESSONS_FORMAT:
            return {}
        lessons = saved.get("lessons")
        return lessons if isinstance(lessons, dict) else {}

    def _save(self, lessons: dict[str, dict[str, Any]]) -> bool:
        writing = self.path.with_suffix(".writing")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = {"format": LESSONS_FORMAT, "lessons": lessons}
            writing.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            writing.replace(self.path)
        except OSError as e:
            with contextlib.suppress(OSError):
                writing.unlink(missing_ok=True)
            logger.error("Could not save the lessons", extra={"error": str(e)})
            return False
        return True
