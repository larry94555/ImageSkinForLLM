"""The steps of each prompt's thinking (roadmap R134c) as a Markdown file that is easy to open:
`speed/thinking-steps.md` in the data folder, the latest prompts first, each with a table of
its steps, when each started and ended and its share of the whole. The same is kept beside it as
JSON, so the file survives a restart and a first prompt after a start keeps the ones before."""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from imageskin.reply_times import ReplyTimes, ms_from
from imageskin.time_llm import write_atomically

logger = logging.getLogger(__name__)

NAME = "thinking-steps"
KEEP = 20  # prompts kept in the file, the latest first
PROMPT_CHARS = 80  # of the prompt, in its heading
# Details a step may carry, as the table names them.
DETAILS = {
    "tokens_read": "tokens read",
    "tokens_reused": "tokens reused",
    "tokens_written": "tokens written",
    "requests": "requests cut off",
    "error": "error",
}


def seconds(ms: float | None) -> str:
    return "-" if ms is None else f"{ms / 1000:.1f} s"


def entry(times: ReplyTimes, prompt: str, summary_running: bool) -> dict[str, Any]:
    """One prompt's steps, in the order they started, with when it was answered."""
    total = None if times.answered_at is None else ms_from(times, times.answered_at)
    short = prompt if len(prompt) <= PROMPT_CHARS else prompt[: PROMPT_CHARS - 1] + "…"
    return {
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "prompt": short,
        "total_ms": total,
        "summary_running": summary_running,
        "steps": sorted(times.steps, key=lambda s: (s["start_ms"], -s["duration_ms"])),
    }


def prompt_markdown(e: dict[str, Any]) -> list[str]:
    total = e["total_ms"]
    steps = e["steps"]
    longest = max(steps, key=lambda s: s["duration_ms"], default=None)
    out = [f"## {e['at']}: {e['prompt']}", ""]
    line = f"Answered in **{seconds(total)}**"
    if longest is not None:
        line += f"; the longest step was **{longest['step']}** ({seconds(longest['duration_ms'])})"
    out += [line + ".", ""]
    if e["summary_running"]:
        out += ["A summary of the conversation was being made at the same time.", ""]
    if not steps:
        return out + ["No steps were timed.", ""]
    out += ["| Step | Starts | Ends | Takes | Share | Details |", "|---|---|---|---|---|---|"]
    for s in steps:
        # A part of a wait (the warm-up's parts) is shown under the wait.
        name = (
            f"↳ {s['step'][len('warm-up: ') :]}" if s["step"].startswith("warm-up: ") else s["step"]
        )
        share = "-" if not total else f"{round(100 * s['duration_ms'] / total)}%"
        details = ", ".join(
            f"{label} {s[key]}" for key, label in DETAILS.items() if s.get(key) is not None
        )
        out.append(
            f"| {name} | {seconds(s['start_ms'])} | {seconds(s['end_ms'])} "
            f"| {seconds(s['duration_ms'])} | {share} | {details} |"
        )
    return out + [""]


def markdown(entries: list[dict[str, Any]]) -> str:
    out = [
        "# Where the thinking goes",
        "",
        f"The last {KEEP} prompts, the latest first. Each step's start and end are counted from "
        "when the prompt reached the app; steps can overlap, as the warm-up's parts (↳) run "
        "during the wait for it.",
        "",
    ]
    for e in entries:
        out += prompt_markdown(e)
    return "\n".join(out)


class ThinkingReport:
    """Adds each answered prompt to the file. A failure to write it is logged and never fails
    the reply."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self.folder / f"{NAME}.md"

    def add(self, times: ReplyTimes, prompt: str, summary_running: bool = False) -> None:
        start = time.perf_counter()
        try:
            with self._lock:
                self.folder.mkdir(parents=True, exist_ok=True)
                kept = self._load()
                entries = [entry(times, prompt, summary_running), *kept][:KEEP]
                write_atomically(self.folder / f"{NAME}.json", json.dumps(entries, indent=2))
                write_atomically(self.path, markdown(entries))
        except Exception:
            logger.exception("Could not write the thinking steps", extra={"path": str(self.path)})
            return
        logger.info(
            "Thinking steps written",
            extra={
                "path": str(self.path),
                "prompts": len(entries),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )

    def _load(self) -> list[dict[str, Any]]:
        try:
            kept = json.loads((self.folder / f"{NAME}.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, ValueError):
            logger.warning("Thinking steps file unreadable; starting it again")
            return []
        return kept if isinstance(kept, list) else []
