"""R129: where the pauses come from in a long reply. An experiment, not part of the app.

    python experiments/long_reply/long_reply.py CLIPS_JSONL [--url URL] [-o long-reply]
        [--label cloud-kokoro] [--voice af_heart | --voice-sample WAV] [--no-own-rate]
        [prompt ...]

The app must be running under serve_logged.py, which writes CLIPS_JSONL. Each prompt (by
default the three in replies.py, which fake_llm.py answers) is sent and its clips followed with
R96's `time-reply` (`time_reply.measure`), and each clip's row is joined with its line in
CLIPS_JSONL. For each clip it then has its words, where its text ends (a full stop, a clause or
neither), when its text came from the LLM, how long it waited, how long its voice and video took
to make, how long it plays and how long its speech is, the silence the speech starts and ends
with, when it was ready against when the clip before it ended, the gap heard (playback waiting
for it), the whole pause heard before it (the silence at the end of the clip before, the gap and
the silence at its start), and why there was a gap.

For each reply: the speaking rate heard (words a minute from the first word to the end of the
last clip), the rate inside the clips (gaps left out), the speech rate (the clips' speech with
their silence left out: the voice's own pace as the app spoke it), the voice's own rate outside
the app (the reply spoken a whole sentence at a time with `imageskin say`'s engine, the silence
at each sentence's start and end left out, after the replies, unless --no-own-rate), the LLM's
writing rate, and how fast clips are made against how long they play. It waits up to --wait
seconds for the app to start. The tables go to <out>/long-reply-<label>.md and .json, and one
timeline a reply to <out>/timeline-<label>-<n>.png when matplotlib is installed.
"""

import argparse
import json
import logging
import re
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

logger = logging.getLogger("long_reply")

GAP_MS = 300  # a gap or pause heard longer than this is counted (R130's default)
WAITED_MS = 100  # waiting longer than this for the clip before it means it was queued
REFUSED = (400, 401, 403, 409)  # the app refused the prompt: no other will do better
WAIT_EVERY_S = 3  # how often to ask whether the app has started
TOGETHER_MS = 50  # clips whose text came this close together were cut in one go
_SENTENCE_END = re.compile(r"[.!?…][\"'”’)\]*_]*$")
_CLAUSE_END = re.compile(r"[,;:—–-][\"'”’)\]*_]*$")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")
_LIST_OR_HEADING = re.compile(r"^\s*(?:\d+[.)]|[-*+]|#{1,6})\s")


def ends_at(sentence: str) -> str:
    """Where the clip's text ends: at a full stop ("sentence"), a list item or heading (also
    "sentence": a speaker pauses after it), a comma, semicolon, colon or dash ("clause"), or
    in the middle of a clause ("none")."""
    text = sentence.strip()
    if _SENTENCE_END.search(text) or _LIST_OR_HEADING.match(text) or "\n" in text:
        return "sentence"
    if _CLAUSE_END.search(text):
        return "clause"
    return "none"


def new_lines(path: Path, offset: int) -> tuple[list[dict[str, Any]], int]:
    """The lines serve_logged.py added to `path` after byte `offset`, and the new offset."""
    if not path.is_file():
        return [], offset
    with path.open("rb") as f:
        f.seek(offset)
        data = f.read()
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    return rows, offset + len(data)


def file_size(path: Path) -> int:
    return path.stat().st_size if path.is_file() else 0


def gap_cause(clip: dict[str, Any], previous: dict[str, Any]) -> str | None:
    """Why playback waited for the clip, or None when it didn't: it was made behind the clips
    before it ("queued": clips are made slower than they play), its text came from the LLM only
    after the clip before had started playing ("text late"), or it took longer to make than
    the clip before had left to play ("slow to make")."""
    if not clip["gap_ms"] or clip["gap_ms"] <= 0:
        return None
    if (clip["waited_ms"] or 0) > WAITED_MS:
        return "queued"
    text_at, previous_plays = clip["sentence_ms"], previous["plays_ms"]
    if text_at is not None and previous_plays is not None and text_at > previous_plays:
        return "text late"
    return "slow to make"


def ms_or_none(seconds: float | None) -> int | None:
    return None if seconds is None else round(seconds * 1000)


def analyze(summary: dict[str, Any], noted: list[dict[str, Any]]) -> dict[str, Any]:
    """One reply's clips from `time_reply.summarize`, joined in order with their lines from
    serve_logged.py, and the reply's rates."""
    clips = []
    previous: dict[str, Any] | None = None
    for row, note in zip(summary["clips"], noted, strict=False):
        seconds = row["seconds"]
        end_ms = (
            None if row["plays_ms"] is None or seconds is None else row["plays_ms"] + seconds * 1000
        )
        clip = {
            **row,
            "words": note["words"],
            "text": note["text"],
            "sentence": note["sentence"],
            "ends_at": ends_at(note["sentence"]),
            "wav_s": note["wav_s"],
            "stretch_ms": None if seconds is None else round((seconds - note["wav_s"]) * 1000),
            "lead_silence_ms": ms_or_none(note["lead_silence_s"]),
            "trail_silence_ms": ms_or_none(note["trail_silence_s"]),
            "end_ms": None if end_ms is None else round(end_ms),
            "pause_heard_ms": None,
            "cause": None,
            "after_ends_at": None,
            "cut_together": False,
        }
        if previous is not None:
            clip["after_ends_at"] = previous["ends_at"]
            if previous["end_ms"] is not None and row["first_byte_ms"] is not None:
                # Ready this long before the clip before it ended (negative: after).
                clip["ready_before_end_ms"] = previous["end_ms"] - row["first_byte_ms"]
            if clip["gap_ms"] is not None:
                clip["pause_heard_ms"] = (
                    (previous["trail_silence_ms"] or 0)
                    + clip["gap_ms"]
                    + (clip["lead_silence_ms"] or 0)
                )
            clip["cause"] = gap_cause(clip, previous)
            # Cut from the same stretch of text as the clip before, in the same moment.
            clip["cut_together"] = (
                row["sentence_ms"] is not None
                and previous["sentence_ms"] is not None
                and abs(row["sentence_ms"] - previous["sentence_ms"]) <= TOGETHER_MS
            )
        clips.append(clip)
        previous = clip
    words = sum(c["words"] for c in clips)
    played = [c for c in clips if c["end_ms"] is not None]
    span_s = (played[-1]["end_ms"] - played[0]["plays_ms"]) / 1000 if played else None
    in_clips_s = sum(c["seconds"] for c in played)
    speech_s = sum(
        c["wav_s"] - ((c["lead_silence_ms"] or 0) + (c["trail_silence_ms"] or 0)) / 1000
        for c in clips
    )
    made_s = sum((c["voice_ms"] or 0) + (c["video_ms"] or 0) for c in clips) / 1000
    writing_s = (
        None
        if summary["first_token_ms"] is None or summary["last_token_ms"] is None
        else (summary["last_token_ms"] - summary["first_token_ms"]) / 1000
    )
    gaps = [c for c in clips if (c["gap_ms"] or 0) > GAP_MS]
    pauses = [c for c in clips if (c["pause_heard_ms"] or 0) > GAP_MS]
    return {
        "prompt": summary["prompt"],
        "error": summary["error"],
        "first_word_heard_ms": summary["first_word_heard_ms"],
        "first_token_ms": summary["first_token_ms"],
        "last_token_ms": summary["last_token_ms"],
        "clips": clips,
        "words": words,
        "heard_s": None if span_s is None else round(span_s, 1),
        "rate_heard_wpm": rate(words, span_s),
        "rate_in_clips_wpm": rate(words, in_clips_s),
        # The voice's own pace as the app spoke it: the clips' speech, their silence left out.
        "rate_speech_wpm": rate(words, speech_s),
        "rate_llm_wpm": rate(words, writing_s),
        # Time to make the clips against how long they play: over 1 is slower than they play.
        "make_ratio": round(made_s / in_clips_s, 2) if in_clips_s else None,
        "gaps_over": len(gaps),
        "gaps_total_s": round(sum(c["gap_ms"] for c in gaps) / 1000, 1),
        "gap_causes": count_by(gaps, "cause"),
        "pauses_over": len(pauses),
        "pauses_mid_sentence": sum(1 for c in pauses if c["after_ends_at"] != "sentence"),
        "cut_together": sum(1 for c in clips if c["cut_together"]),
        # The silence the clips' own starts and ends add at the joins between them.
        "join_silence_s": round(
            sum(
                (a["trail_silence_ms"] or 0) + (b["lead_silence_ms"] or 0)
                for a, b in zip(clips, clips[1:], strict=False)
            )
            / 1000,
            1,
        ),
        "ends": count_by(clips, "ends_at"),
        "silence_ms": {
            "start": median([c["lead_silence_ms"] for c in clips]),
            "end": median([c["trail_silence_ms"] for c in clips]),
        },
        "stretch_ms_max": max((abs(c["stretch_ms"] or 0) for c in clips), default=None),
        "own_rate_wpm": None,
        "own_seconds": None,
    }


def rate(words: int, seconds: float | None) -> float | None:
    return round(words / seconds * 60) if seconds else None


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rows:
        counts[str(r[key])] = counts.get(str(r[key]), 0) + 1
    return counts


def median(values: Sequence[int | None]) -> int | None:
    known = sorted(v for v in values if v is not None)
    if not known:
        return None
    mid = len(known) // 2
    return known[mid] if len(known) % 2 else round((known[mid - 1] + known[mid]) / 2)


def sentences_of(text: str) -> list[str]:
    """The reply's spoken text cut at each full stop, for speaking a sentence at a time."""
    return [t for t in _SENTENCE_SPLIT.split(text.strip()) if t]


def own_rate(result: dict[str, Any], speaker: Any, voice: str) -> None:
    """Speak the reply a whole sentence at a time with `imageskin say`'s engine, outside the
    app, for the voice's own speaking rate: words a minute of speech, with the silence each
    sentence starts and ends with left out. A sentence at a time, as Chatterbox stops at about
    40 s of speech, so it can't say a long reply in one go."""
    from serve_logged import silences

    from imageskin.voice import write_speech

    text = " ".join(c["text"] for c in result["clips"])
    if not text:
        return
    start = time.perf_counter()
    voiced = 0.0
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "sentence.wav"
        for sentence in sentences_of(text):
            write_speech(speaker.speak(voice, sentence), wav, wav.with_suffix(".json"))
            seconds, lead, trail = silences(wav)
            voiced += max(0.0, seconds - lead - trail)
    result["own_seconds"] = round(voiced, 1)
    result["own_rate_wpm"] = rate(result["words"], voiced)
    logger.info(
        "Own rate measured",
        extra={
            "words": result["words"],
            "voiced_s": round(voiced, 1),
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )


def cell(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def table(header: list[str], rows: list[list[object]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return lines + ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]


def markdown(results: list[dict[str, Any]], label: str) -> str:
    out = [f"# Where the pauses come from in a long reply ({label})", ""]
    out.append(
        "Times in milliseconds from the prompt being sent, rates in words a minute. A gap is "
        "playback waiting for the clip; the pause heard is the silence at the end of the clip "
        "before, the gap and the silence at the start of this one."
    )
    out.append("")
    out += table(
        [
            "Reply",
            "Words",
            "First word heard",
            "Heard for (s)",
            "Rate heard",
            "Rate in clips",
            "Speech rate",
            "Own rate",
            "LLM writes",
            "Make/play",
            f"Gaps > {GAP_MS} ms",
            "Gap total (s)",
            "Gap causes",
            f"Pauses heard > {GAP_MS} ms",
            "Of them mid-sentence",
            "Cut together",
            "Silence at joins (s)",
            "Clip ends",
            "Start/end silence",
        ],
        [
            [
                i,
                r["words"],
                r["first_word_heard_ms"],
                r["heard_s"],
                r["rate_heard_wpm"],
                r["rate_in_clips_wpm"],
                r.get("rate_speech_wpm"),
                r["own_rate_wpm"],
                r["rate_llm_wpm"],
                r["make_ratio"],
                r["gaps_over"],
                r["gaps_total_s"],
                ", ".join(f"{k} {v}" for k, v in r["gap_causes"].items()) or "-",
                r["pauses_over"],
                r["pauses_mid_sentence"],
                r["cut_together"],
                r["join_silence_s"],
                ", ".join(f"{k} {v}" for k, v in r["ends"].items()),
                f"{cell(r['silence_ms']['start'])}/{cell(r['silence_ms']['end'])}",
            ]
            for i, r in enumerate(results, 1)
        ],
    )
    for i, r in enumerate(results, 1):
        out += ["", f"## Reply {i}: {r['prompt']}", ""]
        if r["error"]:
            out += [f"Error: {r['error']}", ""]
        out += table(
            [
                "Clip",
                "Words",
                "Ends at",
                "Text came",
                "Waited",
                "Voice",
                "Video",
                "First byte",
                "Plays",
                "Seconds",
                "Speech s",
                "Start/end silence",
                "Ready before end",
                "Gap",
                "Pause heard",
                "Cause",
                "Text",
            ],
            [
                [
                    c["clip"],
                    c["words"],
                    c["ends_at"],
                    c["sentence_ms"],
                    c["waited_ms"],
                    c["voice_ms"],
                    c["video_ms"],
                    c["first_byte_ms"],
                    c["plays_ms"],
                    c["seconds"],
                    c["wav_s"],
                    f"{cell(c['lead_silence_ms'])}/{cell(c['trail_silence_ms'])}",
                    c.get("ready_before_end_ms"),
                    c["gap_ms"],
                    c["pause_heard_ms"],
                    c["cause"],
                    c["text"][:60] + ("…" if len(c["text"]) > 60 else ""),
                ]
                for c in r["clips"]
            ],
        )
    return "\n".join(out) + "\n"


def timeline(result: dict[str, Any], path: Path, title: str) -> bool:
    """A picture of the reply: when each clip's text came, its making (voice, then video) and
    its playing, with the silence at each clip's start and end and every gap over GAP_MS
    marked. False when matplotlib isn't installed."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.info("No timeline: matplotlib isn't installed")
        return False
    clips = result["clips"]
    fig, ax = plt.subplots(figsize=(12, 3.2), dpi=120)
    voice, video, play, gap = "#2a78d6", "#93c1f4", "#1b9e77", "#d6402a"
    quiet = "#c8ccd0"  # the silence at a clip's start and end
    for c in clips:
        if c["sentence_ms"] is not None:
            ax.plot([c["sentence_ms"] / 1000] * 2, [2.6, 3.4], color="#555555", linewidth=1)
        start = c["sentence_ms"] + (c["waited_ms"] or 0) if c["sentence_ms"] is not None else None
        if start is not None and c["voice_ms"] is not None:
            ax.barh(
                1.5 + (c["clip"] % 2) * 0.35,
                c["voice_ms"] / 1000,
                left=start / 1000,
                height=0.3,
                color=voice,
            )
            if c["video_ms"] is not None:
                ax.barh(
                    1.5 + (c["clip"] % 2) * 0.35,
                    c["video_ms"] / 1000,
                    left=(start + c["voice_ms"]) / 1000,
                    height=0.3,
                    color=video,
                )
        if c["plays_ms"] is not None and c["seconds"] is not None:
            ax.barh(
                0.5,
                c["seconds"],
                left=c["plays_ms"] / 1000,
                height=0.5,
                color=play,
                edgecolor="white",
                linewidth=1,
            )
            end = c["plays_ms"] + c["seconds"] * 1000
            for silence, left in (
                (c["lead_silence_ms"], c["plays_ms"]),
                (c["trail_silence_ms"], end - (c["trail_silence_ms"] or 0)),
            ):
                if silence:
                    ax.barh(0.5, silence / 1000, left=left / 1000, height=0.5, color=quiet)
            ax.text(
                (c["plays_ms"] / 1000) + c["seconds"] / 2,
                0.5,
                str(c["clip"]),
                ha="center",
                va="center",
                color="white",
                fontsize=7,
            )
            if (c["gap_ms"] or 0) > GAP_MS:
                ax.barh(
                    0.5,
                    c["gap_ms"] / 1000,
                    left=(c["plays_ms"] - c["gap_ms"]) / 1000,
                    height=0.5,
                    color=gap,
                )
    ax.set_yticks([0.5, 1.67, 3.0], ["Playing", "Making", "Text from LLM"])
    ax.set_xlabel("Seconds from the prompt being sent")
    ax.set_title(title, loc="left", fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    from matplotlib.patches import Patch

    ax.legend(
        handles=[
            Patch(color=voice, label="voice"),
            Patch(color=video, label="video"),
            Patch(color=play, label="playing"),
            Patch(color=quiet, label="silence in the clip"),
            Patch(color=gap, label=f"gap > {GAP_MS} ms"),
        ],
        loc="upper left",
        bbox_to_anchor=(1.0, 1.0),
        frameon=False,
        fontsize=8,
    )
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return True


def wait_for_app(base: str, wait_s: float, sleep: Callable[[float], None] = time.sleep) -> bool:
    """Whether the app answers, asking every few seconds for up to `wait_s` seconds while it
    starts."""
    from imageskin import time_reply

    deadline = time.perf_counter() + wait_s
    while True:
        try:
            time_reply.ask(base + "/health", timeout=10)
            return True
        except OSError as e:
            if time.perf_counter() >= deadline:
                logger.error("Could not reach the app", extra={"url": base, "error": str(e)})
                return False
        logger.info("Waiting for the app to start", extra={"url": base})
        sleep(WAIT_EVERY_S)


def run(
    base: str,
    prompts: list[str],
    noted_path: Path,
    out: Path,
    label: str,
    voice: str,
    voice_sample: Path | None,
    measure_own_rate: bool = True,
    wait_s: float = 0.0,
) -> int:
    from imageskin import time_reply

    start = time.perf_counter()
    base = base.rstrip("/")
    if not wait_for_app(base, wait_s):
        return 1
    logger.info("Long reply experiment started", extra={"replies": len(prompts), "label": label})
    results = []
    offset = file_size(noted_path)
    for prompt in prompts:
        summary = time_reply.summarize(time_reply.measure(base, prompt))
        noted, offset = new_lines(noted_path, offset)
        if len(noted) != len(summary["clips"]):
            logger.warning(
                "Clips and noted lines differ",
                extra={"clips": len(summary["clips"]), "noted": len(noted)},
            )
        result = analyze(summary, noted)
        logger.info(
            "Long reply measured",
            extra={
                "words": result["words"],
                "clips": len(result["clips"]),
                "rate_heard_wpm": result["rate_heard_wpm"],
                "gaps_over": result["gaps_over"],
            },
        )
        results.append(result)
        if summary.get("status") in REFUSED:
            # The chat is locked (no accepted sample) or the prompt is refused: every other
            # prompt would be too, so say why once rather than measure nothing three times.
            logger.error(
                "The app refused the prompt; stopping",
                extra={"status": summary["status"], "error": summary["error"]},
            )
            print(f"The app refused the prompt ({summary['status']}): {summary['error']}")
            print("Make sure a typed question gets a spoken answer in the chat, then run again.")
            return 1
    if measure_own_rate:
        from imageskin.cli import voice_engine

        try:
            speaker, voice = voice_engine(voice, voice_sample)
            for result in results:
                own_rate(result, speaker, voice)
        except Exception as e:  # the voice's own errors: the rest is still worth writing
            logger.error("Could not measure the own rate", extra={"error": str(e)})
    out.mkdir(parents=True, exist_ok=True)
    report = markdown(results, label)
    (out / f"long-reply-{label}.md").write_text(report, encoding="utf-8")
    (out / f"long-reply-{label}.json").write_text(
        json.dumps({"label": label, "results": results}, indent=2), encoding="utf-8"
    )
    for i, result in enumerate(results, 1):
        timeline(result, out / f"timeline-{label}-{i}.png", f"Reply {i} ({label})")
    print(report)
    failed = sum(1 for r in results if r["error"])
    logger.info(
        "Long reply experiment done",
        extra={
            "replies": len(results),
            "failed": failed,
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    from replies import PROMPTS

    from imageskin.kokoro_engine import DEFAULT_VOICE
    from imageskin.logging_setup import setup_logging

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("clips", type=Path, help="the JSONL file serve_logged.py writes")
    parser.add_argument("prompts", nargs="*", help="default: the three in replies.py")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("-o", "--out", type=Path, default=Path("long-reply"))
    parser.add_argument("--label", default="run")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="Kokoro voice for the own rate")
    parser.add_argument("--voice-sample", type=Path, help="the cloned voice's sample, instead")
    parser.add_argument(
        "--no-own-rate",
        action="store_true",
        help="skip speaking each reply again outside the app (the Speech rate column still "
        "gives the voice's own pace)",
    )
    parser.add_argument(
        "--wait", type=float, default=300, help="seconds to wait for the app to start"
    )
    args = parser.parse_args(argv)
    setup_logging()
    return run(
        args.url,
        args.prompts or list(PROMPTS),
        args.clips,
        args.out,
        args.label,
        args.voice,
        args.voice_sample,
        not args.no_own_rate,
        args.wait,
    )


if __name__ == "__main__":
    sys.exit(main())
