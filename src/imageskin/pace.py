"""A steady pace in long replies (roadmap R130, R161): when to start playing a reply's clips so
the rest keeps up, and the pace the reply was heard at, for the log.

R129 (experiments/long_reply/) found replies waiting for clips not made in time: behind the clips
before them when the voice was slower than real time, or for the LLM's text. Each gap pushes the
rest of the reply later, so starting it later by the gaps' total ends it at the same time with
no gap at all. R130 held each reply back by the gaps the last replies had, kept in memory, so
the first reply after a restart, or one longer than the last, still broke up (R161). Now the
reply starts once the gaps foreseen from then on are under PLAY_THROUGH_GAP_S, worked out at
every look from how fast this machine makes clips and the LLM writes (kept in a file across
restarts), and at most MAX_HOLD_S after its first clip is ready.
"""

import json
import logging
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_HOLD_S = 30.0  # the most playback is held back after the first clip is ready (R161)
GAP_S = 0.3  # a gap at least this long is logged, with its cause
# Playback starts once the gaps foreseen from then on total no more than this (R161).
PLAY_THROUGH_GAP_S = 0.5

# Before this machine has made any clip: R129's cloud figures (a clip takes 0.5 s and as long
# again as it plays), Kokoro's 0.37 s a word, Gemma's 205 words a minute and a reply of 120.
FIXED_S = 0.5
PER_SPEECH_S = 1.0
SPEECH_S_PER_WORD = 0.37
LLM_WORDS_PER_S = 205 / 60
REPLY_WORDS = 120
# The words a clip waits for when the voice waits for text: a long sentence, as a sentence is
# spoken only once it is written. Fitted to R129's three replies so none pauses over 3 s.
CLIP_WORDS = 25
# The most words a clip of sentences joined while the voice was busy may have: about 10 s of
# speech, well under the 40 s at which Chatterbox stops (reply_video.JOIN_WORDS).
JOIN_WORDS = 30
# Clips whose speech spans less than this are too alike to fit a fixed cost and a cost per second
# by: on the hosted machine, two short clips (1.4 s and 2.5 s) gave 0.4 s a second of speech where
# the next clip took 1.4 (R161), and the reply broke up. Then the cost is all per second.
MIN_SPREAD_S = 3.0
KEEP_CLIPS = 40  # clips measured, for how fast this machine makes them
KEEP_REPLIES = 5  # replies measured, for their length and the LLM's pace


@dataclass(frozen=True)
class Machine:
    """How fast this machine makes a clip and the LLM writes, from the replies measured."""

    fixed_s: float = FIXED_S  # a clip takes this long, plus
    per_speech_s: float = PER_SPEECH_S  # this long per second of its speech
    speech_s_per_word: float = SPEECH_S_PER_WORD
    llm_words_per_s: float = LLM_WORDS_PER_S
    reply_words: float = REPLY_WORDS  # a reply's usual length

    def make_s(self, words: float) -> float:
        return self.fixed_s + self.per_speech_s * words * self.speech_s_per_word


def fit(clips: Sequence[tuple[float, float, int]]) -> tuple[float, float, float]:
    """The fixed cost, the cost per second of speech and the seconds of speech a word, from
    clips as (seconds to make, seconds of speech, words), by least squares."""
    if len(clips) < 2:
        return FIXED_S, PER_SPEECH_S, SPEECH_S_PER_WORD
    make = [c[0] for c in clips]
    speech = [c[1] for c in clips]
    words = sum(c[2] for c in clips)
    per_word = sum(speech) / words if words else SPEECH_S_PER_WORD
    mean_s, mean_m = statistics.fmean(speech), statistics.fmean(make)
    var = sum((s - mean_s) ** 2 for s in speech)
    if max(speech) - min(speech) >= MIN_SPREAD_S:
        slope = sum((s - mean_s) * (m - mean_m) for s, m in zip(speech, make, strict=True)) / var
        fixed = mean_m - slope * mean_s
        if slope > 0 and fixed >= 0:
            return fixed, slope, per_word
    # Clips too alike, or a fit that makes no sense: all of a clip's time per second of speech.
    return 0.0, sum(make) / sum(speech), per_word


class PaceStore:
    """What this machine measured, kept in a JSON file so a restart doesn't forget it (R161):
    the last KEEP_CLIPS clips' times and the last KEEP_REPLIES replies' words and LLM pace."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.clips: list[tuple[float, float, int]] = []
        self.replies: list[tuple[int, float]] = []  # words, LLM words a second
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.clips = [(float(m), float(s), int(w)) for m, s, w in data["clips"]]
            self.replies = [(int(w), float(r)) for w, r in data["replies"]]
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError, TypeError) as e:
            logger.warning("Could not read the reply pace", extra={"error": str(e)})

    def machine(self) -> Machine:
        fixed, per_speech, per_word = fit(self.clips)
        words = [w for w, _ in self.replies]
        rates = [r for _, r in self.replies if r > 0]
        return Machine(
            fixed,
            per_speech,
            per_word,
            statistics.median(rates) if rates else LLM_WORDS_PER_S,
            statistics.median(words) if words else REPLY_WORDS,
        )

    def add(self, clips: Sequence[tuple[float, float, int]], words: int, rate: float) -> None:
        """Add a reply's clips, its words and the LLM's words a second, and save."""
        self.clips = [*self.clips, *clips][-KEEP_CLIPS:]
        self.replies = [*self.replies, (words, rate)][-KEEP_REPLIES:]
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = {"clips": self.clips, "replies": self.replies}
            self.path.write_text(json.dumps(data), encoding="utf-8")
        except OSError as e:
            logger.warning("Could not save the reply pace", extra={"error": str(e)})


def gaps_ahead(
    machine: Machine,
    *,
    ahead_s: float,
    making: tuple[float, int] | None,
    waiting_words: int,
    words_to_come: float,
    llm_words_per_s: float,
) -> float:
    """The seconds of gaps foreseen if playback starts now (R161), from how fast this machine
    makes clips and the LLM writes. `ahead_s` is the speech in clips ready to play;
    `making` the clip being spoken, as (seconds since it began, words); `waiting_words` the
    words written but not yet begun; `words_to_come` those not yet written. Clips are made one
    after another, joining up to JOIN_WORDS of the text waiting, as reply_video does."""
    play_end = ahead_s  # times in seconds from now
    free = 0.0  # when the engines are free
    gaps = 0.0
    if making is not None:
        free = max(0.0, machine.make_s(making[1]) - making[0])
        gaps += max(0.0, free - play_end)
        play_end = max(play_end, free) + making[1] * machine.speech_s_per_word
    waiting, to_come, written = float(waiting_words), max(0.0, words_to_come), 0.0
    rate = max(llm_words_per_s, 0.1)
    while waiting + to_come >= 1:
        want = min(JOIN_WORDS, max(waiting, min(CLIP_WORDS, waiting + to_come)))
        more = max(0.0, want - waiting)  # words still to be written for this clip
        written += more
        waiting, to_come = waiting + more, to_come - more
        start = max(free, written / rate)
        free = start + machine.make_s(want)
        gaps += max(0.0, free - play_end)
        play_end = max(play_end, free) + want * machine.speech_s_per_word
        waiting -= want
    return gaps


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
