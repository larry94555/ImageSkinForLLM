"""Chat replies go before the wiki at the local LLM (roadmap R99).

Measured in R96a: a question asked while a PDF's wiki was built ran beside the wiki's request in
another of llama-server's slots, on the same 2 threads, and was written at 0.6 tokens a second in
the cloud and 3.1 on Larry's hosted machine, so its first word was heard after 70 and 74 s. The
slots also share one context, so a reply could leave the wiki's request without room. So while a
reply is being written, the wiki's request is cut off (by `ask_stop`, as when its PDF is
removed) and asked again once the reply is written, and no new wiki request starts. llama-server
keeps what it read of the cut-off request, so asking again reads little of it again.

A second slot for replies was the other choice: llama-server already has four, and it is their
sharing of the threads that slows the reply.
"""

import logging
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from typing import Any, TypeVar

from imageskin.chat import LlmCancelled, ask_stop

logger = logging.getLogger(__name__)

T = TypeVar("T")


class _CutOff(threading.Event):
    """A wiki request's `ask_stop`: set when a reply starts, and also counted as set once the
    build's own stop is (the PDF removed or replaced), which the request is still cut off by.
    A wait looks at the build's stop every 0.1 s."""

    def __init__(self, outer: threading.Event | None) -> None:
        super().__init__()
        self.outer = outer

    def is_set(self) -> bool:
        return super().is_set() or (self.outer is not None and self.outer.is_set())

    def wait(self, timeout: float | None = None) -> bool:
        end = None if timeout is None else time.monotonic() + timeout
        while not self.is_set():
            left = 0.1 if end is None else min(0.1, end - time.monotonic())
            if left <= 0:
                return False
            super().wait(left)
        return True


class RepliesFirst:
    """Holds the wiki's LLM requests back while a chat reply is being written. Only the chat's
    requests to the LLM count (`asking`, `streaming`): a reply made without it, such as the
    topics, doesn't cut the wiki off."""

    def __init__(self, settle: Callable[[], object] | None = None) -> None:
        # Called after requests are cut off for a reply, before it is sent: waits until the LLM
        # has stopped them, so the reply doesn't share it with them (R147).
        self._settle = settle
        self._changed = threading.Condition()
        self._replies = 0
        self._asking: set[_CutOff] = set()  # the wiki's requests being answered now

    @contextmanager
    def reply(self) -> Iterator[None]:
        """Around a reply's use of the LLM: the wiki's request is cut off, and waits."""
        with self._changed:
            self._replies += 1
            cut = [request for request in self._asking if not request.is_set()]
            for request in cut:
                request.set()
        try:
            # Inside the try, so a settle that fails still lets the wiki go on after the reply
            # (Codex's review).
            if cut:
                logger.info("Wiki request cut off for a reply", extra={"requests": len(cut)})
                if self._settle is not None:
                    start = time.perf_counter()
                    self._settle()
                    logger.info(
                        "Reply waited for the requests cut off to stop",
                        extra={"duration_ms": round((time.perf_counter() - start) * 1000, 1)},
                    )
            yield
        finally:
            with self._changed:
                self._replies -= 1
                self._changed.notify_all()

    def asking(self, ask: Callable[..., T], local: Callable[[], bool]) -> Callable[..., T]:
        """`ask` for the chat: while it waits for the local LLM, the wiki's requests wait."""

        def asked(*args: Any, **kwargs: Any) -> T:
            with self.reply() if local() else nullcontext():
                return ask(*args, **kwargs)

        return asked

    def streaming(
        self, stream: Callable[..., Iterator[str]], local: Callable[[], bool]
    ) -> Callable[..., Iterator[str]]:
        """`stream` for the chat: the wiki's requests wait until the reply is written."""

        def streamed(*args: Any, **kwargs: Any) -> Iterator[str]:
            with self.reply() if local() else nullcontext():
                yield from stream(*args, **kwargs)

        return streamed

    def wiki(self, ask: Callable[..., T]) -> Callable[..., T]:
        """`ask` for the wiki: it waits while a reply is written, and a request cut off by a
        reply is asked again after it. One stopped because its PDF went still ends the build."""

        def asked(*args: Any, **kwargs: Any) -> T:
            outer = ask_stop.get()
            while True:
                self._wait_for_replies(outer)
                request = _CutOff(outer)
                with self._changed:
                    if self._replies:
                        continue  # a reply started meanwhile
                    self._asking.add(request)
                token = ask_stop.set(request)
                try:
                    return ask(*args, **kwargs)
                except LlmCancelled:
                    if outer is not None and outer.is_set():
                        raise  # the PDF was removed or replaced
                    logger.info("Wiki request paused for a reply; it is asked again after it")
                finally:
                    ask_stop.reset(token)
                    with self._changed:
                        self._asking.discard(request)

        return asked

    def _wait_for_replies(self, outer: threading.Event | None) -> None:
        start = time.perf_counter()
        with self._changed:
            if not self._replies:
                return
            # Checked every second too, so a build stopped meanwhile doesn't wait out the reply.
            while self._replies and not (outer is not None and outer.is_set()):
                self._changed.wait(1.0)
        if outer is not None and outer.is_set():
            raise LlmCancelled("Stopped while waiting for a reply to be written.")
        logger.info(
            "Wiki waited for a reply",
            extra={"duration_ms": round((time.perf_counter() - start) * 1000, 1)},
        )
