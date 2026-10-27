"""A steady pace in long replies (roadmap R130): when to start playing a reply's clips so the
rest keeps up, and the pace the reply was heard at, for the log.

R129 (experiments/long_reply/) found replies waiting for clips not made in time: behind the clips
before them when the voice was slower than real time (Kokoro at 1.05 to 1.22 times in a cloud
session, the hosted machine's voice at 2.8 to 2.95), or for the LLM's text. Each gap pushes the
rest of the reply later, so starting it later by the gaps' total ends it at the same time with
no gap at all. The gaps a reply would have had if played at once are measured on the machine
it runs on, and the next reply starts later by the recent replies' median, at most MAX_HOLD_S
more, so a slow voice (Chatterbox at 3 to 4 times) still starts within a few seconds more.
"""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

MAX_HOLD_S = 15.0  # the most playback is held back after the first clip is ready
GAP_S = 0.3  # a gap at least this long is logged, with its cause


def hold_s(recent_gaps: Sequence[float]) -> float:
    """How long to hold the next reply's playback back: the median of the gaps the recent
    replies would have had if played at once, at most MAX_HOLD_S; none before any reply."""
    return min(MAX_HOLD_S, statistics.median(recent_gaps)) if recent_gaps else 0.0


@dataclass(frozen=True)
class ClipPlay:
    """One clip's times, as time.perf_counter() seconds, and its speech's length and words."""

    sentence_at: float  # its text came from the LLM
    started_at: float | None  # its voice step began
    listed_at: float  # it was listed for the browser, as its video began to be written
    whole_at: float  # its video was whole
    speech_s: float
    words: int


@dataclass(frozen=True)
class Gap:
    clip: int  # the clip waited for, from 1
    seconds: float
    cause: str  # `text late`, `queued` or `slow to make`, as R129 named them


@dataclass(frozen=True)
class Pace:
    words: int
    heard_s: float  # from the first word to the end of the last clip
    wpm: float  # words a minute heard
    gaps: list[Gap]


def heard(clips: Sequence[ClipPlay], start: float) -> Pace:
    """The pace the reply is heard at when playback starts at `start`, as the server sees it:
    each clip plays once the one before has ended and it is listed, and doesn't end before it
    is whole (the browser follows a clip as it is written). The browser's own switch between
    clips, under 0.1 s (R127), is left out."""
    gaps: list[Gap] = []
    end = before = start
    for n, c in enumerate(clips, 1):
        begin = max(end, c.listed_at)
        if n > 1 and begin - end >= GAP_S:
            gaps.append(Gap(n, round(begin - end, 2), _cause(c, before)))
        before, end = begin, max(begin + c.speech_s, c.whole_at)
    words = sum(c.words for c in clips)
    heard_s = end - start
    wpm = 60 * words / heard_s if heard_s > 0 else 0.0
    return Pace(words, round(heard_s, 2), round(wpm), gaps)


def _cause(clip: ClipPlay, before_began: float) -> str:
    """Why the clip wasn't ready when the one before it (which began at `before_began`) ended."""
    if clip.sentence_at >= before_began:
        return "text late"  # its text came only once the clip before was playing
    if clip.started_at is not None and clip.started_at - clip.sentence_at >= GAP_S:
        return "queued"  # made behind the clips before it
    return "slow to make"
