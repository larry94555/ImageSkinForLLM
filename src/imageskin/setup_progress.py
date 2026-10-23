"""How far `imageskin time-setup` has got and about how long is left, kept in a small text file
that can be read while it runs (`cat setup-progress.txt`), since a run can take hours on a slow
machine (Larry's hosted machine, 2026-10-23)."""

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

# Prepare's steps as long as they took in the cloud (R96b, 2026-10-22). Until a step has finished
# on this machine, the time left is these scaled by how much slower this machine has been.
CLOUD_STEP_S = {
    "voice": 8.6,
    "models": 2.4,
    "shapes": 69.1,
    "loop": 252.0,
    "align": 12.1,
    "clips": 25.0,
}
Kind = Literal["uploads", "prepare", "photo", "voice", "start"]
# The steps each kind of Prepare does: another photo keeps the voice, another voice (an accent,
# or the avatar in the user's own voice) keeps the face.
STEPS: dict[str, tuple[str, ...]] = {
    "prepare": tuple(CLOUD_STEP_S),
    "photo": tuple(s for s in CLOUD_STEP_S if s != "voice"),
    "voice": ("voice", "clips"),
}
START_NOW_GUESS_S = 180  # the download, the lines and the first reply
WRITE_EVERY_S = 5.0


def duration(seconds: float) -> str:
    """`1 h 05 min`, `12 min` or `40 s`."""
    s = max(0, round(seconds))
    if s < 60:
        return f"{s} s"
    minutes = round(s / 60)
    return f"{minutes // 60} h {minutes % 60:02d} min" if minutes >= 60 else f"{minutes} min"


@dataclass
class Progress:
    """The phases of the run in order, as (label, kind), and how the current one is going."""

    path: Path | None
    phases: list[tuple[str, Kind]]
    started: float = field(default_factory=time.time)
    current: int = 0
    status: dict[str, Any] | None = None  # the current Prepare's latest status
    actual_s: float = 0.0  # Prepare's steps finished so far, and as long as they took
    cloud_s: float = 0.0
    finished: set[tuple[int, str]] = field(default_factory=set)
    written: float = 0.0

    def begin(self, label: str) -> None:
        """The phase named `label` has started."""
        labels = [p[0] for p in self.phases]
        self.current = labels.index(label) if label in labels else self.current
        self.status = None
        self.write(force=True)

    def prepare(self, status: dict[str, Any]) -> None:
        """The current Prepare's latest status, with each step's time once it has finished."""
        self.status = status
        for step in status.get("steps") or []:
            key, seconds = step.get("key"), step.get("seconds")
            if key in CLOUD_STEP_S and seconds and (self.current, key) not in self.finished:
                self.finished.add((self.current, key))
                self.actual_s += seconds
                self.cloud_s += CLOUD_STEP_S[key]
        self.write()

    @property
    def slower(self) -> float:
        """How many times slower than the cloud this machine's Prepare steps have been."""
        return self.actual_s / self.cloud_s if self.cloud_s else 1.0

    def left_in_prepare(self) -> float:
        """About how long the current Prepare has left."""
        left = 0.0
        for step in (self.status or {}).get("steps") or []:
            if step.get("done", 0) >= step.get("total", 1):
                continue
            if step.get("left_s") is not None:
                left += step["left_s"]
            else:
                left += CLOUD_STEP_S.get(step.get("key", ""), 0.0) * self.slower
        return left

    def guess(self, kind: Kind) -> float:
        """About how long a phase of this kind takes on this machine, before it starts."""
        if kind == "start":
            return START_NOW_GUESS_S
        return sum(CLOUD_STEP_S[s] for s in STEPS.get(kind, ())) * self.slower

    def left_after(self) -> float:
        """About how long the phases after the current one take."""
        return sum(self.guess(kind) for _, kind in self.phases[self.current + 1 :])

    def text(self, now: float) -> str:
        label, kind = self.phases[self.current]
        lines = [
            f"time-setup started {clock(self.started)}, {duration(now - self.started)} ago.",
            f"Now: {self.current + 1} of {len(self.phases)}, {label}.",
        ]
        if kind in STEPS and self.status:
            steps = self.status.get("steps") or []
            running = next((s for s in steps if s.get("done", 0) < s.get("total", 1)), None)
            if running:
                lines.append(
                    f"Step: {running.get('label', running.get('key'))}"
                    f" ({running.get('done', 0)} of {running.get('total', 1)})."
                )
            left_now = self.left_in_prepare()
        else:
            left_now = self.guess(kind)
        if kind in STEPS:
            lines.append(f"About {duration(left_now)} left in this Prepare.")
        total = left_now + self.left_after()
        how = (
            f"this machine's Prepare steps have taken {self.slower:.1f} times as long as in the"
            " cloud"
            if self.cloud_s
            else "a rough guess until Prepare's first step finishes"
        )
        lines.append(
            f"About {duration(total)} left in all, finishing around {clock(now + total)} ({how})."
        )
        done = [p[0] for p in self.phases[: self.current]]
        if done:
            lines.append("Done: " + "; ".join(done) + ".")
        return "\n".join(lines) + "\n"

    def write(self, force: bool = False) -> None:
        now = time.time()
        if self.path is None or (not force and now - self.written < WRITE_EVERY_S):
            return
        self.written = now
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            saving = self.path.with_suffix(".saving")
            saving.write_text(self.text(now), encoding="utf-8")
            saving.replace(self.path)
        except OSError as e:
            logger.warning("Could not write the progress file", extra={"error": str(e)})

    def done(self, report: Path, failed: int) -> None:
        """The run has finished: when, and where its results are."""
        now = time.time()
        problems = (
            f"Steps that failed: {failed}; see the Error columns." if failed else "No errors."
        )
        self.final(
            f"time-setup finished {clock(now)}, after {duration(now - self.started)}. {problems}\n"
            f"Results: {report}\n"
        )

    def stopped(self, error: BaseException) -> None:
        """The run stopped before it finished."""
        now = time.time()
        label = self.phases[self.current][0] if self.phases else "starting"
        self.final(
            f"time-setup stopped {clock(now)}, after {duration(now - self.started)}, during"
            f" {label}: {error!r}\n"
        )

    def final(self, text: str) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(text, encoding="utf-8")
        except OSError as e:
            logger.warning("Could not write the progress file", extra={"error": str(e)})


def clock(at: float) -> str:
    return (datetime.fromtimestamp(0, UTC) + timedelta(seconds=at)).strftime("%H:%M UTC")
