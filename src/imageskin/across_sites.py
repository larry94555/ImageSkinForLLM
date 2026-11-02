"""What the sites take turns with (roadmap R61d, feature item 66).

The clone (Chatterbox Turbo or Pocket TTS, about 3 GB) learns one site's voice and accent, so
each site has its own. Only a set number of sites keep theirs loaded at once (`CloneBudget`,
`clones_loaded` in config.toml, 2 by default): when another site's is used, the one used least
recently is unloaded, and learns its site's voice and accent again when it is next asked to
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
from imageskin.voice import Speech

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
    """Which sites' clones are loaded, the one used least recently first, and at most
    `max_loaded` of them: using another unloads the least recently used, in the background."""

    def __init__(self, max_loaded: int = CLONES_LOADED) -> None:
        if max_loaded < 1:
            raise ValueError("At least one site must keep the clone loaded.")
        self.max_loaded = max_loaded
        self._lock = threading.Lock()
        self._loaded: OrderedDict[SiteClone, None] = OrderedDict()
        self._unloading: list[threading.Thread] = []

    def engine(self, clone: AccentEngine, site: str) -> "SiteClone":
        """The site's clone, counted in the budget."""
        return SiteClone(clone, site, self)

    def loaded(self) -> list[str]:
        """The sites whose clone is loaded, the one used least recently first."""
        with self._lock:
            return [c.site for c in self._loaded]

    def is_loaded(self, clone: "SiteClone") -> bool:
        with self._lock:
            return clone in self._loaded

    def used(self, clone: "SiteClone") -> None:
        """The clone was just used: it is loaded, and the least recently used past the budget
        are unloaded."""
        with self._lock:
            self._loaded[clone] = None
            self._loaded.move_to_end(clone)
            victims = []
            while len(self._loaded) > self.max_loaded:
                victim, _ = self._loaded.popitem(last=False)
                victims.append(victim)
            # In the background: the victim may be speaking, and waiting for it here could
            # hold up this site's speech, or wait on a site waiting on this one.
            threads = [
                threading.Thread(target=v.unload, name="clone-unload", daemon=True) for v in victims
            ]
            self._unloading = [t for t in self._unloading if t.is_alive()] + threads
        for t in threads:
            t.start()

    def dropped(self, clone: "SiteClone") -> None:
        """The clone was unloaded another way (Delete my data)."""
        with self._lock:
            self._loaded.pop(clone, None)

    def wait(self, timeout: float = 30) -> None:
        """For tests: until the clones being unloaded are."""
        with self._lock:
            threads = list(self._unloading)
        for t in threads:
            t.join(timeout)


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
            self._budget.used(self)
            self._clone.prepare(voice, accent)
            self._prepared, self._unloaded = (voice, accent), False
            self._used_at = time.perf_counter()

    def speak(self, voice: str, text: str) -> Speech:
        with self._lock:
            self._budget.used(self)
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

    def unload(self) -> None:
        """Free the clone's memory, unless it was used again since it was picked."""
        with self._lock:
            if self._budget.is_loaded(self) or self._unloaded:
                return
            start = time.perf_counter()
            idle_s = round(start - self._used_at, 1)
            try:
                self._clone.forget_voice()
            except Exception:
                logger.exception("Clone not unloaded", extra={"site": self.site})
                return
            self._unloaded = True
            logger.info(
                "Clone unloaded",
                extra={"site": self.site, "idle_s": idle_s, "duration_ms": ms_since(start)},
            )

    def forget_voice(self) -> None:
        """After Delete my data: nothing is learned again until it is prepared."""
        with self._lock:
            self._clone.forget_voice()
            self._prepared, self._unloaded = None, False
            self._budget.dropped(self)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._clone, name)
