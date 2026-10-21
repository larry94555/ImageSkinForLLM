"""Where the time goes in a reply, as the server sees it (roadmap R96): the waits before the
prompt reaches the LLM, the LLM's first token, first sentence and last token, and llama-server's
own timings. The chat API returns them with the reply, so `imageskin time-reply` can measure a
reply without the browser."""

import time
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Any

# The fields of llama-server's `timings` (sent with the last piece of a streamed reply) that are
# kept: tokens read from the prompt and their speed, tokens reused from its cache, and tokens
# written and their speed.
LLM_TIMING_KEYS = (
    "cache_n",
    "prompt_n",
    "prompt_ms",
    "prompt_per_second",
    "predicted_n",
    "predicted_ms",
    "predicted_per_second",
)


@dataclass
class ReplyTimes:
    """One prompt's times, as time.perf_counter() seconds (the clock of the clips' times), or
    milliseconds where the name says so. A time is None when it didn't happen: a reply made
    without the LLM has no tokens."""

    received_at: float
    waited_warm_up_ms: float = 0.0  # for the replies' warm-up after a sample was accepted
    waited_turn_ms: float = 0.0  # behind the prompt before, or the wiki's LLM request
    history_tokens: int | None = None  # the conversation sent with the prompt
    prompt_sent_at: float | None = None
    first_token_at: float | None = None
    first_sentence_at: float | None = None
    last_token_at: float | None = None
    answered_at: float | None = None
    llm: dict[str, Any] | None = None  # llama-server's own timings; a provider sends none

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# The prompt being answered on this thread, if its times are being kept.
current: ContextVar[ReplyTimes | None] = ContextVar("reply_times", default=None)


def note(**times: Any) -> None:
    """Set these fields on the prompt being answered, if any. A time already set is kept, so
    only the first token or sentence counts."""
    kept = current.get()
    if kept is None:
        return
    for name, value in times.items():
        if getattr(kept, name) is None or name in ("last_token_at", "answered_at", "llm"):
            setattr(kept, name, value)


def note_now(name: str) -> None:
    """Note that `name` happened now."""
    note(**{name: time.perf_counter()})


def note_llm(timings: object) -> None:
    """Keep llama-server's timings for the prompt being answered, when it sent them."""
    if isinstance(timings, dict):
        note(llm={k: timings[k] for k in LLM_TIMING_KEYS if k in timings})
