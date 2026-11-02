"""What the sites take turns with (roadmap R61d, feature item 66).

The clone (Chatterbox Turbo or Pocket TTS, about 3 GB) learns one site's voice and accent, so
each site has its own. Only a set number of sites keep theirs loaded at once (`CloneBudget`,
`clones_loaded` in config.toml, 2 by default): before another site's is loaded, the one used
least recently is unloaded, and learns its site's voice and accent again when it is next asked to
speak, from what R183 keeps.

Prepare and reading PDFs take most of the machine while they run, so they run one at a time
across all sites (`Turns`): a site's job waits for another site's to finish, in the order they
asked, and shows that it is waiting. A site's own jobs may still run together, as before.
"""

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from imageskin.accent import Accent, AccentEngine
from imageskin.voice import Speech, VoiceError

logger = logging.getLogger(__name__)

# What a job waiting its turn shows (R61d).
WAITING = "Waiting for another site's preparation to finish"
# How often a waiting job looks again, and says it is still waiting (and so can stop waiting).
POLL_S = 0.25
# How many sites keep the clone loaded at once, unless config.toml says otherwise.
CLONES_LOADED = 2


def ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


class _Ticket:
    """A job waiting its turn."""

    def __init__(self, site: str) -> None:
        self.site = site


class Turns:
    """Prepare and PDF reading, one site at a time. Jobs of the site whose turn it is start at
    once, unless another site was waiting first; the others wait, in the order they asked."""

    def __init__(self, poll_s: float = POLL_S) -> None:
        self._poll_s = poll_s
        self._changed = threading.Condition()
        self._site: str | None = None  # whose turn it is
        self._running = 0  # that site's jobs running
        self._queue: list[_Ticket] = []

    def holder(self) -> str | None:
        """The site whose jobs are running, if any."""
        with self._changed:
            return self._site

    def _may_start(self, ticket: _Ticket) -> bool:
        if self._site not in (None, ticket.site):
            return False
        for waiting in self._queue:
            if waiting is ticket:
                return True
            if waiting.site != ticket.site:
                return False  # another site asked first
        return True

    @contextmanager
    def turn(self, job: str, site: str, waiting: Callable[[], None]) -> Iterator[None]:
        """Run the job once it is its site's turn. While it waits, `waiting()` is called every
        POLL_S, to show it is waiting; whatever it raises stops the wait (a cancel, say)."""
        start = time.perf_counter()
        ticket = _Ticket(site)
        waited = False
        with self._changed:
            self._queue.append(ticket)
            try:
                while not self._may_start(ticket):
                    if not waited:
                        waited = True
                        logger.info(
                            "Waiting for another site",
                            extra={"job": job, "site": site, "running": self._site},
                        )
                    waiting()
                    self._changed.wait(self._poll_s)
            except BaseException:
                self._queue.remove(ticket)
                self._changed.notify_all()
                logger.info(
                    "Stopped waiting for another site",
                    extra={"job": job, "site": site, "waited_ms": ms_since(start)},
                )
                raise
            self._queue.remove(ticket)
            self._site = site
            self._running += 1
        if waited:
            logger.info(
                "Waiting for another site",
                extra={"job": job, "site": site, "waited_ms": ms_since(start), "done": True},
            )
        try:
            yield
        finally:
            with self._changed:
                self._running -= 1
                if self._running == 0:
                    self._site = None
                self._changed.notify_all()


class CloneBudget:
    """The sites whose clone may be in memory, the one used least recently first, and never
    more than `max_loaded` of them. A site whose clone isn't loaded is let in only once another
    is unloaded: the least recently used is unloaded first, waiting for any speech it is in the
    middle of (Codex's review of PR #273). One that fails to unload is still counted, as its
    model may still be in memory, and is tried again the next time room is needed; with none
    unloaded, the site's clone is not loaded and its speech fails with the reason."""

    def __init__(self, max_loaded: int = CLONES_LOADED) -> None:
        if max_loaded < 1:
            raise ValueError("At least one site must keep the clone loaded.")
        self.max_loaded = max_loaded
        self._changed = threading.Condition()
        # Loaded, or not yet known to be unloaded, least recently used first.
        self._resident: OrderedDict[SiteClone, None] = OrderedDict()
        self._unloading: set[SiteClone] = set()

    def engine(self, clone: AccentEngine, site: str) -> "SiteClone":
        """The site's clone, counted in the budget."""
        return SiteClone(clone, site, self)

    def loaded(self) -> list[str]:
        """The sites whose clone may be in memory, the one used least recently first."""
        with self._changed:
            return [c.site for c in self._resident]

    def admit(self, clone: "SiteClone") -> None:
        """Before the clone is used: room is made for it, if it isn't counted already, by
        unloading the least recently used clones, here and now, until it fits. Raises
        VoiceError when none could be unloaded."""
        tried: set[SiteClone] = set()
        with self._changed:
            while clone not in self._resident:
                if len(self._resident) < self.max_loaded:
                    self._resident[clone] = None
                    break
                victim = next(
                    (c for c in self._resident if c not in self._unloading and c not in tried),
                    None,
                )
                if victim is None:
                    if not self._unloading:  # every other clone failed to unload just now
                        logger.error(
                            "Clone not loaded: no other site's clone could be unloaded",
                            extra={"site": clone.site, "loaded": [c.site for c in self._resident]},
                        )
                        raise VoiceError(
                            "The voice can't be loaded now: the server's voice memory is full."
                        )
                    self._changed.wait()  # another site is unloading one
                    continue
                tried.add(victim)
                self._unloading.add(victim)
                self._changed.release()
                try:
                    unloaded = victim.unload()
                finally:
                    self._changed.acquire()
                    self._unloading.discard(victim)
                    if unloaded:
                        self._resident.pop(victim, None)
                    self._changed.notify_all()
            self._resident.move_to_end(clone)

    def dropped(self, clone: "SiteClone") -> None:
        """The clone was unloaded another way (Delete my data)."""
        with self._changed:
            self._resident.pop(clone, None)
            self._changed.notify_all()


class SiteClone:
    """A site's clone in the budget: it learns the voice and accent last prepared again when it
    speaks after being unloaded. One call at a time, so an unload never cuts speech short."""

    def __init__(self, clone: AccentEngine, site: str, budget: CloneBudget) -> None:
        self._clone = clone
        self.site = site
        self._budget = budget
        self._lock = threading.RLock()
        self._prepared: tuple[str, Accent] | None = None  # what to learn again once unloaded
        self._unloaded = False
        self._used_at = time.perf_counter()

    @property
    def base(self) -> str | None:
        return self._clone.base

    @property
    def accent(self) -> Accent:
        return self._clone.accent

    def check_voice_sample(self, voice: str) -> None:
        self._clone.check_voice_sample(voice)

    def prepare(self, voice: str, accent: Accent) -> None:
        with self._lock:
            self._budget.admit(self)
            self._clone.prepare(voice, accent)
            self._prepared, self._unloaded = (voice, accent), False
            self._used_at = time.perf_counter()

    def speak(self, voice: str, text: str) -> Speech:
        with self._lock:
            self._budget.admit(self)
            if self._unloaded and self._prepared is not None:
                start = time.perf_counter()
                learned, accent = self._prepared
                self._clone.prepare(learned, accent)
                logger.info(
                    "Clone loaded again",
                    extra={"site": self.site, "accent": accent, "duration_ms": ms_since(start)},
                )
            self._unloaded = False
            try:
                return self._clone.speak(voice, text)
            finally:
                self._used_at = time.perf_counter()

    def unload(self) -> bool:
        """Free the clone's memory, once any speech it is in the middle of ends. False when it
        could not be freed, so it is still counted."""
        with self._lock:
            start = time.perf_counter()
            idle_s = round(start - self._used_at, 1)
            try:
                self._clone.forget_voice()
            except Exception:
                logger.exception("Clone not unloaded", extra={"site": self.site})
                return False
            self._unloaded = True
            logger.info(
                "Clone unloaded",
                extra={"site": self.site, "idle_s": idle_s, "duration_ms": ms_since(start)},
            )
            return True

    def forget_voice(self) -> None:
        """After Delete my data: nothing is learned again until it is prepared."""
        with self._lock:
            self._clone.forget_voice()
            self._prepared, self._unloaded = None, False
            self._budget.dropped(self)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._clone, name)
