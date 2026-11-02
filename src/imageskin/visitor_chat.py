"""Each visitor's own conversation (roadmap R65a, items 31 and 66).

A site's visitors each get a conversation of their own, found by a cookie for that browser, so
one visitor's questions are never read with another's. The site's signed-in host keeps the
site's own conversation (`conversation.json`), as before, so theirs follows them from browser to
browser. A visitor's conversation is kept in `conversations/<key>.json`, the key being a hash of
the cookie's token, so the folder never holds the token itself. One not used for 30 days is
removed."""

import hashlib
import logging
import os
import re
import secrets
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)

COOKIE = "imageskin_visitor"
COOKIE_MAX_AGE = 60 * 60 * 24 * 400  # as long as browsers keep a cookie
FOLDER = "conversations"
UNUSED_DAYS = 30  # a conversation not used for this long is removed *(default)*
SWEEP_S = 60 * 60  # how often, at most, the old ones are looked for
TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,64}$")

C = TypeVar("C")


def new_token() -> str:
    return secrets.token_urlsafe(24)


def valid(token: str | None) -> bool:
    """Whether the cookie holds a token this server could have made: anything else gets a new
    one, so a hand-made cookie can't name a file."""
    return token is not None and TOKEN.match(token) is not None


def key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:32]


class VisitorConversations(Generic[C]):
    """The site's visitors' conversations, each made by `make` from its file the first time it
    is asked for, and kept in memory while it is used."""

    def __init__(
        self,
        home: Path,
        make: Callable[[Path], C],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.folder = home / FOLDER
        self._make = make
        self.clock = clock
        self._lock = threading.Lock()
        self._open: dict[str, C] = {}
        self._swept_at = 0.0

    def path(self, token: str) -> Path:
        return self.folder / f"{key(token)}.json"

    def of(self, token: str) -> C:
        """The visitor's conversation, started when they have none. Each use counts, so it is
        kept while the visitor comes back."""
        self.sweep()
        k = key(token)
        path = self.path(token)
        with self._lock:
            conversation = self._open.get(k)
            if conversation is None:
                self.folder.mkdir(parents=True, exist_ok=True)
                started = not path.exists()
                conversation = self._make(path)
                self._open[k] = conversation
                if started:
                    logger.info("Visitor conversation started", extra={"visitor": k[:8]})
        try:
            if path.exists():
                os.utime(path)  # used now
        except OSError as e:
            logger.warning(
                "Could not note a visitor's conversation was used", extra={"error": str(e)}
            )
        return conversation

    def open(self) -> list[C]:
        """Every visitor conversation in memory, as Delete my data clears them all."""
        with self._lock:
            return list(self._open.values())

    def sweep(self, force: bool = False) -> int:
        """Remove the conversations not used for UNUSED_DAYS, at most once an hour unless
        `force`. Returns how many were removed."""
        now = self.clock()
        with self._lock:
            if not force and now - self._swept_at < SWEEP_S:
                return 0
            self._swept_at = now
            removed = 0
            for path in self.folder.glob("*.json") if self.folder.is_dir() else []:
                try:
                    if now - path.stat().st_mtime < UNUSED_DAYS * 86400:
                        continue
                    path.unlink()
                except OSError as e:
                    logger.warning(
                        "Could not remove a visitor's conversation", extra={"error": str(e)}
                    )
                    continue
                self._open.pop(path.stem, None)
                removed += 1
        if removed:
            logger.info("Visitor conversations removed", extra={"removed": removed})
        return removed

    def forget_all(self) -> int:
        """Remove every visitor's conversation, for Delete my data (R31). Returns how many
        files were removed."""
        with self._lock:
            self._open.clear()
            removed = 0
            for path in self.folder.glob("*.json") if self.folder.is_dir() else []:
                try:
                    path.unlink()
                    removed += 1
                except OSError as e:
                    logger.error(
                        "Could not remove a visitor's conversation", extra={"error": str(e)}
                    )
        logger.info("Visitor conversations removed", extra={"removed": removed, "why": "delete"})
        return removed
